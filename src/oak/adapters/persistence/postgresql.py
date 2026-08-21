# SPDX-License-Identifier: Apache-2.0
"""Tenant-scoped PostgreSQL workspace repository and content-addressed artifact metadata."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, and_, create_engine, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from oak.adapters.persistence.file_workspace import (
    JSON_MEDIA_KIND,
    KIND_SCHEMA,
    MAXIMUM_ARTIFACT_BYTES,
    OBJECT_DIGEST,
    FileWorkspaceRepository,
)
from oak.adapters.persistence.models import (
    artifact_versions,
    design_case_heads,
    design_case_versions,
    idempotency_records,
    outbox_events,
    transitions,
    workspaces,
)
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from oak.domain.artifacts import Artifact, ArtifactReference, canonical_json_bytes, content_digest
from oak.ports.workspace import WorkspaceCommit, WorkspaceMutation

BeforeCommit = Callable[[Connection, WorkspaceMutation], None]
MAXIMUM_EXPORT_BYTES = 67_108_864


def create_postgresql_engine(database_url: str) -> Engine:
    """Create the replaceable synchronous SQLAlchemy boundary used by API and worker.

    `hide_parameters=True` is a confidentiality control, not a preference. Canonical
    documents — including the user's brief text — are bound as statement parameters, and
    SQLAlchemy's default embeds bound values in `StatementError` messages. The API's own
    handler returns a safe 500 without reading the exception, but Starlette re-raises
    afterwards and uvicorn's error logger writes the whole traceback to stderr, which
    under Compose is the container log. That is the TM-10 log-leak path.
    """

    return create_engine(database_url, pool_pre_ping=True, hide_parameters=True)


class PostgreSQLReadinessProbe:
    """Return only coarse database availability; never expose connection details."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                return int(connection.scalar(text("SELECT 1")) or 0) == 1
        except SQLAlchemyError:
            return False


class PostgreSQLWorkspaceRepository:
    """Persist one workspace through a row-locked, single-database transaction."""

    def __init__(
        self,
        engine: Engine,
        registry: SchemaRegistry,
        artifact_root: Path,
        *,
        workspace_id: str,
        tenant_id: str,
        environment_id: str = "local",
        before_commit: BeforeCommit | None = None,
    ) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgreSQLWorkspaceRepository requires a PostgreSQL engine")
        self._engine = engine
        self._registry = registry
        self._artifact_root = artifact_root
        self._objects = artifact_root / "sha256"
        self.workspace_id = workspace_id
        self.tenant_id = tenant_id
        self.environment_id = environment_id
        self._before_commit = before_commit

    def initialize(self, *, workspace_id: str, tenant_id: str, created_at: str) -> None:
        if workspace_id != self.workspace_id or tenant_id != self.tenant_id:
            raise OAKError(
                "OAK-TENANT-MISMATCH", "repository scope does not match workspace initialization"
            )
        self._objects.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(workspaces).values(
                        **self._scope(),
                        revision=0,
                        created_at=_parse_time(created_at),
                        updated_at=_parse_time(created_at),
                        current_case_id=None,
                        current_case_version=None,
                        current_case_digest=None,
                    )
                )
        except IntegrityError as error:
            raise OAKError("OAK-WORKSPACE-EXISTS", "workspace is already initialized") from error

    def manifest(self) -> dict[str, Any]:
        with self._engine.connect() as connection:
            workspace = self._workspace_row(connection)
            artifacts = connection.execute(
                select(artifact_versions)
                .where(self._workspace_predicate(artifact_versions))
                .order_by(
                    artifact_versions.c.kind,
                    artifact_versions.c.artifact_id,
                    artifact_versions.c.artifact_version,
                )
            ).mappings()
            events = connection.execute(
                select(transitions)
                .where(self._workspace_predicate(transitions))
                .order_by(transitions.c.aggregate_sequence)
            ).mappings()
            idempotency = connection.execute(
                select(idempotency_records)
                .where(self._workspace_predicate(idempotency_records))
                .order_by(idempotency_records.c.aggregate_sequence)
            ).mappings()

            artifact_index = [
                {
                    "id": row["artifact_id"],
                    "version": row["artifact_version"],
                    "digest": row["digest"],
                    "media_type": row["media_type"],
                    "kind": row["kind"],
                    "size_bytes": row["size_bytes"],
                }
                for row in artifacts
            ]
            event_refs = [
                ArtifactReference(
                    id=str(row["event_artifact_id"]),
                    version=str(row["event_artifact_version"]),
                    digest=str(row["event_artifact_digest"]),
                    media_type="application/vnd.oak.audit-event+json",
                ).to_document()
                for row in events
            ]
            idempotency_documents = [
                {
                    "key": row["idempotency_key"],
                    "input_digest": row["input_digest"],
                    "result_case_ref": ArtifactReference(
                        id=str(row["result_case_id"]),
                        version=str(row["result_case_version"]),
                        digest=str(row["result_case_digest"]),
                        media_type="application/vnd.oak.design-case+json",
                    ).to_document(),
                    "event_ref": event_refs[int(row["aggregate_sequence"]) - 1],
                }
                for row in idempotency
            ]
            current_ref = None
            if workspace["current_case_id"] is not None:
                current_ref = ArtifactReference(
                    id=str(workspace["current_case_id"]),
                    version=str(workspace["current_case_version"]),
                    digest=str(workspace["current_case_digest"]),
                    media_type="application/vnd.oak.design-case+json",
                ).to_document()
            document = {
                "schema_version": "0.4.0",
                "id": self.workspace_id,
                "version": int(workspace["revision"]),
                "tenant_id": self.tenant_id,
                "created_at": _format_time(workspace["created_at"]),
                "updated_at": _format_time(workspace["updated_at"]),
                "current_case_ref": current_ref,
                "artifact_index": artifact_index,
                "audit_events": event_refs,
                "idempotency_records": idempotency_documents,
                "extensions": {},
            }
        self._registry.validate("workspace-manifest.schema.json", document)
        return document

    def current_case(self) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            workspace = self._workspace_row(connection)
        if workspace["current_case_id"] is None:
            return None
        return self.read_json_artifact(
            ArtifactReference(
                id=str(workspace["current_case_id"]),
                version=str(workspace["current_case_version"]),
                digest=str(workspace["current_case_digest"]),
                media_type="application/vnd.oak.design-case+json",
            )
        )

    def read_artifact(self, reference: ArtifactReference) -> bytes:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(artifact_versions).where(
                        self._workspace_predicate(artifact_versions),
                        artifact_versions.c.artifact_id == reference.id,
                        artifact_versions.c.artifact_version == reference.version,
                        artifact_versions.c.digest == reference.digest,
                        artifact_versions.c.media_type == reference.media_type,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OAKError("OAK-WORKSPACE-NOT-FOUND", "artifact was not found")
        return self._read_object(str(row["digest"]), expected_size=int(row["size_bytes"]))

    def read_json_artifact(self, reference: ArtifactReference) -> dict[str, Any]:
        content = self.read_artifact(reference)
        try:
            document = json.loads(content)
        except json.JSONDecodeError as error:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed JSON artifact is invalid") from error
        if not isinstance(document, dict):
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed JSON artifact must be an object")
        kind = JSON_MEDIA_KIND.get(reference.media_type)
        if kind is None:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "artifact reference is not canonical JSON")
        self._validate_artifact(
            Artifact(
                id=reference.id,
                version=reference.version,
                kind=kind,
                media_type=reference.media_type,
                content=content,
            )
        )
        return document

    def idempotent_case(self, key: str, input_digest: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = self._idempotency_row(connection, key)
        if row is None:
            return None
        if row["input_digest"] != input_digest:
            raise OAKError(
                "OAK-IDEMPOTENCY-CONFLICT",
                "idempotency key was already used for different input",
            )
        return self.read_json_artifact(self._case_reference(row))

    def commit(self, mutation: WorkspaceMutation) -> WorkspaceCommit:
        for artifact in mutation.artifacts:
            self._validate_artifact(artifact)
            self._write_object(artifact)

        with self._engine.begin() as connection:
            workspace = self._workspace_row(connection, for_update=True)
            duplicate = self._idempotency_row(connection, mutation.idempotency_key)
            if duplicate is not None:
                if duplicate["input_digest"] != mutation.input_digest:
                    raise OAKError(
                        "OAK-IDEMPOTENCY-CONFLICT",
                        "idempotency key was already used for different input",
                    )
                case_document = self._json_document(connection, self._case_reference(duplicate))
                return WorkspaceCommit(case_document=case_document, duplicate=True)

            self._check_expected_version(workspace, mutation.expected_case_version)
            event_document, case_document = self._validate_mutation(connection, workspace, mutation)
            self._insert_artifacts(connection, mutation)
            self._insert_case_version(connection, mutation, case_document)
            self._advance_case_head(connection, mutation)
            self._insert_transition(connection, mutation)
            self._insert_idempotency(connection, mutation)
            self._insert_outbox(connection, mutation)
            connection.execute(
                update(workspaces)
                .where(self._workspace_predicate(workspaces))
                .values(
                    revision=int(workspace["revision"]) + 1,
                    updated_at=_parse_time(mutation.updated_at),
                    current_case_id=mutation.current_case_ref.id,
                    current_case_version=mutation.current_case_ref.version,
                    current_case_digest=mutation.current_case_ref.digest,
                )
            )
            if self._before_commit is not None:
                self._before_commit(connection, mutation)
            if event_document["id"] != mutation.event.event_ref.id:
                raise OAKError("OAK-WORKSPACE-MUTATION", "outbox event identity changed")
        return WorkspaceCommit(case_document=case_document, duplicate=False)

    def export_to(self, destination: Path) -> None:
        if destination.exists():
            raise OAKError("OAK-EXPORT-EXISTS", "export destination already exists")
        parent = destination.parent.resolve()
        parent.mkdir(parents=True, exist_ok=True)
        manifest = self.manifest()
        total = len(canonical_json_bytes(manifest))
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=parent))
        validation_root: Path | None = None
        try:
            objects = temporary / "objects" / "sha256"
            objects.mkdir(parents=True, mode=0o700)
            self._write_new_file(temporary / "manifest.json", canonical_json_bytes(manifest))
            for entry in manifest["artifact_index"]:
                reference = ArtifactReference(
                    id=str(entry["id"]),
                    version=str(entry["version"]),
                    digest=str(entry["digest"]),
                    media_type=str(entry["media_type"]),
                )
                content = self.read_artifact(reference)
                total += len(content)
                if total > MAXIMUM_EXPORT_BYTES:
                    raise OAKError("OAK-EXPORT-SIZE", "canonical export exceeds the size limit")
                self._write_new_file(objects / self._digest_hex(reference.digest), content)
            validation_root = Path(tempfile.mkdtemp(prefix=".oak-export-validation-", dir=parent))
            FileWorkspaceRepository(validation_root / "workspace", self._registry).import_from(
                temporary
            )
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
            if validation_root is not None and validation_root.exists():
                shutil.rmtree(validation_root)

    def import_from(self, source: Path) -> None:
        validation_root = Path(tempfile.mkdtemp(prefix="oak-postgres-import-"))
        try:
            validated = FileWorkspaceRepository(validation_root / "workspace", self._registry)
            validated.import_from(source)
            manifest = validated.manifest()
            if manifest["id"] != self.workspace_id or manifest["tenant_id"] != self.tenant_id:
                raise OAKError(
                    "OAK-IMPORT-SCOPE", "import workspace or tenant does not match destination"
                )
            total = len(canonical_json_bytes(manifest))
            artifacts: list[tuple[dict[str, Any], Artifact]] = []
            for entry in manifest["artifact_index"]:
                reference = ArtifactReference(
                    id=str(entry["id"]),
                    version=str(entry["version"]),
                    digest=str(entry["digest"]),
                    media_type=str(entry["media_type"]),
                )
                content = validated.read_artifact(reference)
                total += len(content)
                if total > MAXIMUM_EXPORT_BYTES:
                    raise OAKError("OAK-IMPORT-SIZE", "canonical import exceeds the size limit")
                artifact = Artifact(
                    id=reference.id,
                    version=reference.version,
                    kind=str(entry["kind"]),
                    media_type=reference.media_type,
                    content=content,
                )
                self._validate_artifact(artifact)
                self._write_object(artifact)
                artifacts.append((entry, artifact))
            self._restore_manifest(manifest, validated, artifacts)
        finally:
            shutil.rmtree(validation_root)

    def transaction_counts(self) -> dict[str, int]:
        """Return scoped metadata counts for rollback and operator diagnostics."""

        tables = (
            artifact_versions,
            design_case_versions,
            design_case_heads,
            transitions,
            idempotency_records,
            outbox_events,
        )
        with self._engine.connect() as connection:
            return {
                table.name: int(
                    connection.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(self._workspace_predicate(table))
                    )
                    or 0
                )
                for table in tables
            }

    def _restore_manifest(
        self,
        manifest: dict[str, Any],
        validated: FileWorkspaceRepository,
        artifacts: list[tuple[dict[str, Any], Artifact]],
    ) -> None:
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(workspaces).values(
                        **self._scope(),
                        revision=0,
                        created_at=_parse_time(str(manifest["created_at"])),
                        updated_at=_parse_time(str(manifest["created_at"])),
                        current_case_id=None,
                        current_case_version=None,
                        current_case_digest=None,
                    )
                )
                for _entry, artifact in artifacts:
                    document = None
                    if artifact.kind != "brief_source":
                        document = _json_object(artifact.content, "canonical artifact")
                    connection.execute(
                        insert(artifact_versions).values(
                            **self._scope(),
                            artifact_id=artifact.id,
                            artifact_version=artifact.version,
                            digest=artifact.digest,
                            kind=artifact.kind,
                            media_type=artifact.media_type,
                            size_bytes=len(artifact.content),
                            storage_key=self._digest_hex(artifact.digest),
                            canonical_document=document,
                            created_at=_parse_time(str(manifest["updated_at"])),
                        )
                    )

                restored_cases: set[tuple[str, str]] = set()
                for sequence, (event_reference_document, idempotency) in enumerate(
                    zip(
                        manifest["audit_events"],
                        manifest["idempotency_records"],
                        strict=True,
                    ),
                    start=1,
                ):
                    event_reference = ArtifactReference.from_document(event_reference_document)
                    case_reference = ArtifactReference.from_document(idempotency["result_case_ref"])
                    event = validated.read_json_artifact(event_reference)
                    case = validated.read_json_artifact(case_reference)
                    case_identity = (case_reference.id, case_reference.version)
                    if case_identity not in restored_cases:
                        connection.execute(
                            insert(design_case_versions).values(
                                **self._scope(),
                                case_id=case_reference.id,
                                case_version=case_reference.version,
                                digest=case_reference.digest,
                                status=case["status"],
                                audit_head=case["audit_head"],
                                document=case,
                                created_at=_parse_time(str(event["occurred_at"])),
                            )
                        )
                        restored_cases.add(case_identity)
                    stable_event_id = self._restored_event_id(event, event_reference)
                    connection.execute(
                        insert(transitions).values(
                            **self._scope(),
                            case_id=event["case_id"],
                            aggregate_sequence=sequence,
                            event_id=stable_event_id,
                            case_version=event["case_version"],
                            event_type=event["event_type"],
                            actor=event["actor"],
                            interface_origin=event["interface_origin"],
                            correlation_id=event["correlation_id"],
                            idempotency_key=idempotency["key"],
                            input_digest=idempotency["input_digest"],
                            occurred_at=_parse_time(str(event["occurred_at"])),
                            event_artifact_id=event_reference.id,
                            event_artifact_version=event_reference.version,
                            event_artifact_digest=event_reference.digest,
                        )
                    )
                    connection.execute(
                        insert(idempotency_records).values(
                            **self._scope(),
                            idempotency_key=idempotency["key"],
                            input_digest=idempotency["input_digest"],
                            result_case_id=case_reference.id,
                            result_case_version=case_reference.version,
                            result_case_digest=case_reference.digest,
                            event_id=stable_event_id,
                            aggregate_sequence=sequence,
                            created_at=_parse_time(str(event["occurred_at"])),
                        )
                    )
                    payload = {
                        "event_id": stable_event_id,
                        "aggregate_type": "design_case",
                        "workspace_id": self.workspace_id,
                        "aggregate_id": event["case_id"],
                        "aggregate_version": event["case_version"],
                        "aggregate_sequence": sequence,
                        "event_type": event["event_type"],
                        "tenant_id": self.tenant_id,
                        "occurred_at": event["occurred_at"],
                        "payload_digest": event_reference.digest,
                        "audit_event_id": event_reference.id,
                        "event_ref": event_reference.to_document(),
                        "case_ref": case_reference.to_document(),
                    }
                    connection.execute(
                        insert(outbox_events).values(
                            **self._scope(),
                            event_id=stable_event_id,
                            aggregate_type="design_case",
                            aggregate_id=event["case_id"],
                            aggregate_version=event["case_version"],
                            aggregate_sequence=sequence,
                            event_type=event["event_type"],
                            payload=payload,
                            payload_digest=event_reference.digest,
                            occurred_at=_parse_time(str(event["occurred_at"])),
                            available_at=_parse_time(str(event["occurred_at"])),
                            claimed_by=None,
                            claim_expires_at=None,
                            delivery_attempts=0,
                            delivered_at=None,
                            last_error_code=None,
                        )
                    )

                current_document = manifest["current_case_ref"]
                if current_document is not None:
                    current = ArtifactReference.from_document(current_document)
                    connection.execute(
                        insert(design_case_heads).values(
                            **self._scope(),
                            case_id=current.id,
                            current_version=current.version,
                            current_digest=current.digest,
                            updated_at=_parse_time(str(manifest["updated_at"])),
                        )
                    )
                    current_values: dict[str, Any] = {
                        "current_case_id": current.id,
                        "current_case_version": current.version,
                        "current_case_digest": current.digest,
                    }
                else:
                    current_values = {}
                connection.execute(
                    update(workspaces)
                    .where(self._workspace_predicate(workspaces))
                    .values(
                        revision=int(manifest["version"]),
                        updated_at=_parse_time(str(manifest["updated_at"])),
                        **current_values,
                    )
                )
        except IntegrityError as error:
            raise OAKError(
                "OAK-WORKSPACE-EXISTS", "import destination is already initialized"
            ) from error

    def _restored_event_id(self, event: dict[str, Any], event_reference: ArtifactReference) -> str:
        identity = "\n".join(
            (
                self.tenant_id,
                self.workspace_id,
                str(event["case_id"]),
                str(event["sequence"]),
                event_reference.digest,
            )
        ).encode("utf-8")
        return f"event.{hashlib.sha256(identity).hexdigest()}"

    @staticmethod
    def _write_new_file(path: Path, content: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def _validate_mutation(
        self,
        connection: Connection,
        workspace: dict[str, Any],
        mutation: WorkspaceMutation,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        artifacts = {artifact.digest: artifact for artifact in mutation.artifacts}
        case_artifact = artifacts.get(mutation.current_case_ref.digest)
        event_artifact = artifacts.get(mutation.event_ref.digest)
        if case_artifact is None or case_artifact.kind != "design_case":
            raise OAKError("OAK-WORKSPACE-MUTATION", "mutation is missing its case artifact")
        if event_artifact is None or event_artifact.kind != "audit_event":
            raise OAKError("OAK-WORKSPACE-MUTATION", "mutation is missing its audit event")
        event = _json_object(event_artifact.content, "audit event")
        case = _json_object(case_artifact.content, "design case")
        expected_sequence = int(workspace["revision"]) + 1
        previous = None
        if int(workspace["revision"]) > 0:
            previous = connection.scalar(
                select(transitions.c.event_artifact_digest).where(
                    self._workspace_predicate(transitions),
                    transitions.c.aggregate_sequence == int(workspace["revision"]),
                )
            )
        transaction_event = mutation.event
        if (
            event["sequence"] != expected_sequence
            or event["previous_event_digest"] != previous
            or case["audit_head"] != mutation.event_ref.digest
            or event["case_id"] != case["id"]
            or event["case_version"] != case["version"]
            or transaction_event.event_ref != mutation.event_ref
            or transaction_event.case_ref != mutation.current_case_ref
            or transaction_event.workspace_id != self.workspace_id
            or transaction_event.event_ref.id != event["id"]
            or transaction_event.aggregate_id != event["case_id"]
            or transaction_event.aggregate_version != event["case_version"]
            or transaction_event.aggregate_sequence != event["sequence"]
            or transaction_event.event_type != event["event_type"]
            or transaction_event.tenant_id != self.tenant_id
            or transaction_event.tenant_id != event["tenant_id"]
            or transaction_event.actor != event["actor"]
            or transaction_event.interface_origin != event["interface_origin"]
            or transaction_event.correlation_id != event["correlation_id"]
            or transaction_event.idempotency_key != mutation.idempotency_key
            or transaction_event.input_digest != mutation.input_digest
            or transaction_event.occurred_at != event["occurred_at"]
        ):
            raise OAKError(
                "OAK-WORKSPACE-MUTATION",
                "transaction metadata does not match canonical case and audit artifacts",
            )
        return event, case

    def _insert_artifacts(self, connection: Connection, mutation: WorkspaceMutation) -> None:
        for artifact in mutation.artifacts:
            existing = connection.execute(
                select(artifact_versions.c.digest).where(
                    self._workspace_predicate(artifact_versions),
                    artifact_versions.c.artifact_id == artifact.id,
                    artifact_versions.c.artifact_version == artifact.version,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing != artifact.digest:
                    raise OAKError(
                        "OAK-ARTIFACT-IMMUTABLE",
                        "an immutable artifact version already has different content",
                    )
                continue
            document = None
            if artifact.kind != "brief_source":
                document = _json_object(artifact.content, "canonical artifact")
            connection.execute(
                insert(artifact_versions).values(
                    **self._scope(),
                    artifact_id=artifact.id,
                    artifact_version=artifact.version,
                    digest=artifact.digest,
                    kind=artifact.kind,
                    media_type=artifact.media_type,
                    size_bytes=len(artifact.content),
                    storage_key=self._digest_hex(artifact.digest),
                    canonical_document=document,
                    created_at=_parse_time(mutation.updated_at),
                )
            )

    def _insert_case_version(
        self, connection: Connection, mutation: WorkspaceMutation, case: dict[str, Any]
    ) -> None:
        connection.execute(
            insert(design_case_versions).values(
                **self._scope(),
                case_id=mutation.current_case_ref.id,
                case_version=mutation.current_case_ref.version,
                digest=mutation.current_case_ref.digest,
                status=case["status"],
                audit_head=case["audit_head"],
                document=case,
                created_at=_parse_time(mutation.updated_at),
            )
        )

    def _advance_case_head(self, connection: Connection, mutation: WorkspaceMutation) -> None:
        head_predicate = and_(
            self._workspace_predicate(design_case_heads),
            design_case_heads.c.case_id == mutation.current_case_ref.id,
        )
        existing = connection.scalar(
            select(func.count()).select_from(design_case_heads).where(head_predicate)
        )
        values = {
            "current_version": mutation.current_case_ref.version,
            "current_digest": mutation.current_case_ref.digest,
            "updated_at": _parse_time(mutation.updated_at),
        }
        if existing:
            connection.execute(update(design_case_heads).where(head_predicate).values(**values))
        else:
            connection.execute(
                insert(design_case_heads).values(
                    **self._scope(), case_id=mutation.current_case_ref.id, **values
                )
            )

    def _insert_transition(self, connection: Connection, mutation: WorkspaceMutation) -> None:
        event = mutation.event
        connection.execute(
            insert(transitions).values(
                **self._scope(),
                case_id=event.aggregate_id,
                aggregate_sequence=event.aggregate_sequence,
                event_id=event.event_id,
                case_version=event.aggregate_version,
                event_type=event.event_type,
                actor=event.actor,
                interface_origin=event.interface_origin,
                correlation_id=event.correlation_id,
                idempotency_key=event.idempotency_key,
                input_digest=event.input_digest,
                occurred_at=_parse_time(event.occurred_at),
                event_artifact_id=event.event_ref.id,
                event_artifact_version=event.event_ref.version,
                event_artifact_digest=event.event_ref.digest,
            )
        )

    def _insert_idempotency(self, connection: Connection, mutation: WorkspaceMutation) -> None:
        event = mutation.event
        connection.execute(
            insert(idempotency_records).values(
                **self._scope(),
                idempotency_key=mutation.idempotency_key,
                input_digest=mutation.input_digest,
                result_case_id=mutation.current_case_ref.id,
                result_case_version=mutation.current_case_ref.version,
                result_case_digest=mutation.current_case_ref.digest,
                event_id=event.event_id,
                aggregate_sequence=event.aggregate_sequence,
                created_at=_parse_time(mutation.updated_at),
            )
        )

    def _insert_outbox(self, connection: Connection, mutation: WorkspaceMutation) -> None:
        event = mutation.event
        connection.execute(
            insert(outbox_events).values(
                **self._scope(),
                event_id=event.event_id,
                aggregate_type="design_case",
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
                aggregate_sequence=event.aggregate_sequence,
                event_type=event.event_type,
                payload=event.outbox_document(),
                payload_digest=event.event_ref.digest,
                occurred_at=_parse_time(event.occurred_at),
                available_at=_parse_time(event.occurred_at),
                claimed_by=None,
                claim_expires_at=None,
                delivery_attempts=0,
                delivered_at=None,
                last_error_code=None,
            )
        )

    def _json_document(
        self, connection: Connection, reference: ArtifactReference
    ) -> dict[str, Any]:
        document = connection.scalar(
            select(artifact_versions.c.canonical_document).where(
                self._workspace_predicate(artifact_versions),
                artifact_versions.c.artifact_id == reference.id,
                artifact_versions.c.artifact_version == reference.version,
                artifact_versions.c.digest == reference.digest,
                artifact_versions.c.media_type == reference.media_type,
            )
        )
        if not isinstance(document, dict):
            raise OAKError("OAK-WORKSPACE-CORRUPT", "canonical artifact metadata is missing")
        return document

    def _workspace_row(self, connection: Connection, *, for_update: bool = False) -> dict[str, Any]:
        statement = select(workspaces).where(self._workspace_predicate(workspaces))
        if for_update:
            statement = statement.with_for_update()
        row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            raise OAKError("OAK-WORKSPACE-NOT-FOUND", "workspace was not found")
        return dict(row)

    def _idempotency_row(self, connection: Connection, key: str) -> dict[str, Any] | None:
        row = (
            connection.execute(
                select(idempotency_records).where(
                    self._workspace_predicate(idempotency_records),
                    idempotency_records.c.idempotency_key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    def _check_expected_version(
        self, workspace: dict[str, Any], expected_version: str | None
    ) -> None:
        actual = workspace["current_case_version"]
        if actual != expected_version:
            expected_label = expected_version or "none"
            actual_label = actual or "none"
            raise OAKError(
                "OAK-EXPECTED-VERSION",
                f"expected case version {expected_label} does not match current version "
                f"{actual_label}",
                retriable=True,
            )

    def _validate_artifact(self, artifact: Artifact) -> None:
        if len(artifact.content) > MAXIMUM_ARTIFACT_BYTES:
            raise OAKError("OAK-ARTIFACT-SIZE", "artifact exceeds the local size limit")
        schema_name = KIND_SCHEMA.get(artifact.kind)
        if schema_name is None:
            if artifact.kind != "brief_source":
                raise OAKError("OAK-ARTIFACT-KIND", "artifact kind is not supported")
            return
        document = _json_object(artifact.content, "canonical artifact")
        self._registry.validate(schema_name, document)
        if artifact.kind == "audit_event":
            identity_matches = document["id"] == artifact.id and str(document["sequence"]) == (
                artifact.version
            )
        elif artifact.kind == "component_manifest":
            identity_matches = (
                document.get("id") == artifact.id
                and str(document.get("release", {}).get("version")) == artifact.version
            )
        else:
            identity_matches = (
                document.get("id") == artifact.id
                and str(document.get("version")) == artifact.version
            )
        if not identity_matches:
            raise OAKError(
                "OAK-ARTIFACT-IDENTITY", "artifact metadata does not match canonical content"
            )
        if canonical_json_bytes(document) != artifact.content:
            raise OAKError(
                "OAK-ARTIFACT-NONCANONICAL", "canonical artifact bytes are not normalized"
            )

    def _write_object(self, artifact: Artifact) -> None:
        self._objects.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._objects / self._digest_hex(artifact.digest)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            if path.is_symlink() or path.read_bytes() != artifact.content:
                raise OAKError(
                    "OAK-ARTIFACT-COLLISION", "artifact digest collision detected"
                ) from error
            return
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(artifact.content)
            stream.flush()
            os.fsync(stream.fileno())

    def _read_object(self, digest: str, *, expected_size: int) -> bytes:
        path = self._objects / self._digest_hex(digest)
        if path.is_symlink() or not path.is_file():
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact object is missing")
        if path.stat().st_size != expected_size or expected_size > MAXIMUM_ARTIFACT_BYTES:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact size does not match")
        content = path.read_bytes()
        if content_digest(content) != digest:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact digest does not match")
        return content

    def _scope(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "environment_id": self.environment_id,
            "workspace_id": self.workspace_id,
        }

    def _workspace_predicate(self, table: Any) -> Any:
        return and_(
            table.c.tenant_id == self.tenant_id,
            table.c.environment_id == self.environment_id,
            table.c.workspace_id == self.workspace_id,
        )

    @staticmethod
    def _case_reference(row: dict[str, Any]) -> ArtifactReference:
        return ArtifactReference(
            id=str(row["result_case_id"]),
            version=str(row["result_case_version"]),
            digest=str(row["result_case_digest"]),
            media_type="application/vnd.oak.design-case+json",
        )

    @staticmethod
    def _digest_hex(digest: str) -> str:
        match = OBJECT_DIGEST.fullmatch(digest)
        if match is None:
            raise OAKError("OAK-ARTIFACT-DIGEST", "artifact digest is invalid")
        return match.group(1)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise OAKError("OAK-TIME-INVALID", "timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise OAKError("OAK-ARTIFACT-INVALID", f"{label} is not JSON") from error
    if not isinstance(document, dict):
        raise OAKError("OAK-ARTIFACT-INVALID", f"{label} must be an object")
    return document
