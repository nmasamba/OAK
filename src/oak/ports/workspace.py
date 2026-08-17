# SPDX-License-Identifier: Apache-2.0
"""Local workspace persistence port."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from oak.domain.artifacts import Artifact, ArtifactReference


@dataclass(frozen=True, slots=True)
class WorkspaceEvent:
    """Transport-neutral metadata committed with one aggregate successor."""

    event_id: str
    workspace_id: str
    aggregate_id: str
    aggregate_version: str
    aggregate_sequence: int
    event_type: str
    tenant_id: str
    actor: str
    interface_origin: str
    correlation_id: str
    idempotency_key: str
    input_digest: str
    occurred_at: str
    event_ref: ArtifactReference
    case_ref: ArtifactReference

    def outbox_document(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_type": "design_case",
            "workspace_id": self.workspace_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "aggregate_sequence": self.aggregate_sequence,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "occurred_at": self.occurred_at,
            "payload_digest": self.event_ref.digest,
            "audit_event_id": self.event_ref.id,
            "event_ref": self.event_ref.to_document(),
            "case_ref": self.case_ref.to_document(),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceMutation:
    expected_case_version: str | None
    idempotency_key: str
    input_digest: str
    artifacts: tuple[Artifact, ...]
    current_case_ref: ArtifactReference
    event_ref: ArtifactReference
    event: WorkspaceEvent
    updated_at: str


@dataclass(frozen=True, slots=True)
class WorkspaceCommit:
    case_document: dict[str, Any]
    duplicate: bool


class WorkspaceRepository(Protocol):
    def initialize(self, *, workspace_id: str, tenant_id: str, created_at: str) -> None: ...

    def manifest(self) -> dict[str, Any]: ...

    def current_case(self) -> dict[str, Any] | None: ...

    def read_artifact(self, reference: ArtifactReference) -> bytes: ...

    def read_json_artifact(self, reference: ArtifactReference) -> dict[str, Any]: ...

    def idempotent_case(self, key: str, input_digest: str) -> dict[str, Any] | None: ...

    def commit(self, mutation: WorkspaceMutation) -> WorkspaceCommit: ...

    def export_to(self, destination: Path) -> None: ...

    def import_from(self, source: Path) -> None: ...
