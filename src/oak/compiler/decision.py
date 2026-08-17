# SPDX-License-Identifier: Apache-2.0
"""Immutable candidate selection decisions."""

from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import Artifact, ArtifactReference, json_artifact

DECISION_MEDIA_TYPE = "application/vnd.oak.architecture-decision+json"


def create_selection_decision(
    selected: Artifact,
    alternatives: tuple[Artifact, ...],
    evaluation_result: Artifact,
    dependency_refs: tuple[ArtifactReference, ...],
    registry: SchemaRegistry,
    *,
    rationale: str,
    owner: str,
    decided_at: str,
) -> Artifact:
    selected_document = _document(selected)
    alternative_items = []
    for alternative in sorted(alternatives, key=lambda item: item.id):
        document = _document(alternative)
        reason = (
            "; ".join(document["rejection_reasons"])
            if document["status"] == "infeasible"
            else "Retained as a visible feasible trade-off but not selected by the owner."
        )
        alternative_items.append(
            {"candidate_ref": alternative.reference.to_document(), "reason": reason}
        )
    document = {
        "schema_version": "0.4.0",
        "id": f"decision.{selected.id}",
        "version": "0.1.0",
        "decided_at": decided_at,
        "owner": owner,
        "selected_candidate_ref": selected.reference.to_document(),
        "rationale": rationale,
        "alternatives": alternative_items,
        "dependency_digests": sorted(
            {selected.digest, evaluation_result.digest, *(item.digest for item in dependency_refs)}
        ),
        "extensions": {
            "oak.community/selected_variant": selected_document["extensions"][
                "oak.community/pattern_variant"
            ]
        },
    }
    registry.validate("architecture-decision.schema.json", document)
    return json_artifact(
        artifact_id=str(document["id"]),
        version=str(document["version"]),
        kind="architecture_decision",
        media_type=DECISION_MEDIA_TYPE,
        document=document,
    )


def _document(artifact: Artifact) -> dict[str, Any]:
    import json

    document = json.loads(artifact.content)
    if not isinstance(document, dict):  # pragma: no cover - guaranteed by construction
        raise TypeError("candidate artifact must contain an object")
    return document
