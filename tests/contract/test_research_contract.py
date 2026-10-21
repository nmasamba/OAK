# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-002: the research contract is registered everywhere a contract must be.

ADR-0018, OAK-FR-CAT-004 and OAK-FR-CAT-005. The two research schemas validate their
examples; the evidence-class enum is one closed list in the domain and in the schema; the
two kinds are registered in both kind tables and the workspace manifest; the two audit
events are in the enum; the two case extensions are in the export-lineage check; an
objective's value may be null only with its reason (K4); and the report schema admits
twenty or twenty-one sections, the twenty-first being appendix G. An export from a
workspace that never researched carries none of this, so a `0.9.0` reader still validates
it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.persistence.file_workspace import JSON_MEDIA_KIND, KIND_SCHEMA
from oak.contracts import ContractValidationError, SchemaRegistry, load_yaml_document
from oak.domain import (
    COMPARISON_EXTENSION,
    EVIDENCE_CLASSES,
    EVIDENCE_SOURCE_TYPES,
    EVIDENCE_WORDS,
    RESEARCH_EXTENSION,
    RESEARCH_REVIEW_MEDIA_TYPE,
    RESEARCH_REVIEW_REFS,
    RESEARCH_SNAPSHOT_MEDIA_TYPE,
    RESEARCH_SNAPSHOT_REF,
    ArtifactReference,
)
from tests.report_support import build_reference_case

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _example(name: str) -> dict[str, object]:
    return load_yaml_document((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_the_research_examples_validate_and_list_no_real_host() -> None:
    snapshot = _example("example-research-snapshot.yaml")
    review = _example("example-research-review.yaml")
    REGISTRY.validate("research-snapshot.schema.json", snapshot)
    REGISTRY.validate("research-review.schema.json", review)

    assert snapshot["source_mode"] == "fixture"
    assert snapshot["hosts"] == []
    assert all(request["host"] == "fixture" for request in snapshot["requests"])
    assert {item["verdict"] for item in snapshot["items"]} == {"passed", "needs_review"}
    assert review["snapshot_ref"]["id"] == snapshot["id"]
    assert review["item_id"] in {item["id"] for item in snapshot["items"]}


def test_the_evidence_classes_are_one_closed_list_everywhere() -> None:
    schema = _schema("research-snapshot.schema.json")
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    claim_enum = defs["claim"]["properties"]["evidence_class"]["enum"]
    pairing_enum = defs["pairing"]["properties"]["claim_classes"]["items"]["enum"]

    assert list(EVIDENCE_CLASSES) == claim_enum == pairing_enum
    assert set(EVIDENCE_WORDS) == set(EVIDENCE_CLASSES)
    assert set(EVIDENCE_SOURCE_TYPES) == set(EVIDENCE_CLASSES)
    source_types = _schema("common.schema.json")["$defs"]["evidenceRef"]["properties"][
        "source_type"
    ]["enum"]
    for source_type, confidence in EVIDENCE_SOURCE_TYPES.values():
        assert source_type in source_types
        # No researched evidence may read as if OAK checked it.
        assert source_type not in {"measured", "authoritative", "official_guidance"}
        assert 0.0 <= confidence <= 1.0
    assert EVIDENCE_SOURCE_TYPES["unverified"] == ("inference", 0.0)


def test_each_research_kind_is_registered_in_every_place_a_kind_must_be() -> None:
    manifest_kinds = set(
        _schema("workspace-manifest.schema.json")["$defs"]["indexedArtifact"]["properties"]["kind"][
            "enum"
        ]
    )
    assert KIND_SCHEMA["research_snapshot"] == "research-snapshot.schema.json"
    assert KIND_SCHEMA["research_review"] == "research-review.schema.json"
    assert JSON_MEDIA_KIND[RESEARCH_SNAPSHOT_MEDIA_TYPE] == "research_snapshot"
    assert JSON_MEDIA_KIND[RESEARCH_REVIEW_MEDIA_TYPE] == "research_review"
    assert {"research_snapshot", "research_review"} <= manifest_kinds


@pytest.mark.parametrize("event_type", ["research_completed", "research_item_reviewed"])
def test_the_research_events_are_audit_event_types(event_type: str) -> None:
    event = _example("example-audit-event.yaml")
    REGISTRY.validate("audit-event.schema.json", {**event, "event_type": event_type})


def test_the_research_references_are_in_the_export_lineage_check() -> None:
    """The check is a table inside one method; pin the two rows rather than rediscover them."""

    source = (ROOT / "src/oak/adapters/persistence/file_workspace.py").read_text(encoding="utf-8")
    assert f'("{RESEARCH_SNAPSHOT_REF}", "research_snapshot")' in source
    assert f'("{RESEARCH_REVIEW_REFS}", "research_review")' in source
    for key in (
        RESEARCH_SNAPSHOT_REF,
        RESEARCH_REVIEW_REFS,
        RESEARCH_EXTENSION,
        COMPARISON_EXTENSION,
    ):
        REGISTRY.validate(
            "design-case.schema.json",
            {**_example("example-design-case.yaml"), "extensions": {key: []}},
        )


def test_an_objective_value_may_be_null_only_with_its_reason() -> None:
    candidate = _example("example-architecture-candidate.yaml")
    objective = candidate["objectives"][0]

    with_reason = copy.deepcopy(candidate)
    with_reason["objectives"][0] = {
        **objective,
        "value": None,
        "unknown_reason": "Nothing is published.",
    }
    REGISTRY.validate("architecture-candidate.schema.json", with_reason)

    without_reason = copy.deepcopy(candidate)
    without_reason["objectives"][0] = {**objective, "value": None}
    with pytest.raises(ContractValidationError):
        REGISTRY.validate("architecture-candidate.schema.json", without_reason)

    reason_on_a_number = copy.deepcopy(candidate)
    reason_on_a_number["objectives"][0] = {**objective, "unknown_reason": "but it has a value"}
    with pytest.raises(ContractValidationError):
        REGISTRY.validate("architecture-candidate.schema.json", reason_on_a_number)


def test_the_report_schema_admits_appendix_g_and_nothing_beyond_it() -> None:
    example = _example("example-architecture-report.yaml")
    appendix = copy.deepcopy(example["sections"][-1])
    appendix.update({"id": "appendix-research", "number": "G", "kind": "appendix"})

    REGISTRY.validate(
        "architecture-report.schema.json", {**example, "sections": [*example["sections"], appendix]}
    )
    with pytest.raises(ContractValidationError):
        REGISTRY.validate(
            "architecture-report.schema.json",
            {**example, "sections": [*example["sections"], appendix, appendix]},
        )
    comparison = next(s for s in example["sections"] if s["id"] == "comparison")
    row = comparison["blocks"][1]["rows"][0]
    column = next(i for i, cell in enumerate(row["cells"]) if cell["type"] == "quantity")
    for basis in ("published by source", "measured by source"):
        document = json.loads(json.dumps(example))
        target = next(s for s in document["sections"] if s["id"] == "comparison")
        cell = target["blocks"][1]["rows"][0]["cells"][column]
        target["blocks"][1]["rows"][0]["cells"][column] = {**cell, "basis": basis}
        REGISTRY.validate("architecture-report.schema.json", document)
    unknown_with_unit = json.loads(json.dumps(example))
    target = next(s for s in unknown_with_unit["sections"] if s["id"] == "comparison")
    target["blocks"][1]["rows"][0]["cells"][column] = {
        "type": "unknown",
        "reason": "Not published.",
        "unit": "Wh/request",
    }
    REGISTRY.validate("architecture-report.schema.json", unknown_with_unit)


def test_an_unresearched_export_carries_nothing_new_and_imports_unchanged(tmp_path: Path) -> None:
    """A pre-change export: the reference journey records no research, so a `0.9.0` reader validates it."""

    workspace = build_reference_case(tmp_path / "source", "bundle_compiled")
    source = FileWorkspaceRepository(workspace, REGISTRY)
    export = tmp_path / "portable-export"
    source.export_to(export)
    manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))

    assert not any(entry["kind"].startswith("research") for entry in manifest["artifact_index"])
    extensions = source.current_case()["extensions"]
    assert RESEARCH_SNAPSHOT_REF not in extensions and RESEARCH_REVIEW_REFS not in extensions
    for entry in manifest["artifact_index"]:
        if entry["kind"] == "architecture_candidate":
            reference = ArtifactReference(
                id=entry["id"],
                version=entry["version"],
                digest=entry["digest"],
                media_type=entry["media_type"],
            )
            document = json.loads(source.read_artifact(reference))
            assert all(isinstance(o["value"], (int, float)) for o in document["objectives"])

    imported = FileWorkspaceRepository(tmp_path / "imported", REGISTRY)
    imported.import_from(export)
    assert imported.manifest() == source.manifest()
