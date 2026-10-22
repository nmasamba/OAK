# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-004: recording the architecture report beside the case.

Recording writes the report document and its PDF, revises the case at its own status and
appends one `report_recorded` event. It is idempotent, refuses a stale version, refuses a
case that has no selection yet and names the step that is missing, and in a model mode
keeps only the notes that pass OAK's checks. When nothing survives, it commits nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.models.fake_narrator import FakeReportNarrator
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.report import PdfReportRenderer
from oak.application import CommandContext, ReportService
from oak.bootstrap import create_candidate_planning_service
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError, content_digest
from oak.domain.report import PDF_MEDIA_TYPE, REPORT_EXTENSION
from tests.report_pdf_support import parse_pdf
from tests.report_support import (
    build_case_with_candidates,
    build_reference_case,
    build_researched_case,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")
RECORDED_AT = "2026-08-18T13:00:00Z"
pytestmark = pytest.mark.integration

GOOD_NOTE = {"section": "7", "text": "The owner chose Balanced over three alternatives."}
INVENTED_NUMBER = {"section": "8", "text": "It saves 99 USD a month."}
APPENDIX = {"section": "A", "text": "Notes belong on main slides only."}
AUTHORITY = {"section": "11", "text": "This design is approved for production."}
EDITION = {"section": "4", "text": "The enterprise option is the strongest."}


def _context(key: str, version: str | None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=RECORDED_AT,
    )


def _service(workspace: Path, *, narrator: Any = None, renderer: Any = "pdf") -> ReportService:
    return ReportService(
        FileWorkspaceRepository(workspace, REGISTRY),
        REGISTRY,
        PdfReportRenderer() if renderer == "pdf" else renderer,
        oak_version="0.9.0",
        narrator_factory=(lambda mode: narrator) if narrator is not None else None,
    )


def _manifest(workspace: Path) -> dict[str, Any]:
    return json.loads((workspace / ".oak" / "manifest.json").read_text(encoding="utf-8"))


def _read(workspace: Path, reference: dict[str, Any]) -> bytes:
    return FileWorkspaceRepository(workspace, REGISTRY).read_artifact(
        ArtifactReference.from_document(reference)
    )


def test_recording_stores_the_report_and_changes_no_status(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    result = _service(workspace).record(_context("report-record-000001", "0.1.7"))

    assert not result.duplicate
    assert (result.case["version"], result.case["status"]) == ("0.1.8", "bundle_compiled")
    entry = result.case["extensions"][REPORT_EXTENSION]
    assert entry == result.report
    assert entry["made_from_case_version"] == "0.1.7"
    assert entry["recorded_case_version"] == "0.1.8"
    assert entry["narrative_ref"] is None and entry["narrative_mode"] == "deterministic"
    document = json.loads(_read(workspace, entry["document_ref"]))
    assert document == result.document
    assert document["case_ref"]["version"] == "0.1.7"
    assert document["generated_at"] == RECORDED_AT
    assert document["renderer"]["libraries"] == {
        "reportlab": PdfReportRenderer().identity()["libraries"]["reportlab"]
    }
    pdf = _read(workspace, entry["pdf_ref"])
    assert entry["pdf_ref"]["media_type"] == PDF_MEDIA_TYPE
    assert content_digest(pdf) == entry["pdf_ref"]["digest"]
    assert (
        parse_pdf(pdf)
        .page_texts[0]
        .startswith("Cited answers over public technical manuals: build the")
    )
    manifest = _manifest(workspace)
    last = manifest["audit_events"][-1]
    event = json.loads(_read(workspace, last))
    assert event["event_type"] == "report_recorded"
    assert {ref["id"] for ref in event["extensions"]["oak.community/artifact_refs"]} == {
        "report.public-manual-qa.from-0.1.7",
        "report.public-manual-qa.from-0.1.7.pdf",
    }
    kinds = {item["id"]: item["kind"] for item in manifest["artifact_index"]}
    assert kinds["report.public-manual-qa.from-0.1.7"] == "architecture_report"
    assert kinds["report.public-manual-qa.from-0.1.7.pdf"] == "report_rendering"


def test_a_retry_returns_the_same_report_and_appends_nothing(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    first = _service(workspace).record(_context("report-record-000002", "0.1.7"))
    events = len(_manifest(workspace)["audit_events"])
    again = _service(workspace).record(_context("report-record-000002", "0.1.7"))
    assert again.duplicate
    assert again.report == first.report
    assert again.document == first.document
    assert len(_manifest(workspace)["audit_events"]) == events


def test_a_stale_expected_version_is_refused(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    with pytest.raises(OAKError) as refused:
        _service(workspace).record(_context("report-record-000003", "0.1.6"))
    assert refused.value.code == "OAK-EXPECTED-VERSION"


def test_a_case_without_a_selection_is_too_early_and_names_the_step(tmp_path: Path) -> None:
    workspace = build_case_with_candidates(tmp_path)
    before = _manifest(workspace)
    with pytest.raises(OAKError) as refused:
        _service(workspace).record(_context("report-record-000004", "0.1.3"))
    assert refused.value.code == "OAK-REPORT-STATE"
    assert "select a candidate" in refused.value.message
    assert _manifest(workspace) == before


def test_a_report_goes_stale_when_the_case_moves_on_and_can_be_recorded_again(
    tmp_path: Path,
) -> None:
    workspace = build_reference_case(tmp_path, "candidate_selected")
    early = _service(workspace).record(_context("report-record-000005", "0.1.5"))
    assert early.case["status"] == "candidate_selected"
    governance = next(s for s in early.document["sections"] if s["id"] == "governance")
    assert governance["state"] == "partial"
    planning = create_candidate_planning_service(workspace)
    planning.assure("candidate-03", _context("report-assure-000005", "0.1.6"))
    case = FileWorkspaceRepository(workspace, REGISTRY).current_case()
    assert case is not None and case["version"] == "0.1.7"
    carried = case["extensions"][REPORT_EXTENSION]
    assert carried["recorded_case_version"] == "0.1.6"  # stale: the case is at 0.1.7
    later = _service(workspace).record(_context("report-record-000006", "0.1.7"))
    assert later.report["made_from_case_version"] == "0.1.7"
    assert later.report["recorded_case_version"] == "0.1.8"
    assert later.report["document_ref"]["id"] == "report.public-manual-qa.from-0.1.7"


def test_a_model_mode_keeps_only_notes_that_pass_the_checks(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    narrator = FakeReportNarrator([GOOD_NOTE, INVENTED_NUMBER, APPENDIX, AUTHORITY, EDITION])
    result = _service(workspace, narrator=narrator).record(
        _context("report-record-000007", "0.1.7"), narrative="online"
    )
    entry = result.report
    assert entry["narrative_mode"] == "online"
    narrative = json.loads(_read(workspace, entry["narrative_ref"]))
    assert narrative["notes"] == [GOOD_NOTE]
    assert narrative["extensions"]["oak.community/model"]["dropped_notes"] == 4
    noted = [s for s in result.document["sections"] if s["note"] is not None]
    assert [s["number"] for s in noted] == ["7"]
    assert noted[0]["note"]["label"] == "Proposed by model"
    assert noted[0]["note"]["model"] == "example-org/example-model via example-route"
    # The model was shown the main slides' words and nothing else.
    shown = json.dumps(narrator.calls[0])
    assert "sha256:" not in shown and "Every input record, by digest" not in shown


def test_a_model_mode_with_no_surviving_note_commits_nothing(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    before = _manifest(workspace)
    narrator = FakeReportNarrator([INVENTED_NUMBER, AUTHORITY])
    with pytest.raises(OAKError) as refused:
        _service(workspace, narrator=narrator).record(
            _context("report-record-000008", "0.1.7"), narrative="local"
        )
    assert refused.value.code == "OAK-NARRATIVE-EMPTY"
    assert _manifest(workspace) == before


@pytest.mark.parametrize(
    ("narrator", "code"),
    (
        (None, "OAK-MODEL-NOT-CONFIGURED"),
        (FakeReportNarrator(unavailable=True), "OAK-NARRATIVE-UNAVAILABLE"),
    ),
)
def test_a_model_mode_that_cannot_run_commits_nothing(
    tmp_path: Path, narrator: Any, code: str
) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    before = _manifest(workspace)
    with pytest.raises(OAKError) as refused:
        _service(workspace, narrator=narrator).record(
            _context("report-record-000009", "0.1.7"), narrative="online"
        )
    assert refused.value.code == code
    assert _manifest(workspace) == before


def test_an_unknown_narrative_mode_and_a_missing_renderer_are_refused(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    with pytest.raises(OAKError) as refused:
        _service(workspace).record(_context("report-record-000010", "0.1.7"), narrative="cloud")
    assert refused.value.code == "OAK-NARRATIVE-MODE"
    with pytest.raises(OAKError) as refused:
        _service(workspace, renderer=None).record(_context("report-record-000011", "0.1.7"))
    assert refused.value.code == "OAK-REPORT-RENDER"


def test_an_exported_workspace_with_a_report_imports_and_keeps_it(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path / "source", "bundle_compiled")
    recorded = _service(workspace).record(_context("report-record-000012", "0.1.7"))
    exported = tmp_path / "exported"
    FileWorkspaceRepository(workspace, REGISTRY).export_to(exported)
    target = tmp_path / "imported"
    target.mkdir()
    imported = FileWorkspaceRepository(target, REGISTRY)
    imported.import_from(exported)
    case = imported.current_case()
    assert case is not None
    assert case["extensions"][REPORT_EXTENSION] == recorded.report
    pdf = imported.read_artifact(ArtifactReference.from_document(recorded.report["pdf_ref"]))
    assert content_digest(pdf) == recorded.report["pdf_ref"]["digest"]


def test_recording_the_acceptance_case_stores_twenty_one_sections_and_renders(
    tmp_path: Path,
) -> None:
    """OAK-S14-006: a report records, validates and renders for the researched case at six
    options; appendix G is its last section and the PDF carries it."""

    workspace = build_researched_case(tmp_path, "candidate_selected")
    result = _service(workspace).record(_context("report-record-research-01", "0.1.7"))

    assert not result.duplicate
    assert (result.case["version"], result.case["status"]) == ("0.1.8", "candidate_selected")
    document = json.loads(_read(workspace, result.report["document_ref"]))
    REGISTRY.validate("architecture-report.schema.json", document)
    assert [section["number"] for section in document["sections"]][-2:] == ["F", "G"]
    assert len(document["sections"]) == 21
    options = next(section for section in document["sections"] if section["id"] == "options")
    table = next(block for block in options["blocks"] if block["kind"] == "table")
    assert len(table["rows"]) == 6
    kinds = {item["kind"] for item in document["inputs"]}
    assert {"research_snapshot", "research_review", "component_manifest"} <= kinds
    pdf = _read(workspace, result.report["pdf_ref"])
    assert content_digest(pdf) == result.report["pdf_ref"]["digest"]
    text = " ".join(parse_pdf(pdf).page_texts)
    assert "What research found, and" in text and "Balanced, new" in text
