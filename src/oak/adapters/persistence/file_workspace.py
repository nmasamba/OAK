# SPDX-License-Identifier: Apache-2.0
"""Atomic file-backed Community workspace repository."""

import fcntl
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from oak.contracts import SchemaRegistry, load_json_document
from oak.domain import OAKError
from oak.domain.artifacts import Artifact, ArtifactReference, canonical_json_bytes, content_digest
from oak.ports.workspace import WorkspaceCommit, WorkspaceMutation

OBJECT_DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")
MAXIMUM_ARTIFACT_BYTES = 8_388_608
KIND_SCHEMA = {
    "source_record": "source-record.schema.json",
    "system_intent": "system-intent.schema.json",
    "design_case": "design-case.schema.json",
    "audit_event": "audit-event.schema.json",
}
JSON_MEDIA_KIND = {
    "application/vnd.oak.source-record+json": "source_record",
    "application/vnd.oak.system-intent+json": "system_intent",
    "application/vnd.oak.design-case+json": "design_case",
    "application/vnd.oak.audit-event+json": "audit_event",
}
ReplaceFile = Callable[[Path, Path], None]


def _replace_path(source: Path, destination: Path) -> None:
    os.replace(source, destination)


class FileWorkspaceRepository:
    """Store immutable objects before atomically replacing one manifest pointer."""

    def __init__(
        self,
        root: Path,
        registry: SchemaRegistry,
        *,
        replace_file: ReplaceFile = _replace_path,
    ) -> None:
        self.root = root
        self.control = root / ".oak"
        self.objects = self.control / "objects" / "sha256"
        self.manifest_path = self.control / "manifest.json"
        self.lock_path = self.control / "workspace.lock"
        self._registry = registry
        self._replace_file = replace_file

    @staticmethod
    def discover(start: Path) -> Path:
        candidate = start.resolve()
        for directory in (candidate, *candidate.parents):
            if (directory / ".oak" / "manifest.json").is_file():
                return directory
        raise OAKError("OAK-WORKSPACE-NOT-FOUND", "no OAK workspace found")

    def initialize(self, *, workspace_id: str, tenant_id: str, created_at: str) -> None:
        if self.root.exists() and self.root.is_symlink():
            raise OAKError("OAK-WORKSPACE-UNSAFE-PATH", "workspace root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.control.is_symlink() or self.control.exists():
            raise OAKError("OAK-WORKSPACE-EXISTS", "workspace is already initialized")
        temporary = Path(tempfile.mkdtemp(prefix=".oak.tmp-", dir=self.root))
        try:
            (temporary / "objects" / "sha256").mkdir(parents=True, mode=0o700)
            manifest = {
                "schema_version": "0.4.0",
                "id": workspace_id,
                "version": 0,
                "tenant_id": tenant_id,
                "created_at": created_at,
                "updated_at": created_at,
                "current_case_ref": None,
                "artifact_index": [],
                "audit_events": [],
                "idempotency_records": [],
                "extensions": {},
            }
            self._validate_manifest(manifest)
            self._write_new_file(temporary / "manifest.json", canonical_json_bytes(manifest))
            self._replace_file(temporary, self.control)
            self._fsync_directory(self.root)
        except FileExistsError as error:
            raise OAKError("OAK-WORKSPACE-EXISTS", "workspace is already initialized") from error
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def manifest(self) -> dict[str, Any]:
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise OAKError("OAK-WORKSPACE-NOT-FOUND", "workspace manifest is missing")
        try:
            if self.manifest_path.stat().st_size > MAXIMUM_ARTIFACT_BYTES:
                raise ValueError("workspace manifest exceeds the local size limit")
            document = load_json_document(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "workspace manifest is invalid") from error
        if not isinstance(document, dict):
            raise OAKError("OAK-WORKSPACE-CORRUPT", "workspace manifest must be an object")
        try:
            self._validate_manifest(document)
            self._validate_workspace_lineage(document)
        except Exception as error:
            raise OAKError(
                "OAK-WORKSPACE-CORRUPT", "workspace manifest failed validation"
            ) from error
        return document

    def current_case(self) -> dict[str, Any] | None:
        reference = self.manifest()["current_case_ref"]
        if reference is None:
            return None
        return self.read_json_artifact(ArtifactReference.from_document(reference))

    def read_artifact(self, reference: ArtifactReference) -> bytes:
        return self._read_object(reference.digest)

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
        manifest = self.manifest()
        for record in manifest["idempotency_records"]:
            if record["key"] != key:
                continue
            if record["input_digest"] != input_digest:
                raise OAKError(
                    "OAK-IDEMPOTENCY-CONFLICT",
                    "idempotency key was already used for different input",
                )
            return self.read_json_artifact(
                ArtifactReference.from_document(record["result_case_ref"])
            )
        return None

    def commit(self, mutation: WorkspaceMutation) -> WorkspaceCommit:
        with self._lock():
            manifest = self.manifest()
            duplicate = self._idempotent_result(manifest, mutation)
            if duplicate is not None:
                return WorkspaceCommit(case_document=duplicate, duplicate=True)
            self._check_expected_version(manifest, mutation.expected_case_version)
            self._validate_mutation(manifest, mutation)
            for artifact in mutation.artifacts:
                self._write_object(artifact)
            updated = self._updated_manifest(manifest, mutation)
            self._validate_manifest(updated)
            self._atomic_manifest_write(updated)
            return WorkspaceCommit(
                case_document=self.read_json_artifact(mutation.current_case_ref),
                duplicate=False,
            )

    def export_to(self, destination: Path) -> None:
        if destination.exists():
            raise OAKError("OAK-EXPORT-EXISTS", "export destination already exists")
        destination_parent = destination.parent.resolve()
        destination_parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            manifest = self.manifest()
            self._validate_indexed_objects(manifest)
            self._validate_workspace_lineage(manifest)
            temporary = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination_parent)
            )
            try:
                export_objects = temporary / "objects" / "sha256"
                export_objects.mkdir(parents=True, mode=0o700)
                self._write_new_file(temporary / "manifest.json", canonical_json_bytes(manifest))
                for entry in manifest["artifact_index"]:
                    digest = str(entry["digest"])
                    self._write_new_file(
                        export_objects / self._digest_hex(digest), self._read_object(digest)
                    )
                self._replace_file(temporary, destination)
                self._fsync_directory(destination_parent)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)

    def import_from(self, source: Path) -> None:
        if self.control.is_symlink() or self.control.exists():
            raise OAKError("OAK-WORKSPACE-EXISTS", "workspace is already initialized")
        if self.root.exists() and self.root.is_symlink():
            raise OAKError("OAK-WORKSPACE-UNSAFE-PATH", "workspace root cannot be a symlink")
        if source.is_symlink() or not source.is_dir():
            raise OAKError("OAK-IMPORT-UNSAFE-PATH", "import source must be a regular directory")
        source_objects = source / "objects"
        source_digests = source_objects / "sha256"
        if (
            source_objects.is_symlink()
            or source_digests.is_symlink()
            or not source_digests.is_dir()
        ):
            raise OAKError("OAK-IMPORT-UNSAFE-PATH", "import object store is unsafe")
        source_manifest = source / "manifest.json"
        if source_manifest.is_symlink() or not source_manifest.is_file():
            raise OAKError("OAK-IMPORT-INVALID", "import manifest is missing")
        try:
            if source_manifest.stat().st_size > MAXIMUM_ARTIFACT_BYTES:
                raise ValueError("import manifest exceeds the local size limit")
            manifest = load_json_document(source_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise OAKError("OAK-IMPORT-INVALID", "import manifest is invalid") from error
        if not isinstance(manifest, dict):
            raise OAKError("OAK-IMPORT-INVALID", "import manifest must be an object")
        try:
            self._validate_manifest(manifest)
        except Exception as error:
            raise OAKError("OAK-IMPORT-INVALID", "import manifest failed validation") from error

        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = Path(tempfile.mkdtemp(prefix=".oak.tmp-", dir=self.root))
        try:
            imported_objects = temporary / "objects" / "sha256"
            imported_objects.mkdir(parents=True, mode=0o700)
            for entry in manifest["artifact_index"]:
                digest = str(entry["digest"])
                source_object = source_digests / self._digest_hex(digest)
                if source_object.is_symlink() or not source_object.is_file():
                    raise OAKError("OAK-IMPORT-INVALID", "an indexed import object is missing")
                if source_object.stat().st_size != int(entry["size_bytes"]):
                    raise OAKError("OAK-IMPORT-INVALID", "an imported object size does not match")
                content = source_object.read_bytes()
                if content_digest(content) != digest:
                    raise OAKError("OAK-IMPORT-DIGEST", "an imported object digest does not match")
                self._write_new_file(imported_objects / self._digest_hex(digest), content)
            self._write_new_file(temporary / "manifest.json", canonical_json_bytes(manifest))
            self._validate_export_tree(temporary, manifest)
            self._replace_file(temporary, self.control)
            self._fsync_directory(self.root)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        self._registry.validate("workspace-manifest.schema.json", manifest)
        keys = [str(record["key"]) for record in manifest["idempotency_records"]]
        if len(keys) != len(set(keys)):
            raise ValueError("idempotency keys must be unique")
        identities = [
            (str(entry["id"]), str(entry["version"])) for entry in manifest["artifact_index"]
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("artifact id/version pairs must be unique")
        revision = int(manifest["version"])
        if len(manifest["audit_events"]) != revision:
            raise ValueError("audit sequence must equal workspace revision")
        if len(manifest["idempotency_records"]) != revision:
            raise ValueError("every workspace revision must have one idempotency record")
        indexed: dict[tuple[str, str], dict[str, Any]] = {
            (str(entry["id"]), str(entry["version"])): entry for entry in manifest["artifact_index"]
        }
        references: list[tuple[dict[str, Any], str]] = [
            (reference, "audit_event") for reference in manifest["audit_events"]
        ]
        if manifest["current_case_ref"] is not None:
            references.append((manifest["current_case_ref"], "design_case"))
        for record in manifest["idempotency_records"]:
            references.extend(
                ((record["result_case_ref"], "design_case"), (record["event_ref"], "audit_event"))
            )
        for reference, expected_kind in references:
            self._require_indexed_reference(indexed, reference, expected_kind)

    def _validate_mutation(self, manifest: dict[str, Any], mutation: WorkspaceMutation) -> None:
        artifacts = {artifact.digest: artifact for artifact in mutation.artifacts}
        case_artifact = artifacts.get(mutation.current_case_ref.digest)
        event_artifact = artifacts.get(mutation.event_ref.digest)
        if case_artifact is None or case_artifact.kind != "design_case":
            raise OAKError("OAK-WORKSPACE-MUTATION", "mutation is missing its case artifact")
        if event_artifact is None or event_artifact.kind != "audit_event":
            raise OAKError("OAK-WORKSPACE-MUTATION", "mutation is missing its audit event")
        for artifact in mutation.artifacts:
            self._validate_artifact(artifact)
        event = json.loads(event_artifact.content)
        expected_sequence = len(manifest["audit_events"]) + 1
        if event["sequence"] != expected_sequence:
            raise OAKError("OAK-AUDIT-SEQUENCE", "audit event sequence is not contiguous")
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        if event["previous_event_digest"] != previous:
            raise OAKError("OAK-AUDIT-LINEAGE", "audit event does not extend the current head")
        case = json.loads(case_artifact.content)
        if case["audit_head"] != mutation.event_ref.digest:
            raise OAKError("OAK-AUDIT-LINEAGE", "case audit head does not match its event")
        if event["case_id"] != case["id"] or event["case_version"] != case["version"]:
            raise OAKError("OAK-AUDIT-LINEAGE", "audit event result does not match its case")

    def _validate_artifact(self, artifact: Artifact) -> None:
        schema_name = KIND_SCHEMA.get(artifact.kind)
        if schema_name is None:
            if artifact.kind != "brief_source":
                raise OAKError("OAK-ARTIFACT-KIND", "artifact kind is not supported")
            return
        try:
            document = json.loads(artifact.content)
        except json.JSONDecodeError as error:
            raise OAKError("OAK-ARTIFACT-INVALID", "canonical artifact is not JSON") from error
        if not isinstance(document, dict):
            raise OAKError("OAK-ARTIFACT-INVALID", "canonical artifact must be an object")
        self._registry.validate(schema_name, document)
        if artifact.kind == "audit_event":
            identity_matches = document["id"] == artifact.id and str(document["sequence"]) == (
                artifact.version
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

    def _updated_manifest(
        self, manifest: dict[str, Any], mutation: WorkspaceMutation
    ) -> dict[str, Any]:
        indexed = [*manifest["artifact_index"]]
        known = {(entry["id"], entry["version"]): entry for entry in indexed}
        for artifact in mutation.artifacts:
            identity = (artifact.id, artifact.version)
            existing = known.get(identity)
            if existing is not None and existing["digest"] != artifact.digest:
                raise OAKError(
                    "OAK-ARTIFACT-IMMUTABLE",
                    "an immutable artifact version already has different content",
                )
            if existing is None:
                entry = artifact.index_document()
                indexed.append(entry)
                known[identity] = entry
        indexed.sort(key=lambda item: (str(item["kind"]), str(item["id"]), str(item["version"])))
        return {
            **manifest,
            "version": int(manifest["version"]) + 1,
            "updated_at": mutation.updated_at,
            "current_case_ref": mutation.current_case_ref.to_document(),
            "artifact_index": indexed,
            "audit_events": [*manifest["audit_events"], mutation.event_ref.to_document()],
            "idempotency_records": [
                *manifest["idempotency_records"],
                {
                    "key": mutation.idempotency_key,
                    "input_digest": mutation.input_digest,
                    "result_case_ref": mutation.current_case_ref.to_document(),
                    "event_ref": mutation.event_ref.to_document(),
                },
            ],
        }

    def _idempotent_result(
        self, manifest: dict[str, Any], mutation: WorkspaceMutation
    ) -> dict[str, Any] | None:
        for record in manifest["idempotency_records"]:
            if record["key"] != mutation.idempotency_key:
                continue
            if record["input_digest"] != mutation.input_digest:
                raise OAKError(
                    "OAK-IDEMPOTENCY-CONFLICT",
                    "idempotency key was already used for different input",
                )
            reference = ArtifactReference.from_document(record["result_case_ref"])
            return self.read_json_artifact(reference)
        return None

    def _check_expected_version(
        self, manifest: dict[str, Any], expected_version: str | None
    ) -> None:
        current = manifest["current_case_ref"]
        actual = str(current["version"]) if isinstance(current, dict) else None
        if actual != expected_version:
            expected_label = expected_version or "none"
            actual_label = actual or "none"
            raise OAKError(
                "OAK-EXPECTED-VERSION",
                f"expected case version {expected_label} does not match "
                f"current version {actual_label}",
                retriable=True,
            )

    def _write_object(self, artifact: Artifact) -> None:
        if len(artifact.content) > MAXIMUM_ARTIFACT_BYTES:
            raise OAKError("OAK-ARTIFACT-SIZE", "artifact exceeds the local size limit")
        path = self.objects / self._digest_hex(artifact.digest)
        if path.exists():
            if path.read_bytes() != artifact.content:
                raise OAKError("OAK-ARTIFACT-COLLISION", "artifact digest collision detected")
            return
        self._write_new_file(path, artifact.content)
        self._fsync_directory(self.objects)

    def _read_object(self, digest: str) -> bytes:
        path = self.objects / self._digest_hex(digest)
        if path.is_symlink() or not path.is_file():
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact object is missing")
        if path.stat().st_size > MAXIMUM_ARTIFACT_BYTES:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact exceeds size limit")
        content = path.read_bytes()
        if content_digest(content) != digest:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact digest does not match")
        return content

    def _validate_indexed_objects(self, manifest: dict[str, Any]) -> None:
        for entry in manifest["artifact_index"]:
            content = self._read_object(str(entry["digest"]))
            if len(content) != int(entry["size_bytes"]):
                raise OAKError("OAK-WORKSPACE-CORRUPT", "indexed artifact size does not match")
            artifact = Artifact(
                id=str(entry["id"]),
                version=str(entry["version"]),
                kind=str(entry["kind"]),
                media_type=str(entry["media_type"]),
                content=content,
            )
            self._validate_artifact(artifact)

    def _validate_export_tree(self, control: Path, manifest: dict[str, Any]) -> None:
        original_control = self.control
        original_objects = self.objects
        original_manifest = self.manifest_path
        try:
            self.control = control
            self.objects = control / "objects" / "sha256"
            self.manifest_path = control / "manifest.json"
            self._validate_indexed_objects(manifest)
            self._validate_workspace_lineage(manifest)
        finally:
            self.control = original_control
            self.objects = original_objects
            self.manifest_path = original_manifest

    def _validate_workspace_lineage(self, manifest: dict[str, Any]) -> None:
        indexed = {
            (str(entry["id"]), str(entry["version"])): entry for entry in manifest["artifact_index"]
        }
        previous_digest: str | None = None
        events: dict[tuple[str, str], dict[str, Any]] = {}
        for sequence, reference_document in enumerate(manifest["audit_events"], start=1):
            self._require_indexed_reference(indexed, reference_document, "audit_event")
            reference = ArtifactReference.from_document(reference_document)
            event = self.read_json_artifact(reference)
            if event["sequence"] != sequence or event["previous_event_digest"] != previous_digest:
                raise OAKError("OAK-AUDIT-LINEAGE", "export audit lineage is not contiguous")
            if event["tenant_id"] != manifest["tenant_id"]:
                raise OAKError("OAK-AUDIT-LINEAGE", "export audit tenant does not match")
            result = event["result"]
            if (
                result["case_id"] != event["case_id"]
                or result["case_version"] != event["case_version"]
            ):
                raise OAKError("OAK-AUDIT-LINEAGE", "audit result does not match its event")
            for field, kind in (
                ("intent_ref", "system_intent"),
                ("source_record_ref", "source_record"),
            ):
                nested_reference = result[field]
                if nested_reference is not None:
                    self._require_indexed_reference(indexed, nested_reference, kind)
            intent_reference = result["intent_ref"]
            source_reference = result["source_record_ref"]
            if source_reference is not None:
                source = self.read_json_artifact(ArtifactReference.from_document(source_reference))
                content_entry = self._require_indexed_reference(
                    indexed, source["content_ref"], "brief_source"
                )
                if source["size_bytes"] != content_entry["size_bytes"]:
                    raise OAKError(
                        "OAK-AUDIT-LINEAGE", "source record size does not match source artifact"
                    )
            if intent_reference is not None:
                intent = self.read_json_artifact(ArtifactReference.from_document(intent_reference))
                linked_source = intent["extensions"].get("oak.community/source_record")
                if linked_source != source_reference:
                    raise OAKError(
                        "OAK-AUDIT-LINEAGE", "intent source does not match its audit result"
                    )
            events[(reference.id, reference.version)] = event
            previous_digest = reference.digest

        current_reference_document = manifest["current_case_ref"]
        if current_reference_document is not None:
            self._require_indexed_reference(indexed, current_reference_document, "design_case")
            current = self.read_json_artifact(
                ArtifactReference.from_document(current_reference_document)
            )
            if (
                current["tenant_id"] != manifest["tenant_id"]
                or current["audit_head"] != previous_digest
            ):
                raise OAKError("OAK-AUDIT-LINEAGE", "current case does not match audit head")
            if manifest["audit_events"]:
                last_reference = manifest["audit_events"][-1]
                last_event = events[(str(last_reference["id"]), str(last_reference["version"]))]
                if (last_event["case_id"], last_event["case_version"]) != (
                    current["id"],
                    current["version"],
                ):
                    raise OAKError("OAK-AUDIT-LINEAGE", "current case does not match last event")
            for reference in current["brief_refs"]:
                self._require_indexed_reference(indexed, reference, "brief_source")
            if current["intent_ref"] is not None:
                self._require_indexed_reference(indexed, current["intent_ref"], "system_intent")
                if (
                    manifest["audit_events"]
                    and current["intent_ref"] != last_event["result"]["intent_ref"]
                ):
                    raise OAKError(
                        "OAK-AUDIT-LINEAGE", "current case intent does not match last event"
                    )

        for record in manifest["idempotency_records"]:
            event_reference = record["event_ref"]
            idempotency_event = events.get(
                (str(event_reference["id"]), str(event_reference["version"]))
            )
            if idempotency_event is None or (
                idempotency_event["idempotency_key"],
                idempotency_event["input_digest"],
            ) != (
                record["key"],
                record["input_digest"],
            ):
                raise OAKError("OAK-AUDIT-LINEAGE", "idempotency record does not match event")
            case_reference = record["result_case_ref"]
            case = self.read_json_artifact(ArtifactReference.from_document(case_reference))
            if (case["id"], case["version"], case["audit_head"]) != (
                idempotency_event["case_id"],
                idempotency_event["case_version"],
                event_reference["digest"],
            ):
                raise OAKError("OAK-AUDIT-LINEAGE", "idempotency result does not match event")

    @staticmethod
    def _require_indexed_reference(
        indexed: dict[tuple[str, str], dict[str, Any]],
        reference: dict[str, Any],
        expected_kind: str,
    ) -> dict[str, Any]:
        indexed_entry = indexed.get((str(reference["id"]), str(reference["version"])))
        if (
            indexed_entry is None
            or any(
                indexed_entry[field] != reference[field]
                for field in ("id", "version", "media_type", "digest")
            )
            or indexed_entry["kind"] != expected_kind
        ):
            raise ValueError("manifest reference must match an indexed artifact")
        return indexed_entry

    def _atomic_manifest_write(self, manifest: dict[str, Any]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="manifest.", suffix=".tmp", dir=self.control
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(manifest))
                stream.flush()
                os.fsync(stream.fileno())
            self._replace_file(temporary, self.manifest_path)
            self._fsync_directory(self.control)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_new_file(path: Path, content: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def _lock(self) -> Iterator[None]:
        if self.control.is_symlink() or not self.control.is_dir():
            raise OAKError("OAK-WORKSPACE-NOT-FOUND", "workspace is not initialized")
        if self.lock_path.is_symlink():
            raise OAKError("OAK-WORKSPACE-CORRUPT", "workspace lock path is unsafe")
        with self.lock_path.open("a+b") as stream:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _digest_hex(digest: str) -> str:
        match = OBJECT_DIGEST.fullmatch(digest)
        if match is None:
            raise OAKError("OAK-ARTIFACT-DIGEST", "artifact digest is invalid")
        return match.group(1)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
