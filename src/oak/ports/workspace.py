# SPDX-License-Identifier: Apache-2.0
"""Local workspace persistence port."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from oak.domain.artifacts import Artifact, ArtifactReference


@dataclass(frozen=True, slots=True)
class WorkspaceMutation:
    expected_case_version: str | None
    idempotency_key: str
    input_digest: str
    artifacts: tuple[Artifact, ...]
    current_case_ref: ArtifactReference
    event_ref: ArtifactReference
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
