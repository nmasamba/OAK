# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-002: the architecture report's contract, before anything composes one.

A report is recorded beside the case and authorizes nothing, so its contract is mostly
about what it may not do: it adds no lifecycle transition, its renderings are accepted
only as the two file formats they claim to be, and the libraries that draw them stay
inside one adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oak.adapters.persistence.file_workspace import (
    JSON_MEDIA_KIND,
    KIND_SCHEMA,
    OPAQUE_KINDS,
    validate_opaque_artifact,
)
from oak.contracts import ContractValidationError, SchemaRegistry, load_yaml_document
from oak.domain import Artifact, DesignCase, DesignCaseStatus, OAKError
from oak.domain.design_case import ALLOWED_TRANSITIONS
from oak.domain.report import (
    NARRATIVE_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    PPTX_MEDIA_TYPE,
    RENDERING_KIND,
    REPORT_MEDIA_TYPE,
)
from tools.check_boundaries import check

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")
RECORDABLE = (
    DesignCaseStatus.CANDIDATE_SELECTED,
    DesignCaseStatus.ASSURANCE_PLANNED,
    DesignCaseStatus.BUNDLE_COMPILED,
    DesignCaseStatus.DEPLOYMENT_APPROVED,
    DesignCaseStatus.DEPLOYED,
    DesignCaseStatus.OBSERVING,
)


def _manifest_kinds() -> set[str]:
    schema = json.loads((ROOT / "schemas/workspace-manifest.schema.json").read_text())
    entry = schema["$defs"]["indexedArtifact"]
    return set(entry["properties"]["kind"]["enum"])


def test_each_report_kind_is_registered_in_every_place_a_kind_must_be() -> None:
    assert KIND_SCHEMA["architecture_report"] == "architecture-report.schema.json"
    assert KIND_SCHEMA["report_narrative"] == "report-narrative.schema.json"
    assert JSON_MEDIA_KIND[REPORT_MEDIA_TYPE] == "architecture_report"
    assert JSON_MEDIA_KIND[NARRATIVE_MEDIA_TYPE] == "report_narrative"
    assert RENDERING_KIND in OPAQUE_KINDS and RENDERING_KIND not in KIND_SCHEMA
    assert {"architecture_report", "report_narrative", RENDERING_KIND} <= _manifest_kinds()


def test_report_recorded_is_an_audit_event_type() -> None:
    event = load_yaml_document((ROOT / "examples/example-audit-event.yaml").read_text())
    REGISTRY.validate("audit-event.schema.json", {**event, "event_type": "report_recorded"})


@pytest.mark.parametrize(
    ("media_type", "content"),
    ((PPTX_MEDIA_TYPE, b"PK\x03\x04rest-of-package"), (PDF_MEDIA_TYPE, b"%PDF-1.4\n...")),
)
def test_a_rendering_is_accepted_only_as_the_format_it_claims(
    media_type: str, content: bytes
) -> None:
    validate_opaque_artifact(
        Artifact(
            id="report.x.pdf",
            version="0.1.0",
            kind=RENDERING_KIND,
            media_type=media_type,
            content=content,
        )
    )
    swapped = PDF_MEDIA_TYPE if media_type == PPTX_MEDIA_TYPE else PPTX_MEDIA_TYPE
    for wrong_type, wrong_content in (
        (swapped, content),
        ("application/json", content),
        (media_type, b'{"looks": "like json"}'),
    ):
        with pytest.raises(OAKError) as refused:
            validate_opaque_artifact(
                Artifact(
                    id="report.x.pdf",
                    version="0.1.0",
                    kind=RENDERING_KIND,
                    media_type=wrong_type,
                    content=wrong_content,
                )
            )
        assert refused.value.code == "OAK-ARTIFACT-INVALID"


def test_an_unknown_kind_is_still_refused() -> None:
    with pytest.raises(OAKError) as refused:
        validate_opaque_artifact(
            Artifact(
                id="x.y",
                version="0.1.0",
                kind="report_draft",
                media_type=PDF_MEDIA_TYPE,
                content=b"%PDF-",
            )
        )
    assert refused.value.code == "OAK-ARTIFACT-KIND"


def test_recording_a_report_adds_no_lifecycle_transition() -> None:
    # The lifecycle as Sprint 12 left it. Recording revises the case at its own status
    # (as recording an approval does); it never needs, or gets, an edge of its own.
    assert {
        status.value: sorted(item.value for item in targets)
        for status, targets in ALLOWED_TRANSITIONS.items()
    } == {
        "draft": ["needs_confirmation", "ready_for_candidates"],
        "needs_confirmation": ["ready_for_candidates"],
        "ready_for_candidates": ["candidates_ready"],
        "candidates_ready": ["candidate_selected"],
        "candidate_selected": ["assurance_planned"],
        "assurance_planned": ["bundle_compiled"],
        "bundle_compiled": ["deployment_approved"],
        "deployment_approved": ["deployed"],
        "deployed": ["observing"],
        "observing": ["needs_confirmation"],
        "closed": [],
    }
    example = load_yaml_document((ROOT / "examples/example-design-case.yaml").read_text())
    for status in RECORDABLE:
        case = DesignCase.from_document({**example, "status": status.value, "version": "0.1.4"})
        successor = case.revise(status=status, updated_at="2026-10-16T12:00:00Z")
        assert (successor.status, successor.version) == (status, "0.1.5")


def test_the_report_schema_accepts_only_the_twenty_sections_in_order() -> None:
    example = load_yaml_document((ROOT / "examples/example-architecture-report.yaml").read_text())
    REGISTRY.validate("architecture-report.schema.json", example)
    assert [section["number"] for section in example["sections"]] == [
        *[str(number) for number in range(1, 15)],
        *"ABCDEF",
    ]
    with pytest.raises(ContractValidationError):
        REGISTRY.validate(
            "architecture-report.schema.json",
            {**example, "sections": example["sections"][:-1]},
        )


def test_a_quantity_without_a_unit_or_a_source_is_not_a_report() -> None:
    example = load_yaml_document((ROOT / "examples/example-architecture-report.yaml").read_text())
    comparison = next(s for s in example["sections"] if s["id"] == "comparison")
    quantity = comparison["blocks"][1]["rows"][0]["cells"][1]
    for field, bad in (("unit", ""), ("source", "a guess"), ("basis", "vibes")):
        quantity_copy = {**quantity, field: bad}
        broken = json.loads(json.dumps(example))
        target = next(s for s in broken["sections"] if s["id"] == "comparison")
        target["blocks"][1]["rows"][0]["cells"][1] = quantity_copy
        with pytest.raises(ContractValidationError):
            REGISTRY.validate("architecture-report.schema.json", broken)


def test_the_document_libraries_stay_inside_the_renderer_adapter(tmp_path: Path) -> None:
    package = tmp_path / "oak" / "application"
    package.mkdir(parents=True)
    (package / "leak.py").write_text("import pptx\nfrom reportlab.pdfgen import canvas\n")
    messages = sorted(violation.message for violation in check(tmp_path))
    assert messages == [
        "oak.application must not import pptx",
        "oak.application must not import reportlab",
    ]
