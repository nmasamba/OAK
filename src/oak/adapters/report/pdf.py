# SPDX-License-Identifier: Apache-2.0
"""The architecture report as a 16:9 PDF, drawn with reportlab's standard fonts.

Every page is a slide: the section's conclusion as its title, a one-line subtitle, the
blocks, and a footer with the case title, the report date and "page n of N". Long tables
and fact lists continue on the next page with their header repeated. The cover alone sits
on the dark ground; every other page is paper and ink with one brass accent.

Determinism: the canvas runs in reportlab's invariant mode, the document dates come from
the report's own `generated_at`, and page streams are compressed with zlib, so the same
document gives the same bytes in any process. Fonts are the PDF standard Helvetica and
Courier, which every reader has; none is embedded. They cover the Windows-1252 character
set, so any other character is drawn as "?" (the JSON report keeps it).
"""

from __future__ import annotations

import io
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from oak.adapters.report import palette
from oak.domain import OAKError
from oak.domain.report import MAXIMUM_RENDERING_BYTES, PDF_MEDIA_TYPE

RENDERER_NAME = "oak-report-renderer"
RENDERER_VERSION = "1.0.0"
PAGE_WIDTH = 960.0
PAGE_HEIGHT = 540.0
MARGIN_X = 48.0
TOP = 34.0
CONTENT_BOTTOM = 46.0
FOOTER_BASELINE = 22.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
BLOCK_GAP = 12.0
CELL_PAD_X = 5.0
CELL_PAD_Y = 4.0
# The tallest single unit: a page's content area less the tallest header (a two-line title,
# a two-line subtitle and its appendix line) and a table's caption and header row. Anything
# taller is split into continuing pieces, so no record's text can run off a page.
UNIT_LIMIT = 280.0
ELLIPSIS = "..."
BAR_HEIGHT = 9.0

FONT = palette.FONT
BOLD = palette.FONT_BOLD
ITALIC = palette.FONT_ITALIC
MONO = palette.FONT_MONO

FILLED_CIRCLE = frozenset({"pass", "satisfied", "clear", "current"})
CROSS = frozenset({"fail", "revoked", "infeasible"})
RING = frozenset({"unknown", "absent", "required"})


def pdf_text(text: str) -> str:
    """Text the standard fonts can draw: Windows-1252, anything else as "?"."""

    normalised = unicodedata.normalize("NFKC", str(text))
    characters = []
    for character in normalised:
        if character in "\n\t":
            characters.append(" ")
            continue
        try:
            character.encode("cp1252")
        except UnicodeEncodeError:
            characters.append("?")
        else:
            characters.append(character)
    return "".join(characters)


def text_width(text: str, font: str, size: float) -> float:
    return float(stringWidth(pdf_text(text), font, size))


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Greedy word wrap; a word wider than the line is broken by characters.

    The text is made drawable once and each word measured once, so a long record costs
    time in proportion to its length.
    """

    space = float(stringWidth(" ", font, size))
    lines: list[str] = []
    current = ""
    current_width = 0.0
    for word in pdf_text(text).split(" "):
        word_width = float(stringWidth(word, font, size))
        if current and current_width + space + word_width <= width:
            current, current_width = f"{current} {word}", current_width + space + word_width
            continue
        if not current and word_width <= width:
            current, current_width = word, word_width
            continue
        if current:
            lines.append(current)
        if word_width <= width:
            current, current_width = word, word_width
            continue
        current, current_width = "", 0.0
        for character in word:
            character_width = float(stringWidth(character, font, size))
            if current and current_width + character_width > width:
                lines.append(current)
                current, current_width = "", 0.0
            current, current_width = current + character, current_width + character_width
    if current or not lines:
        lines.append(current)
    return lines


def fit(text: str, font: str, size: float, width: float) -> str:
    """One line of text, shortened with an ellipsis when it is wider than `width`."""

    drawable = pdf_text(text)
    if stringWidth(drawable, font, size) <= width:
        return drawable
    room = width - float(stringWidth(ELLIPSIS, font, size))
    kept, used = "", 0.0
    for character in drawable:
        used += float(stringWidth(character, font, size))
        if used > room:
            break
        kept += character
    return kept.rstrip() + ELLIPSIS


# ----- drawing primitives ----------------------------------------------------------------


class Ink:
    """Draw in top-down coordinates on one page: y grows downwards from the page top."""

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas

    def fill(self, colour: str) -> None:
        self.canvas.setFillColor(HexColor(colour))

    def stroke(self, colour: str, width: float = 0.75) -> None:
        self.canvas.setStrokeColor(HexColor(colour))
        self.canvas.setLineWidth(width)

    def text(self, x: float, top: float, text: str, font: str, size: float, colour: str) -> None:
        self.fill(colour)
        self.canvas.setFont(font, size)
        self.canvas.drawString(x, PAGE_HEIGHT - top - size * 0.8, pdf_text(text))

    def rect(
        self,
        x: float,
        top: float,
        width: float,
        height: float,
        *,
        fill: str | None = None,
        stroke: str | None = None,
        dash: bool = False,
    ) -> None:
        if fill is not None:
            self.fill(fill)
        if stroke is not None:
            self.stroke(stroke)
        if dash:
            self.canvas.setDash(3, 2)
        self.canvas.rect(
            x,
            PAGE_HEIGHT - top - height,
            width,
            height,
            stroke=1 if stroke else 0,
            fill=1 if fill else 0,
        )
        if dash:
            self.canvas.setDash()

    def line(
        self, x1: float, top1: float, x2: float, top2: float, colour: str, width: float
    ) -> None:
        self.stroke(colour, width)
        self.canvas.line(x1, PAGE_HEIGHT - top1, x2, PAGE_HEIGHT - top2)

    def polygon(
        self, points: Sequence[tuple[float, float]], *, fill: str | None, stroke: str
    ) -> None:
        self.stroke(stroke, 0.9)
        if fill is not None:
            self.fill(fill)
        path = self.canvas.beginPath()
        first, *rest = points
        path.moveTo(first[0], PAGE_HEIGHT - first[1])
        for x, y in rest:
            path.lineTo(x, PAGE_HEIGHT - y)
        path.close()
        self.canvas.drawPath(path, stroke=1, fill=1 if fill else 0)

    def circle(self, x: float, top: float, radius: float, *, fill: str | None, stroke: str) -> None:
        self.stroke(stroke, 0.9)
        if fill is not None:
            self.fill(fill)
        self.canvas.circle(x, PAGE_HEIGHT - top, radius, stroke=1, fill=1 if fill else 0)


def draw_status_shape(ink: Ink, status: str, x: float, middle: float, colour: str) -> None:
    """The shape half of "shape and word": distinct outlines, never colour alone."""

    r = 3.2
    if status in FILLED_CIRCLE:
        ink.circle(x + r, middle, r, fill=colour, stroke=colour)
    elif status in CROSS:
        ink.line(x, middle - r, x + 2 * r, middle + r, colour, 1.3)
        ink.line(x, middle + r, x + 2 * r, middle - r, colour, 1.3)
    elif status in RING:
        ink.circle(x + r, middle, r, fill=None, stroke=colour)
    elif status == "not_applicable":
        ink.line(x, middle, x + 2 * r, middle, colour, 1.3)
    elif status == "selected":
        ink.polygon(
            [
                (x + r, middle - r - 1),
                (x + 2 * r + 1, middle),
                (x + r, middle + r + 1),
                (x - 1, middle),
            ],
            fill=palette.BRASS,
            stroke=palette.BRASS,
        )
    elif status == "frontier":
        ink.polygon(
            [(x, middle + r), (x + 2 * r, middle + r), (x + r, middle - r)],
            fill=colour,
            stroke=colour,
        )
    elif status == "dominated":
        ink.polygon(
            [(x, middle + r), (x + 2 * r, middle + r), (x + r, middle - r)],
            fill=None,
            stroke=colour,
        )
    elif status == "blocked":
        ink.rect(x, middle - r, 2 * r, 2 * r, fill=colour)
    elif status == "expired":
        ink.circle(x + r, middle, r, fill=None, stroke=colour)
        ink.line(x, middle + r, x + 2 * r, middle - r, colour, 1.0)
    else:
        ink.circle(x + r, middle, r, fill=None, stroke=colour)


def draw_mark_shape(ink: Ink, kind: str, x: float, middle: float, colour: str) -> None:
    """Where a value came from, in the workspace's shapes (`web/src/ui/ProvenanceMark.tsx`):
    a filled square for a fact from the brief, a ring for an inference, a triangle for a
    domain default, a diamond for a model's proposal, a half-filled square for a reviewer's
    correction, a dashed square for an unknown."""

    r = 3.2
    if kind == "explicit":
        ink.rect(x, middle - r, 2 * r, 2 * r, fill=colour)
    elif kind == "inferred_from_brief":
        ink.circle(x + r, middle, r, fill=None, stroke=colour)
    elif kind == "domain_default":
        ink.polygon(
            [(x, middle + r), (x + 2 * r, middle + r), (x + r, middle - r)],
            fill=None,
            stroke=colour,
        )
    elif kind == "model_proposed":
        ink.polygon(
            [(x + r, middle - r), (x + 2 * r, middle), (x + r, middle + r), (x, middle)],
            fill=None,
            stroke=colour,
        )
    elif kind == "user_correction":
        ink.rect(x, middle - r, 2 * r, 2 * r, stroke=colour)
        ink.rect(x, middle, 2 * r, r, fill=colour)
    elif kind in {"policy", "measured"}:
        ink.circle(x + r, middle, r, fill=colour, stroke=colour)
    else:
        ink.rect(x, middle - r, 2 * r, 2 * r, stroke=colour, dash=True)


# ----- units: the atoms the paginator places -----------------------------------------------


@dataclass
class Unit:
    """Something drawn at full content width, with a known height."""

    height: float
    draw: Callable[[Ink, float], None]
    keep_with_next: bool = False
    repeat: Unit | None = None


@dataclass
class Line:
    text: str
    font: str
    size: float
    colour: str
    indent: float = 0.0
    shape: str | None = None


def _lines_height(lines: Sequence[Line], leading: float) -> float:
    return len(lines) * leading


def _pieces(lines: list[Line], leading: float, reserve: float) -> list[list[Line]]:
    """Lines cut into runs that each fit one unit, with `reserve` points kept for its frame."""

    per_piece = max(1, int((UNIT_LIMIT - reserve) // leading))
    return [lines[start : start + per_piece] for start in range(0, len(lines), per_piece)] or [[]]


def _draw_lines(ink: Ink, x: float, top: float, lines: Sequence[Line], leading: float) -> None:
    for index, line in enumerate(lines):
        offset = x + line.indent
        if line.shape is not None and line.shape.startswith("mark:"):
            draw_mark_shape(
                ink,
                line.shape.removeprefix("mark:"),
                offset,
                top + index * leading + line.size * 0.42,
                line.colour,
            )
            offset += 11
        elif line.shape is not None:
            draw_status_shape(
                ink, line.shape, offset, top + index * leading + line.size * 0.42, line.colour
            )
            offset += 11
        ink.text(offset, top + index * leading, line.text, line.font, line.size, line.colour)


def _value_lines(
    value: dict[str, Any],
    width: float,
    size: float,
    *,
    display: str = "full",
    colour: str = palette.INK,
    muted: str = palette.INK_MUTED,
) -> list[Line]:
    kind = value.get("type")
    if kind == "text":
        lines = [Line(t, FONT, size, colour) for t in wrap(str(value["text"]), FONT, size, width)]
        return lines
    if kind == "list":
        items = value.get("items") or []
        if not items:
            return [Line("none", FONT, size, muted)]
        result: list[Line] = []
        for item in items:
            wrapped = wrap(str(item), FONT, size, width - 9)
            result.append(Line(f"- {wrapped[0]}", FONT, size, colour))
            result.extend(Line(rest, FONT, size, colour, indent=9) for rest in wrapped[1:])
        return result
    if kind == "quantity":
        shown = str(value["short"] if display == "short" else value["text"])
        lines = [Line(t, FONT, size, colour) for t in wrap(shown, FONT, size, width)]
        basis = str(value.get("basis") or "")
        if basis in {"synthetic estimate", "assumed", "measured", "confirmed", "estimated"}:
            lines.append(Line(basis, ITALIC, size - 1.5, muted))
        return lines
    if kind == "status":
        status = str(value.get("status"))
        word_lines = wrap(str(value.get("word")), BOLD, size, width - 11)
        lines = [Line(word_lines[0], BOLD, size, colour, shape=status)]
        lines.extend(Line(t, BOLD, size, colour, indent=11) for t in word_lines[1:])
        reason = value.get("reason")
        if reason:
            lines.extend(
                Line(t, FONT, size - 1.5, muted, indent=11)
                for t in wrap(str(reason), FONT, size - 1.5, width - 11)
            )
        return lines
    reason = str(value.get("reason") or "")
    lines = [Line("unknown", BOLD, size, colour, shape="unknown")]
    lines.extend(
        Line(t, FONT, size - 1.5, muted, indent=11)
        for t in wrap(reason, FONT, size - 1.5, width - 11)
    )
    return lines


def _mark_line(value: dict[str, Any], size: float, muted: str = palette.INK_MUTED) -> Line | None:
    mark = value.get("mark")
    if not isinstance(mark, dict):
        return None
    return Line(str(mark.get("word")), FONT, size - 1.5, muted, shape=f"mark:{mark.get('class')}")


def _marked_lines(
    value: dict[str, Any],
    width: float,
    size: float,
    *,
    display: str = "full",
    colour: str = palette.INK,
    muted: str = palette.INK_MUTED,
) -> list[Line]:
    """A value and, under it, where it came from; a value that is only its mark is drawn once."""

    mark = _mark_line(value, size, muted) if value.get("type") in {"text", "list"} else None
    if mark is not None and value.get("type") == "text" and value.get("text") == mark.text:
        return [Line(mark.text, FONT, size, colour, shape=mark.shape)]
    lines = _value_lines(value, width, size, display=display, colour=colour, muted=muted)
    if mark is not None:
        lines.append(mark)
    return lines


# ----- blocks to units ---------------------------------------------------------------------


def _heading_unit(text: str, size: float = 10.5) -> Unit:
    lines = [Line(t, BOLD, size, palette.INK) for t in wrap(text, BOLD, size, CONTENT_WIDTH)]
    leading = size * 1.3
    return Unit(
        height=_lines_height(lines, leading) + 3,
        draw=lambda ink, top: _draw_lines(ink, MARGIN_X, top, lines, leading),
        keep_with_next=True,
    )


def _caption_unit(text: str) -> Unit:
    size = 8.5
    lines = [
        Line(t, ITALIC, size, palette.INK_MUTED) for t in wrap(text, ITALIC, size, CONTENT_WIDTH)
    ]
    leading = size * 1.3
    return Unit(
        height=_lines_height(lines, leading) + 2,
        draw=lambda ink, top: _draw_lines(ink, MARGIN_X, top, lines, leading),
        keep_with_next=True,
    )


def _column_widths(
    columns: Sequence[str], rows: Sequence[Sequence[str]], size: float
) -> list[float]:
    natural = []
    for index, column in enumerate(columns):
        widest = text_width(column, BOLD, size)
        for row in rows:
            if index < len(row):
                widest = max(widest, min(text_width(row[index], FONT, size), 360.0))
        natural.append(widest + 2 * CELL_PAD_X)
    total = sum(natural)
    if total <= CONTENT_WIDTH:
        spare = (CONTENT_WIDTH - total) / len(natural)
        return [width + spare for width in natural]
    minimum = 64.0
    widths = [max(minimum, width * CONTENT_WIDTH / total) for width in natural]
    scale = CONTENT_WIDTH / sum(widths)
    return [width * scale for width in widths]


def _plain(value: dict[str, Any], display: str) -> str:
    kind = value.get("type")
    if kind == "text":
        return str(value["text"])
    if kind == "list":
        return max((str(item) for item in value.get("items") or []), key=len, default="none")
    if kind == "quantity":
        return str(value["short"] if display == "short" else value["text"])
    if kind == "status":
        return str(value.get("word"))
    return "unknown"


def _table_units(block: dict[str, Any]) -> list[Unit]:
    size = 8.5
    leading = size * 1.32
    display = str(block.get("display") or "full")
    columns = [str(column) for column in block["columns"]]
    plain_rows = [[_plain(cell, display) for cell in row["cells"]] for row in block["rows"]]
    widths = _column_widths(columns, plain_rows, size)
    units: list[Unit] = []
    if block.get("heading"):
        units.append(_heading_unit(str(block["heading"])))
    units.append(_caption_unit(str(block["caption"])))

    header_cells = [
        [Line(t, BOLD, size, palette.INK) for t in wrap(column, BOLD, size, w - 2 * CELL_PAD_X)]
        for column, w in zip(columns, widths, strict=True)
    ]
    header_height = max(_lines_height(cells, leading) for cells in header_cells) + 2 * CELL_PAD_Y

    def draw_header(ink: Ink, top: float) -> None:
        ink.rect(MARGIN_X, top, CONTENT_WIDTH, header_height, fill=palette.PAPER_SHADE)
        x = MARGIN_X
        for cells, width in zip(header_cells, widths, strict=True):
            _draw_lines(ink, x + CELL_PAD_X, top + CELL_PAD_Y, cells, leading)
            x += width
        ink.line(
            MARGIN_X,
            top + header_height,
            MARGIN_X + CONTENT_WIDTH,
            top + header_height,
            palette.BRASS,
            0.8,
        )

    header = Unit(height=header_height, draw=draw_header, keep_with_next=True)
    units.append(header)
    for row in block["rows"]:
        cell_lines: list[list[Line]] = []
        for index, width in enumerate(widths):
            cell = (
                row["cells"][index]
                if index < len(row["cells"])
                else {"type": "text", "text": "", "mark": None}
            )
            cell_lines.append(_marked_lines(cell, width - 2 * CELL_PAD_X, size, display=display))
        # A row taller than one unit continues in pieces; only its last piece is ruled off.
        per_piece = max(1, int((UNIT_LIMIT - 2 * CELL_PAD_Y) // leading))
        tallest = max(1, *(len(lines) for lines in cell_lines))
        for start in range(0, tallest, per_piece):
            piece = [lines[start : start + per_piece] for lines in cell_lines]
            last = start + per_piece >= tallest
            height = max(_lines_height(lines, leading) for lines in piece) + 2 * CELL_PAD_Y

            def draw_row(
                ink: Ink,
                top: float,
                piece: list[list[Line]] = piece,
                height: float = height,
                last: bool = last,
            ) -> None:
                x = MARGIN_X
                for lines, width in zip(piece, widths, strict=True):
                    _draw_lines(ink, x + CELL_PAD_X, top + CELL_PAD_Y, lines, leading)
                    x += width
                if last:
                    ink.line(
                        MARGIN_X,
                        top + height,
                        MARGIN_X + CONTENT_WIDTH,
                        top + height,
                        palette.RULE,
                        0.5,
                    )

            units.append(Unit(height=height, draw=draw_row, repeat=header))
    return units


def _facts_units(
    block: dict[str, Any], *, colour: str = palette.INK, muted: str = palette.INK_MUTED
) -> list[Unit]:
    size = 10.0
    leading = size * 1.32
    label_width = 210.0
    value_width = CONTENT_WIDTH - label_width - 10
    units: list[Unit] = []
    if block.get("heading"):
        units.append(_heading_unit(str(block["heading"])))
    for item in block["items"]:
        labels = [
            Line(t, BOLD, size - 1, muted)
            for t in wrap(str(item["label"]), BOLD, size - 1, label_width)
        ]
        values = _marked_lines(item["value"], value_width, size, colour=colour, muted=muted)
        per_piece = max(1, int((UNIT_LIMIT - 4) // leading))
        for start in range(0, max(len(labels), len(values)), per_piece):
            label_piece = labels[start : start + per_piece]
            value_piece = values[start : start + per_piece]
            height = max(_lines_height(label_piece, leading), _lines_height(value_piece, leading))

            def draw_fact(
                ink: Ink,
                top: float,
                labels: list[Line] = label_piece,
                values: list[Line] = value_piece,
            ) -> None:
                _draw_lines(ink, MARGIN_X, top, labels, leading)
                _draw_lines(ink, MARGIN_X + label_width + 10, top, values, leading)

            units.append(Unit(height=height + 4, draw=draw_fact))
    return units


def _quote_unit(
    block: dict[str, Any],
    *,
    colour: str = palette.INK,
    muted: str = palette.INK_MUTED,
    accent: str = palette.BRASS,
) -> list[Unit]:
    size = 14.0
    leading = size * 1.3
    width = CONTENT_WIDTH - 24
    label = Line(str(block["label"]), BOLD, 8.5, accent)
    body = [Line(t, ITALIC, size, colour) for t in wrap(f'"{block["text"]}"', ITALIC, size, width)]
    attribution = Line(str(block["attribution"]), FONT, 9, muted)
    pieces = _pieces(body, leading, 30)
    units: list[Unit] = []
    for index, piece in enumerate(pieces):
        first, last = index == 0, index == len(pieces) - 1
        head = 14 if first else 0
        height = head + _lines_height(piece, leading) + (16 if last else 4)

        def draw(
            ink: Ink,
            top: float,
            piece: list[Line] = piece,
            first: bool = first,
            last: bool = last,
            head: float = head,
            height: float = height,
        ) -> None:
            ink.rect(MARGIN_X, top, 3, height - 4, fill=accent)
            if first:
                _draw_lines(ink, MARGIN_X + 14, top, [label], 12)
            _draw_lines(ink, MARGIN_X + 14, top + head, piece, leading)
            if last:
                _draw_lines(
                    ink,
                    MARGIN_X + 14,
                    top + head + _lines_height(piece, leading) + 2,
                    [attribution],
                    12,
                )

        units.append(Unit(height=height, draw=draw))
    return units


def _callout_unit(
    block: dict[str, Any], *, colour: str = palette.INK, accent: str = palette.BRASS
) -> list[Unit]:
    size = 16.0
    leading = size * 1.25
    body = [
        Line(t, BOLD, size, colour)
        for t in wrap(str(block["text"]), BOLD, size, CONTENT_WIDTH - 14)
    ]
    label = Line(str(block["label"]), BOLD, 8.5, accent)
    units: list[Unit] = []
    for index, piece in enumerate(_pieces(body, leading, 17)):
        head = 13 if index == 0 else 0
        height = head + _lines_height(piece, leading) + 4

        def draw(
            ink: Ink,
            top: float,
            piece: list[Line] = piece,
            head: float = head,
            height: float = height,
        ) -> None:
            ink.rect(MARGIN_X, top, 3, height - 4, fill=accent)
            if head:
                _draw_lines(ink, MARGIN_X + 12, top, [label], 12)
            _draw_lines(ink, MARGIN_X + 12, top + head, piece, leading)

        units.append(Unit(height=height, draw=draw))
    return units


def _paragraph_unit(block: dict[str, Any], *, colour: str = palette.INK) -> list[Unit]:
    size = 10.5
    leading = size * 1.35
    lines = [
        Line(t, FONT, size, colour) for t in wrap(str(block["text"]), FONT, size, CONTENT_WIDTH)
    ]
    units: list[Unit] = []
    for piece in _pieces(lines, leading, 0):

        def draw(ink: Ink, top: float, piece: list[Line] = piece) -> None:
            _draw_lines(ink, MARGIN_X, top, piece, leading)

        units.append(Unit(height=_lines_height(piece, leading), draw=draw))
    return units


def _commands_unit(block: dict[str, Any]) -> list[Unit]:
    size = 10.0
    leading = size * 1.4
    units: list[Unit] = []
    if block.get("heading"):
        units.append(_heading_unit(str(block["heading"])))
    lines = [
        Line(t, MONO, size, palette.INK)
        for command in block["lines"]
        for t in wrap(str(command), MONO, size, CONTENT_WIDTH - 24)
    ]
    if not lines:
        lines = [Line("Nothing to run.", FONT, size, palette.INK_MUTED)]
    pieces = _pieces(lines, leading, 14)
    for index, piece in enumerate(pieces):
        box = _lines_height(piece, leading) + 14

        def draw(ink: Ink, top: float, piece: list[Line] = piece, box: float = box) -> None:
            ink.rect(MARGIN_X, top, CONTENT_WIDTH, box, fill=palette.PAPER_SHADE)
            _draw_lines(ink, MARGIN_X + 12, top + 7, piece, leading)

        units.append(Unit(height=box, draw=draw, keep_with_next=index == len(pieces) - 1))
    units.append(_caption_unit(str(block["note"])))
    return units


def _not_yet_unit(block: dict[str, Any]) -> list[Unit]:
    size = 10.0
    leading = size * 1.35
    width = CONTENT_WIDTH - 24
    lines = [Line("Not yet", BOLD, size, palette.INK, shape="unknown")]
    lines += [
        Line(t, FONT, size, palette.INK)
        for t in wrap(f"{block['what']}. Next step: {block['step']}.", FONT, size, width)
    ]
    if block.get("hint"):
        lines += [
            Line(t, MONO, size - 1, palette.INK_MUTED)
            for t in wrap(str(block["hint"]), MONO, size - 1, width)
        ]
    units: list[Unit] = []
    for piece in _pieces(lines, leading, 14):
        height = _lines_height(piece, leading) + 14

        def draw(ink: Ink, top: float, piece: list[Line] = piece, height: float = height) -> None:
            ink.rect(MARGIN_X, top, CONTENT_WIDTH, height, stroke=palette.INK_MUTED, dash=True)
            _draw_lines(ink, MARGIN_X + 12, top + 7, piece, leading)

        units.append(Unit(height=height, draw=draw))
    return units


def _diagram_unit(block: dict[str, Any]) -> Unit:
    layout_width = float(block.get("width") or 1.0) or 1.0
    layout_height = float(block.get("height") or 1.0) or 1.0
    maximum_height = 190.0
    scale = min(CONTENT_WIDTH / layout_width, maximum_height / layout_height, 1.0)
    drawn_height = layout_height * scale
    offset_x = MARGIN_X + (CONTENT_WIDTH - layout_width * scale) / 2
    description = [
        Line(t, ITALIC, 8.5, palette.INK_MUTED)
        for t in wrap(str(block["description"]), ITALIC, 8.5, CONTENT_WIDTH)
    ]

    def draw(ink: Ink, top: float) -> None:
        ink.rect(MARGIN_X, top, CONTENT_WIDTH, drawn_height, fill=palette.PAPER_SHADE)
        for edge in block["edges"]:
            x1 = offset_x + float(edge["x1"]) * scale
            y1 = top + float(edge["y1"]) * scale
            x2 = offset_x + float(edge["x2"]) * scale
            y2 = top + float(edge["y2"]) * scale
            ink.line(x1, y1, x2, y2, palette.INK, 1.1)
            direction = 1 if x2 >= x1 else -1
            ink.polygon(
                [(x2, y2), (x2 - 7 * direction, y2 - 3.5), (x2 - 7 * direction, y2 + 3.5)],
                fill=palette.INK,
                stroke=palette.INK,
            )
            if edge.get("label"):
                ink.text(
                    (x1 + x2) / 2 - text_width(str(edge["label"]), FONT, 7.5) / 2,
                    (y1 + y2) / 2 - 11,
                    str(edge["label"]),
                    FONT,
                    7.5,
                    palette.INK_MUTED,
                )
        for node in block["nodes"]:
            x = offset_x + float(node["x"]) * scale
            y = top + float(node["y"]) * scale
            width = 200 * scale
            height = 72 * scale
            ink.rect(x, y, width, height, fill=palette.PAPER, stroke=palette.INK)
            ink.rect(x, y, width, 2.5, fill=palette.BRASS)
            role = wrap(str(node["role"]), BOLD, 8.5, width - 10)[:3]
            _draw_lines(ink, x + 5, y + 6, [Line(t, BOLD, 8.5, palette.INK) for t in role], 10.5)
            component = node.get("component")
            if component:
                short = wrap(str(component), MONO, 6.5, width - 10)[:2]
                _draw_lines(
                    ink,
                    x + 5,
                    y + height - 8 - 8 * len(short),
                    [Line(t, MONO, 6.5, palette.INK_MUTED) for t in short],
                    8,
                )
        _draw_lines(ink, MARGIN_X, top + drawn_height + 4, description, 11)

    return Unit(height=drawn_height + 6 + _lines_height(description, 11), draw=draw)


def _chart_units(block: dict[str, Any], selected_label: str | None) -> list[Unit]:
    units: list[Unit] = []
    description = [
        Line(t, ITALIC, 8.5, palette.INK_MUTED)
        for t in wrap(str(block["description"]), ITALIC, 8.5, CONTENT_WIDTH)
    ]
    units.append(
        Unit(
            height=_lines_height(description, 11) + 2,
            draw=lambda ink, top: _draw_lines(ink, MARGIN_X, top, description, 11),
            keep_with_next=True,
        )
    )
    per_piece = max(1, int((UNIT_LIMIT - 21) // (BAR_HEIGHT + 4)))
    for whole in block["series"]:
        every_bar = whole["bars"]
        numbers = [
            float(n)
            for bar in every_bar
            for n in (
                bar["value"].get("lower"),
                bar["value"].get("upper"),
                bar["value"].get("value"),
            )
            if isinstance(n, (int, float))
        ]
        low = min([0.0, *numbers]) if numbers else 0.0
        high = max(numbers) if numbers else 1.0
        span = (high - low) or 1.0
        # Every piece of one series shares its scale, so bars stay comparable across pieces.
        for start in range(0, max(len(every_bar), 1), per_piece):
            bars = every_bar[start : start + per_piece]
            series = {**whole, "objective": whole["objective"] + (" (continued)" if start else "")}
            units.append(_series_unit(series, bars, low, span, selected_label))
    return units


def _series_unit(
    series: dict[str, Any],
    bars: list[dict[str, Any]],
    low: float,
    span: float,
    selected_label: str | None,
) -> Unit:
    label_width = 150.0
    value_width = 150.0
    track_x = MARGIN_X + label_width
    track_width = CONTENT_WIDTH - label_width - value_width - 10
    bar_height = BAR_HEIGHT
    height = 15 + len(bars) * (bar_height + 4) + 6

    def draw(
        ink: Ink,
        top: float,
        series: dict[str, Any] = series,
        bars: list[dict[str, Any]] = bars,
        low: float = low,
        span: float = span,
    ) -> None:
        ink.text(MARGIN_X, top, f"{series['objective']} ({series['unit']})", BOLD, 9, palette.INK)
        for index, bar in enumerate(bars):
            row_top = top + 15 + index * (bar_height + 4)
            value = bar["value"]
            ink.text(MARGIN_X + 8, row_top, str(bar["label"]), FONT, 8.5, palette.INK)
            ink.rect(track_x, row_top + 3, track_width, 3, fill=palette.PAPER_SHADE)
            lower = (
                value.get("lower")
                if isinstance(value.get("lower"), (int, float))
                else value.get("value")
            )
            upper = (
                value.get("upper")
                if isinstance(value.get("upper"), (int, float))
                else value.get("value")
            )
            if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
                x1 = track_x + (float(lower) - low) / span * track_width
                x2 = track_x + (float(upper) - low) / span * track_width
                colour = palette.BRASS if bar["label"] == selected_label else palette.INK_MUTED
                ink.rect(x1, row_top + 1, max(x2 - x1, 2.0), bar_height - 2, fill=colour)
            point = value.get("value")
            if isinstance(point, (int, float)):
                x = track_x + (float(point) - low) / span * track_width
                ink.rect(x - 1, row_top - 1, 2, bar_height + 2, fill=palette.INK)
            ink.text(
                track_x + track_width + 10,
                row_top,
                str(value.get("short") or value.get("text")),
                FONT,
                8.5,
                palette.INK,
            )

    return Unit(height=height, draw=draw)


def _note_unit(note: dict[str, Any]) -> Unit:
    size = 10.0
    leading = size * 1.35
    width = CONTENT_WIDTH - 24
    label = Line(f"{note['label']} · {note['model']}", BOLD, 8.5, palette.BRASS)
    body = [Line(t, FONT, size, palette.INK) for t in wrap(str(note["text"]), FONT, size, width)]
    height = 12 + _lines_height(body, leading) + 14

    def draw(ink: Ink, top: float) -> None:
        ink.rect(MARGIN_X, top, CONTENT_WIDTH, height, fill=palette.NOTE_GROUND)
        _draw_lines(ink, MARGIN_X + 12, top + 7, [label], 12)
        _draw_lines(ink, MARGIN_X + 12, top + 20, body, leading)

    return Unit(height=height, draw=draw)


def _block_units(
    block: dict[str, Any], *, cover: bool, selected_label: str | None = None
) -> list[Unit]:
    colour = palette.COVER_TEXT if cover else palette.INK
    muted = palette.COVER_MUTED if cover else palette.INK_MUTED
    accent = palette.BRASS_LIGHT if cover else palette.BRASS
    kind = block["kind"]
    if kind == "facts":
        return _facts_units(block, colour=colour, muted=muted)
    if kind == "table":
        return _table_units(block)
    if kind == "quote":
        return _quote_unit(block, colour=colour, muted=muted, accent=accent)
    if kind == "callout":
        return _callout_unit(block, colour=colour, accent=accent)
    if kind == "paragraph":
        return _paragraph_unit(block, colour=colour)
    if kind == "commands":
        return _commands_unit(block)
    if kind == "not_yet":
        return _not_yet_unit(block)
    if kind == "diagram":
        return [_diagram_unit(block)]
    if kind == "chart":
        return _chart_units(block, selected_label)
    return []


# ----- pages -----------------------------------------------------------------------------


@dataclass
class Page:
    section: dict[str, Any]
    continued: bool
    placed: list[tuple[float, Unit]] = field(default_factory=list)


def _header_height(
    section: dict[str, Any], continued: bool
) -> tuple[float, list[Line], list[Line]]:
    cover = section["id"] == "cover"
    title_size = 26.0 if cover else 21.0
    title = section["title"] + (" (continued)" if continued else "")
    title_lines = [
        Line(t, BOLD, title_size, palette.COVER_TEXT if cover else palette.INK)
        for t in wrap(title, BOLD, title_size, CONTENT_WIDTH - 90)
    ]
    subtitle_lines = (
        []
        if continued
        else [
            Line(t, FONT, 11, palette.COVER_MUTED if cover else palette.INK_MUTED)
            for t in wrap(str(section["subtitle"]), FONT, 11, CONTENT_WIDTH - 90)
        ]
    )
    if section.get("detail_in") and not continued:
        appendices = " and ".join(section["detail_in"])
        subtitle_lines.append(
            Line(
                f"Detail in appendix {appendices}.",
                FONT,
                9.5,
                palette.BRASS_LIGHT if cover else palette.BRASS,
            )
        )
    height = (
        TOP
        + _lines_height(title_lines, title_size * 1.15)
        + 6
        + _lines_height(subtitle_lines, 14)
        + 12
    )
    return height, title_lines, subtitle_lines


def _selected_label(document: dict[str, Any]) -> str | None:
    """The recommended option's label, as the cover's "Recommended" callout states it."""

    for block in document["sections"][0]["blocks"]:
        if block["kind"] == "callout" and block["label"] == "Recommended":
            return str(block["text"]).split(" (", 1)[0]
    return None


def paginate(document: dict[str, Any]) -> list[Page]:
    """Every section's blocks placed on 16:9 pages, continuing where a page is full."""

    pages: list[Page] = []
    selected_label = _selected_label(document)
    for section in document["sections"]:
        cover = section["id"] == "cover"
        units: list[Unit] = []
        if section.get("note"):
            units.append(_note_unit(section["note"]))
        for block in section["blocks"]:
            block_units = _block_units(block, cover=cover, selected_label=selected_label)
            if block_units:
                block_units[-1] = Unit(
                    height=block_units[-1].height + BLOCK_GAP,
                    draw=block_units[-1].draw,
                    keep_with_next=False,
                    repeat=block_units[-1].repeat,
                )
            units.extend(block_units)
        page = Page(section=section, continued=False)
        top = _header_height(section, False)[0]
        pages.append(page)
        index = 0
        while index < len(units):
            unit = units[index]
            group = [unit]
            follow = index
            while group[-1].keep_with_next and follow + 1 < len(units):
                follow += 1
                group.append(units[follow])
            needed = sum(item.height for item in group)
            if top + needed > PAGE_HEIGHT - CONTENT_BOTTOM and page.placed:
                page = Page(section=section, continued=True)
                pages.append(page)
                top = _header_height(section, True)[0]
                if unit.repeat is not None:
                    page.placed.append((top, unit.repeat))
                    top += unit.repeat.height
            if top + needed > PAGE_HEIGHT - CONTENT_BOTTOM and len(group) > 1:
                # Too tall to keep together even on a fresh page: let the group break.
                group, follow = [unit], index
            for item in group:
                page.placed.append((top, item))
                top += item.height
            index = follow + 1
    return pages


def _draw_page(ink: Ink, page: Page, number: int, total: int, footer: str) -> None:
    section = page.section
    cover = section["id"] == "cover"
    ground = palette.COVER if cover else palette.PAPER
    ink.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=ground)
    height, title_lines, subtitle_lines = _header_height(section, page.continued)
    title_size = title_lines[0].size if title_lines else 21.0
    _draw_lines(ink, MARGIN_X, TOP, title_lines, title_size * 1.15)
    _draw_lines(
        ink, MARGIN_X, TOP + _lines_height(title_lines, title_size * 1.15) + 6, subtitle_lines, 14
    )
    marker = section["number"] if section["kind"] == "main" else f"Appendix {section['number']}"
    accent = palette.BRASS_LIGHT if cover else palette.BRASS
    ink.text(
        PAGE_WIDTH - MARGIN_X - text_width(marker, BOLD, 10), TOP + 4, marker, BOLD, 10, accent
    )
    ink.line(MARGIN_X, height - 7, PAGE_WIDTH - MARGIN_X, height - 7, accent, 0.9)
    for top, unit in page.placed:
        unit.draw(ink, top)
    muted = palette.COVER_MUTED if cover else palette.INK_MUTED
    page_text = f"page {number} of {total}"
    page_width = text_width(page_text, FONT, 8)
    baseline = PAGE_HEIGHT - FOOTER_BASELINE
    ink.text(PAGE_WIDTH - MARGIN_X - page_width, baseline, page_text, FONT, 8, muted)
    ink.text(
        MARGIN_X, baseline, fit(footer, FONT, 8, CONTENT_WIDTH - page_width - 24), FONT, 8, muted
    )


def _pdf_date(timestamp: str) -> Callable[..., str]:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(UTC)
    fixed = instant.strftime("D:%Y%m%d%H%M%S+00'00'")
    return lambda *_parts: fixed


def render_pdf(document: dict[str, Any]) -> bytes:
    pages = paginate(document)
    cover = document["sections"][0]
    case_title = next(
        (
            item["value"].get("text")
            for block in cover["blocks"]
            if block["kind"] == "facts"
            for item in block["items"]
            if item["label"] == "Case"
        ),
        document["case_ref"]["id"],
    )
    footer = f"{case_title} · {str(document['generated_at'])[:10]}"
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), invariant=1, pageCompression=1)
    canvas.setDateFormatter(_pdf_date(str(document["generated_at"])))
    canvas.setTitle(pdf_text(cover["title"]))
    canvas.setAuthor(pdf_text(str(document["generated_by"])))
    canvas.setSubject(
        pdf_text(
            f"Architecture report for {document['case_ref']['id']} "
            f"at version {document['case_ref']['version']}"
        )
    )
    canvas.setCreator(f"OAK Community {RENDERER_NAME} {RENDERER_VERSION}")
    ink = Ink(canvas)
    for number, page in enumerate(pages, start=1):
        _draw_page(ink, page, number, len(pages), footer)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


class PdfReportRenderer:
    """`ReportRendererPort` for the PDF; the PPTX was deferred by the owner (Sprint 13)."""

    def identity(self) -> dict[str, Any]:
        return {
            "name": RENDERER_NAME,
            "version": RENDERER_VERSION,
            "libraries": {"reportlab": str(reportlab.Version)},
        }

    def formats(self) -> tuple[str, ...]:
        return (PDF_MEDIA_TYPE,)

    def render(self, document: dict[str, Any], media_type: str) -> bytes:
        if media_type != PDF_MEDIA_TYPE:
            raise OAKError("OAK-REPORT-RENDER", "this renderer writes PDF only")
        try:
            content = render_pdf(document)
        except (KeyError, TypeError, ValueError) as error:
            raise OAKError("OAK-REPORT-RENDER", "the report document could not be drawn") from error
        if len(content) > MAXIMUM_RENDERING_BYTES:
            raise OAKError("OAK-REPORT-SIZE", "the rendered report exceeds 4 MiB")
        return content
