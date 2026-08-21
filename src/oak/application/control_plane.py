# SPDX-License-Identifier: Apache-2.0
"""Shared persistent control-plane application facade.

This module composes existing use cases without depending on HTTP or a persistence
implementation. The REST API and worker therefore invoke the same commands as the local CLI.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oak.application.candidate_planning import (
    AssuranceResult,
    CandidatePlanningService,
    SelectionResult,
)
from oak.application.context import CommandContext
from oak.application.design_case import CreateCaseResult, DesignCaseService, DesignResult
from oak.application.operations import OperationService, OperationSubmission
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError, canonical_json_bytes, content_digest
from oak.ports import (
    BriefIntakePort,
    CaseDirectoryPort,
    CataloguePort,
    OutboxLag,
    OutboxStore,
    TargetProfilePort,
    WorkspaceRepository,
)

RepositoryFactory = Callable[[str, str], WorkspaceRepository]
OperationServiceFactory = Callable[[str], OperationService]
OutboxStoreFactory = Callable[[str], OutboxStore]
CaseDirectoryFactory = Callable[[str], CaseDirectoryPort]
MAXIMUM_PORTABLE_EXPORT_BYTES = 67_108_864
DIGEST_PATTERN = re.compile(r"^sha256:([a-f0-9]{64})$")


@dataclass(frozen=True, slots=True)
class ArtifactContent:
    reference: ArtifactReference
    kind: str
    content: bytes


class CommunityControlPlane:
    """Tenant-scoped orchestration used by persistent interfaces and workers."""

    def __init__(
        self,
        repository_factory: RepositoryFactory,
        operation_service_factory: OperationServiceFactory,
        intake: BriefIntakePort,
        interpreter: DeterministicBriefInterpreter,
        catalogue: CataloguePort,
        target_profiles: TargetProfilePort,
        registry: SchemaRegistry,
        outbox_store_factory: OutboxStoreFactory | None = None,
        case_directory_factory: CaseDirectoryFactory | None = None,
    ) -> None:
        self._repository_factory = repository_factory
        self._operation_service_factory = operation_service_factory
        self._intake = intake
        self._interpreter = interpreter
        self._catalogue = catalogue
        self._target_profiles = target_profiles
        self._registry = registry
        self._outbox_store_factory = outbox_store_factory
        self._case_directory_factory = case_directory_factory

    def create_design_case(
        self,
        *,
        original_name: str,
        content: bytes,
        context: CommandContext,
    ) -> CreateCaseResult:
        brief = self._intake.read_content(original_name=original_name, content=content)
        workspace_id = f"workspace.{brief.id.removeprefix('brief.')}"
        service = self._design_service(workspace_id, context.tenant_id)
        try:
            service.initialize(
                workspace_id=workspace_id,
                tenant_id=context.tenant_id,
                created_at=context.occurred_at,
            )
        except OAKError as error:
            if error.code != "OAK-WORKSPACE-EXISTS":
                raise
        result = service.create_content(
            original_name=original_name,
            content=content,
            context=context,
        )
        expected_case_id = self._case_id_for_workspace(workspace_id)
        if result.case["id"] != expected_case_id:
            raise OAKError("OAK-CASE-CONFLICT", "workspace contains a different design case")
        return result

    def get_design_case(self, case_id: str, *, tenant_id: str) -> DesignResult:
        service = self._design_for_case(case_id, tenant_id)
        result = service.current()
        self._verify_case(case_id, result.case)
        return result

    def list_design_cases(self, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        if self._case_directory_factory is None:
            raise OAKError("OAK-DIRECTORY-UNAVAILABLE", "design-case directory is unavailable")
        return self._case_directory_factory(tenant_id).list_cases()

    def list_audit_events(self, case_id: str, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        repository = self._repository_for_case(case_id, tenant_id)
        self._verify_case(case_id, self._require_case(repository))
        events: list[dict[str, Any]] = []
        for entry in repository.manifest()["artifact_index"]:
            if str(entry["kind"]) != "audit_event":
                continue
            events.append(
                repository.read_json_artifact(
                    ArtifactReference(
                        id=str(entry["id"]),
                        version=str(entry["version"]),
                        digest=str(entry["digest"]),
                        media_type=str(entry["media_type"]),
                    )
                )
            )
        events.sort(key=lambda event: int(event["sequence"]))
        return tuple(events)

    def interpret(self, case_id: str, context: CommandContext) -> DesignResult:
        service = self._design_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, service.current().case)
        return service.interpret(context)

    def confirm(
        self,
        case_id: str,
        answers: dict[str, Any],
        context: CommandContext,
    ) -> DesignResult:
        service = self._design_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, service.current().case)
        return service.confirm(answers, context)

    def list_candidates(self, case_id: str, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        planning = self._planning_for_case(case_id, tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=tenant_id).case)
        return planning.list_candidates()

    def select_candidate(
        self,
        case_id: str,
        candidate_id: str,
        rationale: str,
        context: CommandContext,
    ) -> SelectionResult:
        planning = self._planning_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=context.tenant_id).case)
        return planning.select(candidate_id, rationale, context)

    def create_assurance_plan(
        self,
        case_id: str,
        candidate_id: str,
        context: CommandContext,
    ) -> AssuranceResult:
        planning = self._planning_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=context.tenant_id).case)
        return planning.assure(candidate_id, context)

    def list_artifacts(self, case_id: str, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        repository = self._repository_for_case(case_id, tenant_id)
        self._verify_case(case_id, self._require_case(repository))
        manifest = repository.manifest()
        return tuple(
            sorted(
                manifest["artifact_index"],
                key=lambda item: (str(item["kind"]), str(item["id"]), str(item["version"])),
            )
        )

    def read_artifact(
        self,
        case_id: str,
        *,
        tenant_id: str,
        artifact_id: str,
        version: str,
        digest: str,
    ) -> ArtifactContent:
        repository = self._repository_for_case(case_id, tenant_id)
        self._verify_case(case_id, self._require_case(repository))
        entry = next(
            (
                item
                for item in repository.manifest()["artifact_index"]
                if item["id"] == artifact_id
                and item["version"] == version
                and item["digest"] == digest
            ),
            None,
        )
        if entry is None:
            raise OAKError("OAK-ARTIFACT-NOT-FOUND", "artifact was not found")
        reference = ArtifactReference(
            id=artifact_id,
            version=version,
            digest=digest,
            media_type=str(entry["media_type"]),
        )
        return ArtifactContent(
            reference=reference,
            kind=str(entry["kind"]),
            content=repository.read_artifact(reference),
        )

    def export_design_case(self, case_id: str, *, tenant_id: str) -> dict[str, Any]:
        repository = self._repository_for_case(case_id, tenant_id)
        self._verify_case(case_id, self._require_case(repository))
        manifest = repository.manifest()
        manifest_bytes = canonical_json_bytes(manifest)
        total = len(manifest_bytes)
        objects: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in manifest["artifact_index"]:
            digest = str(entry["digest"])
            if digest in seen:
                continue
            reference = ArtifactReference(
                id=str(entry["id"]),
                version=str(entry["version"]),
                digest=digest,
                media_type=str(entry["media_type"]),
            )
            content = repository.read_artifact(reference)
            total += len(content)
            if total > MAXIMUM_PORTABLE_EXPORT_BYTES:
                raise OAKError("OAK-EXPORT-SIZE", "canonical export exceeds the size limit")
            objects.append(
                {
                    "digest": digest,
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            )
            seen.add(digest)
        objects.sort(key=lambda item: item["digest"])
        return {
            "export_version": "0.1.0",
            "manifest": manifest,
            "objects": objects,
        }

    def import_design_case(
        self,
        export_document: dict[str, Any],
        *,
        context: CommandContext,
    ) -> DesignResult:
        if len(context.idempotency_key) < 16:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "idempotency key is required")
        if export_document.get("export_version") != "0.1.0":
            raise OAKError("OAK-IMPORT-INVALID", "canonical export version is not supported")
        manifest = export_document.get("manifest")
        encoded_objects = export_document.get("objects")
        if not isinstance(manifest, dict) or not isinstance(encoded_objects, list):
            raise OAKError("OAK-IMPORT-INVALID", "canonical export document is invalid")
        self._registry.validate("workspace-manifest.schema.json", manifest)
        if manifest["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-IMPORT-SCOPE", "import tenant does not match command authority")
        current_reference = manifest.get("current_case_ref")
        if not isinstance(current_reference, dict):
            raise OAKError("OAK-IMPORT-INVALID", "import contains no current design case")
        case_id = str(current_reference["id"])
        workspace_id = str(manifest["id"])
        if self._workspace_id(case_id) != workspace_id:
            raise OAKError("OAK-IMPORT-SCOPE", "import case and workspace do not match")
        expected_digests = {str(entry["digest"]) for entry in manifest["artifact_index"]}
        decoded: dict[str, bytes] = {}
        total = len(canonical_json_bytes(manifest))
        for item in encoded_objects:
            if not isinstance(item, dict) or set(item) != {"digest", "content_base64"}:
                raise OAKError("OAK-IMPORT-INVALID", "canonical export object is invalid")
            digest = item["digest"]
            encoded = item["content_base64"]
            if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest) is None:
                raise OAKError("OAK-IMPORT-DIGEST", "import object digest is invalid")
            if digest in decoded or not isinstance(encoded, str):
                raise OAKError("OAK-IMPORT-INVALID", "canonical export object is duplicated")
            try:
                content = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise OAKError("OAK-IMPORT-INVALID", "import object encoding is invalid") from error
            total += len(content)
            if total > MAXIMUM_PORTABLE_EXPORT_BYTES:
                raise OAKError("OAK-IMPORT-SIZE", "canonical import exceeds the size limit")
            if content_digest(content) != digest:
                raise OAKError("OAK-IMPORT-DIGEST", "import object digest does not match")
            decoded[digest] = content
        if set(decoded) != expected_digests:
            raise OAKError("OAK-IMPORT-INVALID", "canonical export objects are incomplete")

        repository = self._repository_factory(workspace_id, context.tenant_id)
        duplicate = False
        with tempfile.TemporaryDirectory(prefix="oak-api-import-") as temporary_name:
            temporary = Path(temporary_name)
            objects = temporary / "objects" / "sha256"
            objects.mkdir(parents=True, mode=0o700)
            self._write_new_file(temporary / "manifest.json", canonical_json_bytes(manifest))
            for digest, content in decoded.items():
                match = DIGEST_PATTERN.fullmatch(digest)
                if match is None:  # guarded above; retain a local path-safety assertion
                    raise OAKError("OAK-IMPORT-DIGEST", "import object digest is invalid")
                self._write_new_file(objects / match.group(1), content)
            try:
                repository.import_from(temporary)
            except OAKError as error:
                if error.code != "OAK-WORKSPACE-EXISTS":
                    raise
                if repository.manifest() != manifest:
                    raise OAKError(
                        "OAK-IDEMPOTENCY-CONFLICT",
                        "import destination contains different canonical state",
                    ) from error
                duplicate = True
        case = self._require_case(repository)
        self._verify_case(case_id, case)
        intent = None
        if isinstance(case.get("intent_ref"), dict):
            intent = repository.read_json_artifact(
                ArtifactReference.from_document(case["intent_ref"])
            )
        return DesignResult(case=case, intent=intent, duplicate=duplicate)

    def submit_generate_candidates(
        self, case_id: str, context: CommandContext
    ) -> OperationSubmission:
        return self._submit(
            kind="generate_candidates",
            case_id=case_id,
            request={},
            context=context,
        )

    def submit_evaluate_candidate(
        self, case_id: str, candidate_id: str, context: CommandContext
    ) -> OperationSubmission:
        return self._submit(
            kind="evaluate_candidate",
            case_id=case_id,
            request={"candidate_id": candidate_id},
            context=context,
        )

    def submit_compile_bundle(
        self,
        case_id: str,
        candidate_id: str,
        target: dict[str, Any],
        context: CommandContext,
    ) -> OperationSubmission:
        validated_target = self._target_profiles.validate_document(target)
        return self._submit(
            kind="compile_bundle",
            case_id=case_id,
            request={"candidate_id": candidate_id, "target": validated_target},
            context=context,
        )

    def get_operation(self, operation_id: str, *, tenant_id: str) -> Any:
        return self._operation_service_factory(tenant_id).get(operation_id)

    def cancel_operation(self, operation_id: str, *, context: CommandContext) -> Any:
        return self._operation_service_factory(context.tenant_id).cancel(
            operation_id, context=context
        )

    def outbox_lag(self, *, tenant_id: str) -> OutboxLag:
        if self._outbox_store_factory is None:
            raise OAKError("OAK-OUTBOX-UNAVAILABLE", "outbox observation is unavailable")
        return self._outbox_store_factory(tenant_id).lag(projection_name="design-case-index")

    def execute_operation(self, document: dict[str, Any]) -> dict[str, Any]:
        """Execute one persisted, typed compiler operation under a worker lease."""

        try:
            kind = str(document["kind"])
            workspace_id = str(document["workspace_id"])
            case_id = str(document["case_id"])
            tenant_id = str(document["tenant_id"])
            request = document["request"]
            context = CommandContext(
                actor=str(document["actor"]),
                tenant_id=tenant_id,
                idempotency_key=str(document["idempotency_key"]),
                expected_version=(
                    str(document["expected_version"])
                    if document["expected_version"] is not None
                    else None
                ),
                correlation_id=str(document["correlation_id"]),
                interface_origin=str(document["interface_origin"]),
                occurred_at=str(document["occurred_at"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise OAKError("OAK-OPERATION-DOCUMENT", "operation document is invalid") from error
        if not isinstance(request, dict):
            raise OAKError("OAK-OPERATION-DOCUMENT", "operation request is invalid")
        expected_workspace = self._workspace_id(case_id)
        if workspace_id != expected_workspace:
            raise OAKError("OAK-OPERATION-SCOPE", "operation workspace does not match its case")
        planning = self._planning_service(workspace_id, tenant_id)
        if kind == "generate_candidates":
            return planning.candidates(context).to_document()
        candidate_id = request.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise OAKError("OAK-OPERATION-DOCUMENT", "operation candidate is invalid")
        if kind == "evaluate_candidate":
            return planning.evaluate(candidate_id, context).to_document()
        target = request.get("target")
        if kind == "compile_bundle" and isinstance(target, dict):
            return planning.plan_document(candidate_id, target, context).to_document()
        raise OAKError("OAK-OPERATION-KIND", "operation kind is not supported")

    def _submit(
        self,
        *,
        kind: str,
        case_id: str,
        request: dict[str, Any],
        context: CommandContext,
    ) -> OperationSubmission:
        workspace_id = self._workspace_id(case_id)
        repository = self._repository_factory(workspace_id, context.tenant_id)

        def verify_precondition() -> None:
            case = self._require_case(repository)
            self._verify_case(case_id, case)
            if context.expected_version != case["version"]:
                raise OAKError(
                    "OAK-EXPECTED-VERSION",
                    "expected case version does not match current version",
                    retriable=True,
                )

        return self._operation_service_factory(context.tenant_id).submit(
            kind=kind,
            workspace_id=workspace_id,
            case_id=case_id,
            request=request,
            context=context,
            precondition=verify_precondition,
        )

    def _design_for_case(self, case_id: str, tenant_id: str) -> DesignCaseService:
        return self._design_service(self._workspace_id(case_id), tenant_id)

    def _planning_for_case(self, case_id: str, tenant_id: str) -> CandidatePlanningService:
        return self._planning_service(self._workspace_id(case_id), tenant_id)

    def _repository_for_case(self, case_id: str, tenant_id: str) -> WorkspaceRepository:
        return self._repository_factory(self._workspace_id(case_id), tenant_id)

    def _design_service(self, workspace_id: str, tenant_id: str) -> DesignCaseService:
        return DesignCaseService(
            self._repository_factory(workspace_id, tenant_id),
            self._intake,
            self._interpreter,
            self._registry,
        )

    def _planning_service(self, workspace_id: str, tenant_id: str) -> CandidatePlanningService:
        return CandidatePlanningService(
            self._repository_factory(workspace_id, tenant_id),
            self._catalogue,
            self._target_profiles,
            self._registry,
        )

    @staticmethod
    def _workspace_id(case_id: str) -> str:
        if not case_id.startswith("design-case.") or len(case_id) > 160:
            raise OAKError("OAK-CASE-NOT-FOUND", "design case was not found")
        suffix = case_id.removeprefix("design-case.")
        if not suffix or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in suffix
        ):
            raise OAKError("OAK-CASE-NOT-FOUND", "design case was not found")
        return f"workspace.{suffix}"

    @staticmethod
    def _case_id_for_workspace(workspace_id: str) -> str:
        return f"design-case.{workspace_id.removeprefix('workspace.')}"

    @staticmethod
    def _require_case(repository: WorkspaceRepository) -> dict[str, Any]:
        case = repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "design case was not found")
        return case

    @staticmethod
    def _verify_case(case_id: str, case: dict[str, Any]) -> None:
        if case.get("id") != case_id:
            raise OAKError("OAK-CASE-NOT-FOUND", "design case was not found")

    @staticmethod
    def _write_new_file(path: Path, content: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
