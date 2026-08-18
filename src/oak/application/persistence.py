# SPDX-License-Identifier: Apache-2.0
"""Application construction of one canonical persistence transaction."""

import hashlib
from typing import Any

from oak.domain.artifacts import Artifact, ArtifactReference
from oak.ports.workspace import WorkspaceEvent, WorkspaceMutation


def build_workspace_mutation(
    *,
    workspace_id: str,
    expected_case_version: str | None,
    idempotency_key: str,
    input_digest: str,
    artifacts: tuple[Artifact, ...],
    current_case_ref: ArtifactReference,
    event_artifact: Artifact,
    event_document: dict[str, Any],
    updated_at: str,
) -> WorkspaceMutation:
    """Bind transition, idempotency, audit, and outbox metadata before persistence."""

    event_ref = event_artifact.reference
    event_identity = "\n".join(
        (
            str(event_document["tenant_id"]),
            workspace_id,
            str(event_document["case_id"]),
            str(event_document["sequence"]),
            event_ref.digest,
        )
    ).encode("utf-8")
    event = WorkspaceEvent(
        event_id=f"event.{hashlib.sha256(event_identity).hexdigest()}",
        workspace_id=workspace_id,
        aggregate_id=str(event_document["case_id"]),
        aggregate_version=str(event_document["case_version"]),
        aggregate_sequence=int(event_document["sequence"]),
        event_type=str(event_document["event_type"]),
        tenant_id=str(event_document["tenant_id"]),
        actor=str(event_document["actor"]),
        interface_origin=str(event_document["interface_origin"]),
        correlation_id=str(event_document["correlation_id"]),
        idempotency_key=str(event_document["idempotency_key"]),
        input_digest=str(event_document["input_digest"]),
        occurred_at=str(event_document["occurred_at"]),
        event_ref=event_ref,
        case_ref=current_case_ref,
    )
    return WorkspaceMutation(
        expected_case_version=expected_case_version,
        idempotency_key=idempotency_key,
        input_digest=input_digest,
        artifacts=artifacts,
        current_case_ref=current_case_ref,
        event_ref=event_ref,
        event=event,
        updated_at=updated_at,
    )
