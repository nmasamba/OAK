# SPDX-License-Identifier: Apache-2.0
"""The explicit workspace format commands: inspect the format, and migrate it.

Nothing else migrates. A read of a workspace at an older format is refused; this service is
what carries it forward, once, under the workspace lock, and records what changed. A
migration that reshaped the current design case, or added objects, is recorded the way
every change to canonical state is: a successor of the case and an audit event, both
naming the migration as their origin, with the stored objects and history left as they
were. A migration that only changed the manifest records nothing, because nothing the
audit chain binds changed.
"""

from dataclasses import dataclass, replace
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.contracts import SchemaRegistry
from oak.domain import (
    ArtifactReference,
    DesignCase,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.workspace_format import (
    MIGRATION_EVENT_TYPE,
    MIGRATION_EXTENSION,
    MigrationOutcome,
    WorkspaceFormatReport,
)
from oak.ports.workspace import WorkspaceFormatPort

CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"


@dataclass(frozen=True, slots=True)
class MigrationResult:
    workspace_id: str
    from_format: str
    to_format: str
    steps: tuple[str, ...]
    new_artifact_refs: tuple[dict[str, Any], ...]
    case_ref: dict[str, Any] | None
    event_ref: dict[str, Any] | None

    @property
    def changed(self) -> bool:
        return bool(self.steps)

    def to_document(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "from_format": self.from_format,
            "to_format": self.to_format,
            "changed": self.changed,
            "migration_steps": list(self.steps),
            "new_artifact_refs": list(self.new_artifact_refs),
            "case_ref": self.case_ref,
            "event_ref": self.event_ref,
        }


class WorkspaceFormatService:
    def __init__(self, repository: WorkspaceFormatPort, registry: SchemaRegistry) -> None:
        self._repository = repository
        self._registry = registry

    def status(self) -> WorkspaceFormatReport:
        return self._repository.format_report()

    def migrate(self, context: CommandContext) -> MigrationResult:
        report = self._repository.format_report()
        if not report.known:
            # The adapter says the same thing on every other read; said here too so that a
            # migrate of a workspace this build cannot read is a refusal, not a no-op.
            self._repository.migration_outcome()
        if report.current:
            return MigrationResult(
                workspace_id=report.workspace_id,
                from_format=report.format,
                to_format=report.current_format,
                steps=(),
                new_artifact_refs=(),
                case_ref=None,
                event_ref=None,
            )
        outcome = self._repository.migration_outcome()
        if outcome.manifest["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
        origin = self._origin(outcome)
        input_digest = content_digest(canonical_json_bytes(origin))
        context = replace(
            context,
            idempotency_key=(
                context.idempotency_key or f"migrate:{input_digest.removeprefix('sha256:')}"
            ),
            correlation_id=(
                context.correlation_id or f"correlation:{input_digest.removeprefix('sha256:')[:24]}"
            ),
        )
        if not 16 <= len(context.idempotency_key) <= 240:
            raise OAKError(
                "OAK-IDEMPOTENCY-KEY", "idempotency key must contain 16 to 240 characters"
            )
        current_reference = outcome.manifest.get("current_case_ref")
        mutation = None
        case_ref: dict[str, Any] | None = None
        event_ref: dict[str, Any] | None = None
        if outcome.reshapes_case:
            if not isinstance(current_reference, dict):
                raise OAKError(
                    "OAK-WORKSPACE-MIGRATION",
                    "the migration added objects to a workspace that holds no design case, "
                    "so nothing can record them",
                )
            case_document = outcome.case_document or self._repository.read_json_artifact(
                ArtifactReference.from_document(current_reference)
            )
            self._registry.validate("design-case.schema.json", case_document)
            case = DesignCase.from_document(case_document)
            if case.tenant_id != context.tenant_id:
                raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
            extensions = dict(case.extensions or {})
            extensions[MIGRATION_EXTENSION] = origin
            # An event that names an intent names the source record that intent was
            # read from, as every interpretation and confirmation event does; the case
            # has carried that reference since it was created.
            source_reference = extensions.get("oak.community/source_record_ref")
            source_record_ref = (
                ArtifactReference.from_document(source_reference)
                if case.intent_ref is not None and isinstance(source_reference, dict)
                else None
            )
            successor = case.revise(
                status=case.status, updated_at=context.occurred_at, extensions=extensions
            )
            sequence = len(outcome.manifest["audit_events"]) + 1
            previous = (
                outcome.manifest["audit_events"][-1]["digest"]
                if outcome.manifest["audit_events"]
                else None
            )
            event_document = audit_event_document(
                sequence=sequence,
                previous_event_digest=previous,
                case_id=successor.id,
                case_version=successor.version,
                event_type=MIGRATION_EVENT_TYPE,
                actor=context.actor,
                tenant_id=context.tenant_id,
                interface_origin=context.interface_origin,
                correlation_id=context.correlation_id,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                occurred_at=context.occurred_at,
                intent_ref=successor.intent_ref,
                source_record_ref=source_record_ref,
                extensions={MIGRATION_EXTENSION: origin},
            )
            self._registry.validate("audit-event.schema.json", event_document)
            event_artifact = json_artifact(
                artifact_id=str(event_document["id"]),
                version=str(sequence),
                kind="audit_event",
                media_type=AUDIT_MEDIA_TYPE,
                document=event_document,
            )
            successor = successor.with_audit_head(event_artifact.digest)
            successor_document = successor.to_document()
            self._registry.validate("design-case.schema.json", successor_document)
            case_artifact = json_artifact(
                artifact_id=successor.id,
                version=successor.version,
                kind="design_case",
                media_type=CASE_MEDIA_TYPE,
                document=successor_document,
            )
            mutation = build_workspace_mutation(
                workspace_id=str(outcome.manifest["id"]),
                expected_case_version=case.version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(event_artifact, case_artifact),
                current_case_ref=case_artifact.reference,
                event_artifact=event_artifact,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
            case_ref = case_artifact.reference.to_document()
            event_ref = event_artifact.reference.to_document()
        self._repository.commit_migration(outcome, mutation)
        return MigrationResult(
            workspace_id=str(outcome.manifest["id"]),
            from_format=outcome.from_format,
            to_format=outcome.to_format,
            steps=outcome.steps,
            new_artifact_refs=tuple(
                artifact.reference.to_document() for artifact in outcome.new_artifacts
            ),
            case_ref=case_ref,
            event_ref=event_ref,
        )

    @staticmethod
    def _origin(outcome: MigrationOutcome) -> dict[str, Any]:
        return {
            "from_format": outcome.from_format,
            "to_format": outcome.to_format,
            "steps": list(outcome.steps),
            "source_manifest_digest": outcome.source_digest,
            "new_artifact_refs": [
                artifact.reference.to_document() for artifact in outcome.new_artifacts
            ],
        }


__all__ = ["MigrationResult", "WorkspaceFormatService"]
