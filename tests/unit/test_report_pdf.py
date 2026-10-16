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

from oak.adapters.report import PdfReportRenderer
from oak.adapters.report.pdf import paginate, pdf_text
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


def test_the_renderer_draws_only_palette_colours() -> None:
    source = (ROOT / "src/oak/adapters/report/pdf.py").read_text(encoding="utf-8")
    assert "#" not in "".join(
        line.split("#", 1)[1] if line.lstrip().startswith("#") else ""
        for line in source.splitlines()
        if 'HexColor("#' in line
    )
    assert 'HexColor("#' not in source
