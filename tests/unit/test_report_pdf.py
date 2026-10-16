# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-003: the PDF rendering is byte-stable, well formed, honest about its fonts, and small.

The golden report document is drawn and read back with the standard library. Byte
stability is proved across processes, not just across calls, because a renderer that
reads the clock, the hash seed or the process environment would only differ between runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.report import PdfReportRenderer, pdf
from oak.adapters.report.pdf import CONTENT_BOTTOM, PAGE_HEIGHT, paginate, pdf_text, wrap
from oak.domain import OAKError
from oak.domain.report import MAXIMUM_RENDERING_BYTES, PDF_MEDIA_TYPE
from tests.report_pdf_support import parse_pdf
from tests.report_support import GOLDEN_REPORT

ROOT = Path(__file__).resolve().parents[2]
STANDARD_FONTS = {"Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Courier"}
RENDER = (
    "import hashlib, json, sys; from oak.adapters.report import PdfReportRenderer; "
    "d = json.load(open(sys.argv[1])); "
    "print(hashlib.sha256(PdfReportRenderer().render(d, 'application/pdf')).hexdigest())"
)


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN_REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered() -> bytes:
    return PdfReportRenderer().render(_golden(), PDF_MEDIA_TYPE)


def test_two_processes_draw_the_same_bytes(rendered: bytes) -> None:
    here = hashlib.sha256(rendered).hexdigest()
    digests = set()
    for seed in ("1", "2"):
        environment = {**os.environ, "PYTHONHASHSEED": seed, "TZ": f"Etc/GMT+{seed}"}
        run = subprocess.run(
            [sys.executable, "-c", RENDER, str(GOLDEN_REPORT)],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
            env=environment,
        )
        digests.add(run.stdout.strip())
    assert digests == {here}


def test_the_pdf_reads_back_with_every_page_and_its_footer(rendered: bytes) -> None:
    parsed = parse_pdf(rendered)
    expected_pages = len(paginate(_golden()))
    assert len(parsed.pages) == expected_pages
    for number, text in enumerate(parsed.page_texts, start=1):
        assert f"page {number} of {expected_pages}" in text
        assert "Cited answers over public technical manuals" in text
    assert "build the Balanced design" in parsed.page_texts[0]
    assert "Recommended" in parsed.page_texts[0]


def test_every_section_title_is_on_a_page(rendered: bytes) -> None:
    text = " ".join(parse_pdf(rendered).page_texts)
    for section in _golden()["sections"]:
        first_words = " ".join(section["title"].split()[:4])
        assert first_words in text, section["title"]


def test_the_document_dates_are_the_reports_own(rendered: bytes) -> None:
    info = parse_pdf(rendered).info
    assert b"/CreationDate (D:20260818120000+00'00')" in info
    assert b"/ModDate (D:20260818120000+00'00')" in info
    assert b"/Author (local-user)" in info


def test_only_standard_fonts_are_named_and_none_is_embedded(rendered: bytes) -> None:
    parsed = parse_pdf(rendered)
    assert parsed.fonts <= STANDARD_FONTS
    assert b"/FontFile" not in rendered


def test_the_reference_pdf_is_well_under_four_mebibytes(rendered: bytes) -> None:
    assert len(rendered) <= MAXIMUM_RENDERING_BYTES
    assert len(rendered) < 512 * 1024


def test_the_renderer_names_itself_and_writes_pdf_only() -> None:
    renderer = PdfReportRenderer()
    identity = renderer.identity()
    assert identity["name"] == "oak-report-renderer"
    assert set(identity["libraries"]) == {"reportlab"}
    assert renderer.formats() == (PDF_MEDIA_TYPE,)
    with pytest.raises(OAKError) as refused:
        renderer.render(_golden(), "application/vnd.ms-powerpoint")
    assert refused.value.code == "OAK-REPORT-RENDER"


def test_an_oversized_rendering_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from oak.adapters.report import pdf

    monkeypatch.setattr(
        pdf, "render_pdf", lambda document: b"%PDF-" + b"0" * MAXIMUM_RENDERING_BYTES
    )
    with pytest.raises(OAKError) as refused:
        PdfReportRenderer().render(_golden(), PDF_MEDIA_TYPE)
    assert refused.value.code == "OAK-REPORT-SIZE"


def test_a_malformed_document_is_a_render_error_not_a_crash() -> None:
    with pytest.raises(OAKError) as refused:
        PdfReportRenderer().render({"sections": [{"blocks": []}]}, PDF_MEDIA_TYPE)
    assert refused.value.code == "OAK-REPORT-RENDER"


def test_characters_outside_the_standard_fonts_print_as_question_marks() -> None:
    # Normalised first (NFKC), so an ellipsis becomes three full stops; Windows-1252
    # punctuation such as the em dash and curly quotes survives.
    assert pdf_text("Café · 36 USD — “quoted” …") == "Café · 36 USD — “quoted” ..."
    assert pdf_text("数据 → ≤ ✓") == "?? ? ? ?"
    document = _golden()
    document["sections"][0]["title"] = "数据 report"
    text = parse_pdf(PdfReportRenderer().render(document, PDF_MEDIA_TYPE)).page_texts[0]
    assert "?? report" in text


def test_long_tables_continue_with_their_header_repeated() -> None:
    document = _golden()
    section = next(item for item in document["sections"] if item["id"] == "appendix-record")
    table = section["blocks"][0]
    table["rows"] = table["rows"] * 6
    pages = [page for page in paginate(document) if page.section["id"] == "appendix-record"]
    assert len(pages) >= 3
    assert all(page.continued for page in pages[1:])
    rendered = PdfReportRenderer().render(document, PDF_MEDIA_TYPE)
    texts = parse_pdf(rendered).page_texts
    continued = [text for text in texts if "Every input record, by digest (continued)" in text]
    assert continued and all("Identifier" in text for text in continued)


def test_no_unit_runs_off_its_page_however_long_the_record_text() -> None:
    document = _golden()
    for section in document["sections"]:
        for block in section["blocks"]:
            if block["kind"] in {"quote", "callout", "paragraph"}:
                block["text"] = "Because the brief says so. " * 444
            elif block["kind"] == "table":
                for row in block["rows"][:2]:
                    for cell in row["cells"]:
                        if cell["type"] == "text":
                            cell["text"] = "A long problem statement. " * 153
            elif block["kind"] == "facts":
                for item in block["items"]:
                    if item["value"]["type"] == "text":
                        item["value"]["text"] = "word " * 800
    assert len("Because the brief says so. " * 444) <= 12000
    pages = paginate(document)
    overflow = [
        (page.section["id"], round(top + unit.height))
        for page in pages
        for top, unit in page.placed
        if top + unit.height > PAGE_HEIGHT - CONTENT_BOTTOM
    ]
    assert overflow == []
    texts = parse_pdf(PdfReportRenderer().render(document, PDF_MEDIA_TYPE)).page_texts
    assert len(texts) == len(pages)


def test_a_long_case_title_is_shortened_in_the_footer_and_the_page_count_kept() -> None:
    document = _golden()
    cover = document["sections"][0]
    facts = next(block for block in cover["blocks"] if block["kind"] == "facts")
    case = next(item for item in facts["items"] if item["label"] == "Case")
    case["value"]["text"] = "A very long case title " * 12
    texts = parse_pdf(PdfReportRenderer().render(document, PDF_MEDIA_TYPE)).page_texts
    assert all(f"page {number} of {len(texts)}" in text for number, text in enumerate(texts, 1))
    assert all("..." in text for text in texts)


def test_wrapping_measures_each_character_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    measure = pdf.stringWidth

    def counting(text: str, font: str, size: float) -> float:
        nonlocal calls
        calls += 1
        return float(measure(text, font, size))

    monkeypatch.setattr(pdf, "stringWidth", counting)
    word = "x" * 12000
    lines = wrap(word, "Helvetica", 10, 300)
    assert "".join(lines) == word
    assert all(measure(line, "Helvetica", 10) <= 300 for line in lines)
    assert calls <= len(word) + 2
    calls = 0
    sentence = "Because the brief says so. " * 444
    lines = wrap(sentence, "Helvetica", 10, 300)
    assert " ".join(lines).split() == sentence.split()
    assert calls <= len(sentence.split(" ")) + 2


def test_the_renderer_draws_only_palette_colours() -> None:
    source = (ROOT / "src/oak/adapters/report/pdf.py").read_text(encoding="utf-8")
    assert "#" not in "".join(
        line.split("#", 1)[1] if line.lstrip().startswith("#") else ""
        for line in source.splitlines()
        if 'HexColor("#' in line
    )
    assert 'HexColor("#' not in source
