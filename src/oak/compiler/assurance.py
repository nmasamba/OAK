# SPDX-License-Identifier: Apache-2.0
"""Deterministic assurance-plan construction."""

from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import Artifact, json_artifact

ASSURANCE_MEDIA_TYPE = "application/vnd.oak.assurance-plan+json"


def create_assurance_plan(
    candidate: Artifact,
    evaluation_contract: Artifact,
    evaluation_result: Artifact,
    registry: SchemaRegistry,
    *,
    created_at: str,
) -> Artifact:
    evaluation = _document(evaluation_result)
    candidate_document = _document(candidate)
    test_status = "satisfied" if evaluation["status"] == "pass" else "blocked"
    document = {
        "schema_version": "0.4.0",
        "id": f"assurance.{candidate.id}",
        "version": "0.1.0",
        "created_at": created_at,
        "candidate_ref": candidate.reference.to_document(),
        "evaluation_contract_ref": evaluation_contract.reference.to_document(),
        "evaluation_result_ref": evaluation_result.reference.to_document(),
        "required_tests": [
            {
                "id": "test.offline-contract",
                "description": "Run citation, unsupported-assertion and latency fixture metrics.",
                "owner": "domain-reviewer",
                "status": test_status,
                "evidence_refs": [evaluation_result.id],
            },
            {
                "id": "test.no-egress",
                "description": "Verify the rendered target plan declares no runtime egress.",
                "owner": "security-reviewer",
                "status": "required",
                "evidence_refs": [],
            },
        ],
        "evidence_requirements": [
            {
                "id": "evidence.component-lock",
                "description": "Retain component manifest and catalogue snapshot digests.",
                "owner": "architecture-owner",
                "status": "satisfied",
                "evidence_refs": [
                    candidate_document["extensions"]["oak.community/catalogue_snapshot_ref"]["id"]
                ],
            },
            {
                "id": "evidence.observed-calibration",
                "description": (
                    "Collect observed target cost, latency, quality and energy before deployment."
                ),
                "owner": "evaluation-owner",
                "status": "required",
                "evidence_refs": [],
            },
        ],
        "controls": [
            {
                "id": "control.human-review",
                "description": "Require human review of generated cited answers.",
                "owner": "domain-reviewer",
                "status": "required",
                "evidence_refs": [],
            },
            {
                "id": "control.read-only-plan",
                "description": (
                    "Limit Sprint 2 runner operations to typed non-mutating planning phases."
                ),
                "owner": "security-reviewer",
                "status": "satisfied",
                "evidence_refs": [],
            },
        ],
        "gate_blockers": [
            {
                "gate": "gate_2",
                "status": "clear" if evaluation["status"] == "pass" else "blocked",
                "reason": "The deterministic offline evaluation passed."
                if evaluation["status"] == "pass"
                else "The deterministic offline evaluation is not passing.",
                "owner": "domain-reviewer",
            },
            {
                "gate": "gate_3",
                "status": "blocked",
                "reason": (
                    "Observed calibration, signing, approvals and runner verification are not "
                    "implemented."
                ),
                "owner": "environment-owner",
            },
        ],
        "extensions": {},
    }
    registry.validate("assurance-plan.schema.json", document)
    return json_artifact(
        artifact_id=str(document["id"]),
        version=str(document["version"]),
        kind="assurance_plan",
        media_type=ASSURANCE_MEDIA_TYPE,
        document=document,
    )


def _document(artifact: Artifact) -> dict[str, Any]:
    import json

    document = json.loads(artifact.content)
    if not isinstance(document, dict):  # pragma: no cover - guaranteed by construction
        raise TypeError("canonical artifact must contain an object")
    return document
