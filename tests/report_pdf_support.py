# SPDX-License-Identifier: Apache-2.0
"""Read back a PDF the report renderer wrote, with the standard library alone.

Enough of the format to prove the file is well formed and says what it should: the
header and trailer, every cross-reference offset landing on its object, the page objects,
the document information, and each page's text after ASCII85 and Flate decoding.
"""

from __future__ import annotations

import base64
import re
import zlib
from dataclasses import dataclass

OBJECT = re.compile(rb"(\d+) 0 obj(.*?)endobj", re.DOTALL)
STREAM = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\s*endstream", re.DOTALL)
TEXT = re.compile(rb"\((.*?)(?<!\\)\) Tj")


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
    page_texts = []
    for number in pages:
        contents = int(re.search(rb"/Contents (\d+) 0 R", objects[number]).group(1))
        stream = STREAM.search(objects[contents])
        assert stream is not None
        data = stream.group(2).strip()
        if b"/ASCII85Decode" in stream.group(1):
            data = base64.a85decode(data.removesuffix(b"~>"))
        if b"/FlateDecode" in stream.group(1):
            data = zlib.decompress(data)
        page_texts.append(
            " ".join(
                text.decode("cp1252").replace("\\(", "(").replace("\\)", ")")
                for text in TEXT.findall(data)
            )
        )
    fonts = {font.decode() for font in re.findall(rb"/BaseFont /([A-Za-z-]+)", content)}
    return ParsedPdf(
        objects=objects, pages=pages, info=objects[info_number], page_texts=page_texts, fonts=fonts
    )
