# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-003: the PDF rendering is byte-stable, well formed, honest about its fonts, and small.

The golden report document is drawn and read back with the standard library. Byte
stability is proved across processes, not just across calls, because a renderer that
reads the clock, the hash seed or the process environment would only differ between runs.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from oak.adapters.report import PdfReportRenderer, pdf
from oak.adapters.report.pdf import (
    CONTENT_BOTTOM,
    FONT_DIRECTORY,
    FONT_FILES,
    MONO,
    PAGE_HEIGHT,
    REPLACEMENT,
    paginate,
    pdf_text,
    wrap,
)
from oak.domain import OAKError
from oak.domain.report import MAXIMUM_RENDERING_BYTES, PDF_MEDIA_TYPE
from tests.report_pdf_support import parse_pdf
from tests.report_support import GOLDEN_REPORT, GOLDEN_RESEARCH_REPORT

ROOT = Path(__file__).resolve().parents[2]
VENDORED_FONTS = {"IBMPlexSans", "IBMPlexSans-Bold", "IBMPlexSans-Italic", "IBMPlexMono"}
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


# reportlab reads `RL_<setting>` variables when it is imported, and each of these would
# change the bytes if the renderer did not pin the setting itself (OAK-V1-015).
RL_SETTINGS = {
    "RL_useA85": "0",
    "RL_pageCompression": "0",
    "RL_invariant": "0",
    "RL_pdfComments": "1",
    "RL_pdfMultiLine": "1",
    "RL_documentLang": "fr-FR",
    "RL_canvas_basefontname": "Courier",
    "RL_defaultEncoding": "MacRomanEncoding",
    "RL_ttfAsciiReadable": "0",
}


def test_two_processes_draw_the_same_bytes(rendered: bytes, tmp_path: Path) -> None:
    here = hashlib.sha256(rendered).hexdigest()
    # reportlab also reads `~/.reportlab_settings`, and seeds the document ID from
    # SOURCE_DATE_EPOCH even in invariant mode (failing on a value that is not a number).
    (tmp_path / ".reportlab_settings").write_text("ttfAsciiReadable = 0\n", encoding="utf-8")
    digests = set()
    for seed, settings in (
        ("1", {}),
        ("2", {**RL_SETTINGS, "SOURCE_DATE_EPOCH": "1700000000"}),
        ("3", {"HOME": str(tmp_path), "SOURCE_DATE_EPOCH": "now"}),
    ):
        environment = {
            **{
                key: value
                for key, value in os.environ.items()
                if not key.startswith("RL_") and key != "SOURCE_DATE_EPOCH"
            },
            "PYTHONHASHSEED": seed,
            "TZ": f"Etc/GMT+{seed}",
            **settings,
        }
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


def test_only_the_vendored_fonts_are_named_each_embedded_as_a_subset(rendered: bytes) -> None:
    """OAK-V1-026 (RR-046): no standard font, so no reader substitutes its own."""

    parsed = parse_pdf(rendered)
    assert parsed.fonts == VENDORED_FONTS
    assert rendered.count(b"/FontFile2") == len(re.findall(rb"/BaseFont /[A-Z]{6}\+", rendered))
    assert b"/ToUnicode" in rendered
    assert b"Helvetica" not in rendered and b"Courier" not in rendered
    assert b"oak-report-renderer 1.0.0, IBM Plex)" in parse_pdf(rendered).info


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
    for malformed in ({"sections": [{"blocks": []}]}, {**_golden(), "sections": []}):
        with pytest.raises(OAKError) as refused:
            PdfReportRenderer().render(malformed, PDF_MEDIA_TYPE)
        assert refused.value.code == "OAK-REPORT-RENDER"


def test_concurrent_renderings_draw_the_bytes_one_rendering_draws_alone() -> None:
    """reportlab's font objects are shared by the process; two saves at once used to read
    each other's glyphs (a different subset, a KeyError, or an uncaught IndexError)."""

    composites = "".join(
        chr(point)
        for point in range(0xC0, 0x2000)
        if point in pdf.coverage(pdf.FONT) and len(chr(point).encode()) > 1
    )
    document = _golden()
    document["sections"][0]["subtitle"] = composites[:600]
    alone = PdfReportRenderer().render(document, PDF_MEDIA_TYPE)
    results: list[bytes | BaseException] = []

    def render() -> None:
        for _ in range(3):
            try:
                results.append(PdfReportRenderer().render(document, PDF_MEDIA_TYPE))
            except BaseException as error:
                results.append(error)

    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    try:
        threads = [threading.Thread(target=render) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert len(results) == 18
    assert all(result == alone for result in results)


def test_a_different_font_under_a_report_fonts_name_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reportlab keeps the first font registered under a name, so the pin is checked.

    The impostor is built from the same file so that, unchecked, it would draw without
    error: only the check can refuse it.
    """

    impostor = TTFont(pdf.FONT, io.BytesIO(pdf.font_bytes(pdf.FONT)))
    monkeypatch.setitem(pdfmetrics._fonts, pdf.FONT, impostor)
    with pytest.raises(OAKError) as refused:
        PdfReportRenderer().render(_golden(), PDF_MEDIA_TYPE)
    assert refused.value.code == "OAK-REPORT-RENDER"


def test_a_report_is_laid_out_without_rendering_one_first() -> None:
    """Measuring uses the pinned fonts directly, not reportlab's registry."""

    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from oak.adapters.report.pdf import paginate; "
            "print(len(paginate(json.load(open(sys.argv[1])))))",
            str(GOLDEN_REPORT),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    assert int(run.stdout) == len(paginate(_golden()))


def test_latin_greek_and_cyrillic_print_and_anything_else_is_a_visible_replacement() -> None:
    """OAK-V1-026 (RR-046): never `?`, never dropped; the JSON report keeps every character."""

    assert pdf_text("Café · 36 USD — “quoted” …") == "Café · 36 USD — “quoted” …"
    # As written where the font has the glyph, never folded to another character.
    assert pdf_text("10⁵ req/s in 4 m² ½ ™ H₂O ﬁle") == "10⁵ req/s in 4 m² ½ ™ H₂O ﬁle"
    assert pdf_text("12 µs", MONO) == "12 µs"
    # A compatibility character the font lacks prints as its plain form.
    assert pdf_text("\uff2f\uff21\uff2b") == "OAK"
    assert pdf_text("Ελληνικά Кириллица Łódź") == "Ελληνικά Кириллица Łódź"
    assert pdf_text("数据 report") == f"{REPLACEMENT}{REPLACEMENT} report"
    # Plex Mono has Cyrillic but no Greek.
    assert pdf_text("Кириллица \u03b1", MONO) == f"Кириллица {REPLACEMENT}"
    assert pdf_text("tab\tline\nbreak\x07") == f"tab line break{REPLACEMENT}"
    document = _golden()
    document["sections"][0]["title"] = "数据 Ελληνικά Кириллица report"
    text = parse_pdf(PdfReportRenderer().render(document, PDF_MEDIA_TYPE)).page_texts[0]
    assert f"{REPLACEMENT}{REPLACEMENT} Ελληνικά Кириллица report" in text


def test_a_vendored_font_that_does_not_match_its_pin_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in FONT_FILES.values():
        (tmp_path / name[0]).write_bytes((FONT_DIRECTORY / name[0]).read_bytes())
    tampered = tmp_path / FONT_FILES[MONO][0]
    tampered.write_bytes(tampered.read_bytes() + b"\0")
    monkeypatch.setattr(pdf, "FONT_DIRECTORY", tmp_path)
    _forget_fonts()
    try:
        with pytest.raises(OAKError) as refused:
            PdfReportRenderer().render(_golden(), PDF_MEDIA_TYPE)
        assert refused.value.code == "OAK-REPORT-RENDER"
    finally:
        _forget_fonts()


def _forget_fonts() -> None:
    """Drop the built fonts and reportlab's registration of them, as a fresh process has."""

    for name in FONT_FILES:
        registered = pdfmetrics._fonts.pop(name, None)
        if registered is not None:
            pdfmetrics._dynFaceNames.pop(registered.face.name, None)
    pdf.font_bytes.cache_clear()
    pdf.vendored_font.cache_clear()
    pdf.coverage.cache_clear()


def test_the_vendored_fonts_ship_with_their_licence() -> None:
    licence = (FONT_DIRECTORY / "OFL-1.1-IBM-Plex.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License, Version 1.1" in licence
    assert {path.name for path in FONT_DIRECTORY.iterdir()} == {
        *(file_name for file_name, _ in FONT_FILES.values()),
        "OFL-1.1-IBM-Plex.txt",
    }


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
    measure = pdf.measure

    def counting(text: str, font: str, size: float) -> float:
        nonlocal calls
        calls += 1
        return measure(text, font, size)

    monkeypatch.setattr(pdf, "measure", counting)
    word = "x" * 12000
    lines = wrap(word, pdf.FONT, 10, 300)
    assert "".join(lines) == word
    assert all(measure(line, pdf.FONT, 10) <= 300 for line in lines)
    assert calls <= len(word) + 2
    calls = 0
    sentence = "Because the brief says so. " * 444
    lines = wrap(sentence, pdf.FONT, 10, 300)
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


# ----- the acceptance case (OAK-S14-006, ADR-0018) -----------------------------------------


def _research_golden() -> dict[str, Any]:
    return json.loads(GOLDEN_RESEARCH_REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered_research() -> bytes:
    return PdfReportRenderer().render(_research_golden(), PDF_MEDIA_TYPE)


def test_the_acceptance_report_renders_with_appendix_g_on_its_pages(
    rendered_research: bytes,
) -> None:
    parsed = parse_pdf(rendered_research)
    text = " ".join(parsed.page_texts)
    golden = _research_golden()
    assert golden["sections"][-1]["number"] == "G"
    for section in golden["sections"]:
        first_words = " ".join(section["title"].split()[:4])
        assert first_words in text, section["title"]
    assert "Balanced, new" in text
    assert "Claimed by release notes" in text
    assert len(parsed.pages) == len(paginate(golden))
    assert parsed.fonts == VENDORED_FONTS
    assert len(rendered_research) <= MAXIMUM_RENDERING_BYTES


def test_the_acceptance_pdf_is_byte_stable(rendered_research: bytes) -> None:
    assert PdfReportRenderer().render(_research_golden(), PDF_MEDIA_TYPE) == rendered_research


def test_a_long_component_identifier_ends_in_an_ellipsis_not_a_cut() -> None:
    document = _golden()
    architecture = next(s for s in document["sections"] if s["id"] == "architecture")
    diagram = next(b for b in architecture["blocks"] if b["kind"] == "diagram")
    long_name = "component.research.hub.some-namespace." + "x" * 90 + ".run-1"
    diagram["nodes"][0]["component"] = long_name
    rendered = PdfReportRenderer().render(document, PDF_MEDIA_TYPE)
    text = " ".join(parse_pdf(rendered).page_texts)
    # A fitted line ends in three full stops (`ELLIPSIS`), and the identifier is never cut
    # mid-word.
    assert re.search(r"x{8,}\.\.\.", text)
    assert long_name not in text
