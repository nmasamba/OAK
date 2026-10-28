# SPDX-License-Identifier: Apache-2.0
"""Read back a PDF the report renderer wrote, with the standard library alone.

Enough of the format to prove the file is well formed and says what it should: the
header and trailer, every cross-reference offset landing on its object, the page objects,
the document information, and each page's text after ASCII85 and Flate decoding. The
embedded fonts are subsets that number their glyphs in the order a document first uses
them, so a page's strings are read through each font's ToUnicode map, following the `Tf`
operators that switch between them.
"""

from __future__ import annotations

import base64
import re
import zlib
from dataclasses import dataclass

OBJECT = re.compile(rb"(\d+) 0 obj(.*?)endobj", re.DOTALL)
STREAM = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\s*endstream", re.DOTALL)
# A font switch, or a literal string shown with Tj (escapes kept for _unescape).
TOKEN = re.compile(
    rb"/(?P<font>[A-Za-z0-9+]+) [0-9.]+ Tf|\((?P<text>(?:[^\\)]|\\.)*)\) Tj", re.DOTALL
)
BFCHAR = re.compile(rb"<([0-9A-Fa-f]{2})> <([0-9A-Fa-f]+)>")
ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


@dataclass(frozen=True)
class ParsedPdf:
    objects: dict[int, bytes]
    pages: list[int]
    info: bytes
    page_texts: list[str]
    fonts: set[str]


def parse_pdf(content: bytes) -> ParsedPdf:
    assert content.startswith(b"%PDF-1.")
    assert content.rstrip().endswith(b"%%EOF")
    start = int(re.findall(rb"startxref\s+(\d+)\s+%%EOF", content)[-1])
    assert content[start:].startswith(b"xref")
    header = re.match(rb"xref\s+0 (\d+)\s+", content[start:])
    assert header is not None
    count = int(header.group(1))
    table = content[start + header.end() : start + header.end() + 20 * count]
    for number in range(1, count):
        entry = table[20 * number : 20 * number + 20]
        offset, _, kind = entry[:10], entry[11:16], entry[17:18]
        if kind == b"n":
            assert content[int(offset) :].startswith(f"{number} 0 obj".encode()), number
    objects = {int(match.group(1)): match.group(2) for match in OBJECT.finditer(content)}
    pages = [
        number
        for number, body in sorted(objects.items())
        if re.search(rb"/Type /Page\b(?!s)", body)
    ]
    info_number = int(re.findall(rb"/Info (\d+) 0 R", content)[-1])
    maps = {
        name.decode(): _unicode_map(_stream(objects[int(reference)]))
        for body in objects.values()
        for name, reference in re.findall(
            rb"/Name /([A-Za-z0-9+]+) .*?/ToUnicode (\d+) 0 R", body, re.DOTALL
        )
    }
    page_texts = []
    for number in pages:
        contents = int(re.search(rb"/Contents (\d+) 0 R", objects[number]).group(1))
        data = _stream(objects[contents])
        current: dict[int, str] | None = None
        shown = []
        for token in TOKEN.finditer(data):
            if token.group("font") is not None:
                current = maps.get(token.group("font").decode())
                continue
            raw = _unescape(token.group("text"))
            shown.append(
                raw.decode("cp1252") if current is None else "".join(current[code] for code in raw)
            )
        page_texts.append(" ".join(shown))
    fonts = {
        font.decode() for font in re.findall(rb"/BaseFont /(?:[A-Z]{6}\+)?([A-Za-z-]+)", content)
    }
    return ParsedPdf(
        objects=objects, pages=pages, info=objects[info_number], page_texts=page_texts, fonts=fonts
    )


def _stream(body: bytes) -> bytes:
    stream = STREAM.search(body)
    assert stream is not None
    data = stream.group(2).strip()
    if b"/ASCII85Decode" in stream.group(1):
        data = base64.a85decode(data.removesuffix(b"~>"))
    if b"/FlateDecode" in stream.group(1):
        data = zlib.decompress(data)
    return data


def _unicode_map(cmap: bytes) -> dict[int, str]:
    return {
        int(code, 16): bytes.fromhex(target.decode()).decode("utf-16-be").replace("\x00", "")
        for section in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.DOTALL)
        for code, target in BFCHAR.findall(section)
    }


def _unescape(literal: bytes) -> bytes:
    """A PDF literal string's bytes: backslash escapes, including octal, resolved."""

    out = bytearray()
    index = 0
    while index < len(literal):
        byte = literal[index : index + 1]
        if byte != b"\\":
            out += byte
            index += 1
            continue
        following = literal[index + 1 : index + 2]
        octal = re.match(rb"[0-7]{1,3}", literal[index + 1 : index + 4])
        if octal is not None:
            out.append(int(octal.group(0), 8))
            index += 1 + len(octal.group(0))
        else:
            out += ESCAPES.get(following, following)
            index += 2
    return bytes(out)
