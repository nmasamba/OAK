# SPDX-License-Identifier: Apache-2.0
"""Shared persistent control-plane application facade.

This module composes existing use cases without depending on HTTP or a persistence
implementation. The REST API and worker therefore invoke the same commands as the local CLI.
"""

from __future__ import annotations

import base64
import functools
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from oak.application.candidate_planning import (
    AssuranceResult,
    CandidatePlanningService,
    SelectionResult,
)
from oak.application.context import CommandContext
from oak.application.design_case import (
    CreateCaseResult,
    DesignCaseService,
    DesignResult,
    ModelInterpreterFactory,
)
from oak.application.operations import OperationService, OperationSubmission
from oak.application.recreation import ReplayPlan, replay_plan
from oak.application.report.service import ReportNarratorFactory, ReportResult, ReportService
from oak.application.research import (
    ResearchPlan,
    ResearchReviewResult,
    ResearchService,
    SourceFactory,
    SourceMode,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError, canonical_json_bytes, content_digest
from oak.ports import (
    BriefIntakePort,
    CaseDirectoryPort,
    CataloguePort,
    OutboxLag,
    OutboxStore,
    ProposalLimits,
    ResearchVocabularyPort,
    TargetProfilePort,
    WorkspaceRepository,
)
from oak.ports.report import ReportRendererPort
from oak.ports.research import ResearchRunner

RepositoryFactory = Callable[[str, str], WorkspaceRepository]
OperationServiceFactory = Callable[[str], OperationService]
OutboxStoreFactory = Callable[[str], OutboxStore]
CaseDirectoryFactory = Callable[[str], CaseDirectoryPort]
MAXIMUM_PORTABLE_EXPORT_BYTES = 67_108_864
DIGEST_PATTERN = re.compile(r"^sha256:([a-f0-9]{64})$")


def _case_scoped[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """Answer a case id the server does not hold with the case code, on every interface.

    Each server case is stored as its own workspace, so a well-formed id that names no
    stored case reaches the store, which answers `OAK-WORKSPACE-NOT-FOUND`: the local
    CLI's code for "no workspace here", whose remedy (`oak init`) is wrong for a server.
    A malformed id already answered `OAK-CASE-NOT-FOUND`; this makes a well-formed one
    answer it too, on either store, for REST, MCP and the remote CLI alike.
    """

    @functools.wraps(method)
    def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except OAKError as error:
            if error.code != "OAK-WORKSPACE-NOT-FOUND":
                raise
            raise OAKError("OAK-CASE-NOT-FOUND", "design case was not found") from error

    return scoped


@dataclass(frozen=True, slots=True)
class ArtifactContent:
    reference: ArtifactReference
    kind: str
    content: bytes


# Records only the local release service writes (sign, approve, dispatch, ingest, observe,
# revoke); a server's own export never holds one.
LOCAL_AUTHORITY_KINDS = frozenset(
    {
        "approval",
        "dispatch_envelope",
        "observation_record",
        "plan_signature",
        "revocation_manifest",
        "revocation_notice",
        "runner_message",
    }
)


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
        *,
        model_interpreter_factory: ModelInterpreterFactory | None = None,
        proposal_limits: ProposalLimits | None = None,
        report_renderer: ReportRendererPort | None = None,
        report_narrator_factory: ReportNarratorFactory | None = None,
        oak_version: str = "unknown",
        research_vocabulary: ResearchVocabularyPort | None = None,
        research_source_factory: SourceFactory | None = None,
        research_source_mode: SourceMode | None = None,
        research_runner: ResearchRunner | None = None,
        research_cache: Any = None,
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
        self._model_interpreter_factory = model_interpreter_factory
        self._proposal_limits = proposal_limits
        self._report_renderer = report_renderer
        self._report_narrator_factory = report_narrator_factory
        self._oak_version = oak_version
        self._research_vocabulary = research_vocabulary
        self._research_source_factory = research_source_factory
        self._research_source_mode = research_source_mode
        self._research_runner = research_runner
        self._research_cache = research_cache

    def create_design_case(
        self,
        *,
        original_name: str,
        content: bytes,
        context: CommandContext,
    ) -> CreateCaseResult:
        brief = self._intake.read_content(original_name=original_name, content=content)
        try:
            workspace_id = self._workspace_id(f"design-case.{brief.id.removeprefix('brief.')}")
        except OAKError as error:
            # Every later read reaches a case through this rule, so a case it refuses was
            # created and then unreachable; it is refused here, before anything is stored
            # (F2-5).
            raise OAKError(
                "OAK-INTAKE-IDENTITY",
                "a server design case id is at most 160 characters of lower-case letters, "
                "digits, '.', '_' and '-'; give the brief an id of that form",
            ) from error
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

    @_case_scoped
    def get_design_case(self, case_id: str, *, tenant_id: str) -> DesignResult:
        service = self._design_for_case(case_id, tenant_id)
        result = service.current()
        self._verify_case(case_id, result.case)
        return result

    def list_design_cases(self, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        if self._case_directory_factory is None:
            raise OAKError("OAK-DIRECTORY-UNAVAILABLE", "design-case directory is unavailable")
        return self._case_directory_factory(tenant_id).list_cases()

    @_case_scoped
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

    @_case_scoped
    def resolve_interpreter(self, case_id: str, *, tenant_id: str, interpreter: str) -> str:
        """The mode this case and request will run in; reads only."""

        service = self._design_for_case(case_id, tenant_id)
        self._verify_case(case_id, service.current().case)
        return service.resolve_interpreter(interpreter)

    @_case_scoped
    def interpret(
        self, case_id: str, context: CommandContext, *, interpreter: str = "deterministic"
    ) -> DesignResult:
        service = self._design_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, service.current().case)
        return service.interpret(context, interpreter=interpreter)

    @_case_scoped
    def confirm(
        self,
        case_id: str,
        answers: dict[str, Any],
        context: CommandContext,
    ) -> DesignResult:
        service = self._design_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, service.current().case)
        return service.confirm(answers, context)

    @_case_scoped
    def list_candidates(self, case_id: str, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        planning = self._planning_for_case(case_id, tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=tenant_id).case)
        return planning.list_candidates()

    @_case_scoped
    def architecture(
        self,
        case_id: str,
        *,
        tenant_id: str,
        candidate_id: str | None,
        now: str,
    ) -> dict[str, Any]:
        """The chosen (or named) architecture as one document; reads only, writes nothing."""

        planning = self._planning_for_case(case_id, tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=tenant_id).case)
        return planning.architecture(candidate_id, now=now)

    @staticmethod
    def resolve_narrative(narrative: str) -> str:
        """The narrative mode a report request runs in; reads nothing."""

        return ReportService.resolve_narrative(narrative)

    @_case_scoped
    def record_report(
        self,
        case_id: str,
        context: CommandContext,
        *,
        narrative: str = "deterministic",
    ) -> ReportResult:
        """Record the architecture report beside the case; authorizes nothing."""

        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=context.tenant_id).case)
        return self._report_service(self._workspace_id(case_id), context.tenant_id).record(
            context, narrative=narrative
        )

    @_case_scoped
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

    @_case_scoped
    def create_assurance_plan(
        self,
        case_id: str,
        candidate_id: str,
        context: CommandContext,
    ) -> AssuranceResult:
        planning = self._planning_for_case(case_id, context.tenant_id)
        self._verify_case(case_id, self.get_design_case(case_id, tenant_id=context.tenant_id).case)
        return planning.assure(candidate_id, context)

    @_case_scoped
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

    @_case_scoped
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

    @_case_scoped
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
        # A workspace named otherwise than from its case is a local one: its identity is not
        # the server's, so the case is re-created below rather than restored.
        recreate = self._workspace_id(case_id) != workspace_id
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
        if recreate:
            return self._recreate(replay_plan(manifest, decoded), context)
        # Restored as itself only what a server could have written: a server has no approval,
        # signing, dispatch or runner path, so an export holding their records came from a
        # local workspace whatever its manifest says, and would bring that authority along.
        if {str(entry["kind"]) for entry in manifest["artifact_index"]} & LOCAL_AUTHORITY_KINDS:
            raise OAKError(
                "OAK-IMPORT-AUTHORITY",
                "an export holding approvals, signatures or runner records imports only into "
                "a local workspace",
            )

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

    # ----- research at the point of design (Sprint 14, ADR-0018) ----------------------

    def _recreate(self, plan: ReplayPlan, context: CommandContext) -> DesignResult:
        """Re-create a local export's case through this server's own steps.

        Each step runs under the importing command's actor and tenant, as `import`, with a
        key derived from the import's, so a retried import converges on the same case and
        a step the server refuses stops the replay where it stands.
        """

        def step(name: str, expected_version: str | None) -> CommandContext:
            digest = content_digest(f"{context.idempotency_key}\n{name}".encode())
            return replace(
                context,
                idempotency_key=f"import.{name}.{digest.removeprefix('sha256:')[:32]}",
                expected_version=expected_version,
                interface_origin="import",
            )

        created = self.create_design_case(
            original_name=plan.original_name,
            content=plan.content,
            context=step("create", None),
        )
        case_id = str(created.case["id"])
        service = self._design_for_case(case_id, context.tenant_id)
        result = service.record_recreation(
            plan.origin, step("origin", str(created.case["version"]))
        )
        duplicate = created.duplicate and result.duplicate
        try:
            if plan.interpreted:
                result = self.interpret(case_id, step("interpret", str(result.case["version"])))
                duplicate = duplicate and result.duplicate
            for index, answers in enumerate(plan.rounds, start=1):
                result = self.confirm(
                    case_id,
                    {
                        "answers_version": "0.1.0",
                        "design_case_id": case_id,
                        "answers": list(answers),
                    },
                    step(f"confirm-{index}", str(result.case["version"])),
                )
                duplicate = duplicate and result.duplicate
        except OAKError as error:
            # The case and every step before this one stand, under the server's own records;
            # say how far the replay got rather than only the step's own refusal.
            status = str(service.current().case["status"])
            raise OAKError(
                "OAK-IMPORT-REPLAY",
                f"the case was re-created on the server up to {status}, where the server "
                f"refused the next replayed step ({error.code}); continue it on the server",
                retriable=error.retriable,
            ) from error
        final = service.current()
        return DesignResult(case=final.case, intent=final.intent, duplicate=duplicate)

    @_case_scoped
    def research_plan(self, case_id: str, *, tenant_id: str) -> ResearchPlan:
        return self._research_service(self._workspace_id(case_id), tenant_id).plan()

    @_case_scoped
    def submit_research(
        self, case_id: str, consent: dict[str, Any], context: CommandContext
    ) -> OperationSubmission:
        """Enqueue one consented research run; the worker checks the case again before any request.

        The consent is checked against the plan recomputed from the current intent before
        anything is enqueued, and the run is submitted with one attempt: a timed-out run must
        never send its terms a second time without new consent.
        """

        workspace_id = self._workspace_id(case_id)
        service = self._research_service(workspace_id, context.tenant_id)
        # The documented order (ADR-0018): the capability token (the route's dependency),
        # the consent against the recomputed plan, the idempotent replay and the version,
        # then the status, exactly as :generate-candidates handles its own checks.
        service.check_consent(consent)
        return self._submit(
            kind="research_catalogue",
            case_id=case_id,
            request={
                "consent": {
                    "hosts": sorted(consent["hosts"]),
                    "terms_digest": consent["terms_digest"],
                }
            },
            context=context,
            max_attempts=1,
            check=service.check_state,
        )

    @_case_scoped
    def review_research_item(
        self,
        case_id: str,
        context: CommandContext,
        *,
        item_id: str,
        decision: str,
        rationale: str,
    ) -> ResearchReviewResult:
        service = self._research_service(self._workspace_id(case_id), context.tenant_id)
        self._verify_case(
            case_id, self._require_case(self._repository_for_case(case_id, context.tenant_id))
        )
        return service.review(context, item_id=item_id, decision=decision, rationale=rationale)

    @_case_scoped
    def submit_generate_candidates(
        self, case_id: str, context: CommandContext
    ) -> OperationSubmission:
        return self._submit(
            kind="generate_candidates",
            case_id=case_id,
            request={},
            context=context,
        )

    @_case_scoped
    def submit_evaluate_candidate(
        self, case_id: str, candidate_id: str, context: CommandContext
    ) -> OperationSubmission:
        return self._submit(
            kind="evaluate_candidate",
            case_id=case_id,
            request={"candidate_id": candidate_id},
            context=context,
        )

    @_case_scoped
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
        if kind == "research_catalogue":
            consent = request.get("consent")
            if not isinstance(consent, dict):
                raise OAKError("OAK-OPERATION-DOCUMENT", "operation consent is invalid")
            service = self._research_service(workspace_id, tenant_id)
            return service.run(context, consent=consent).to_document()
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
        max_attempts: int = 3,
        check: Callable[[], Any] | None = None,
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
            if check is not None:
                # A kind-specific check (the research status) runs after the version check
                # and never ahead of an idempotent replay.
                check()

        return self._operation_service_factory(context.tenant_id).submit(
            kind=kind,
            workspace_id=workspace_id,
            case_id=case_id,
            request=request,
            context=context,
            max_attempts=max_attempts,
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
            model_interpreter_factory=self._model_interpreter_factory,
            proposal_limits=self._proposal_limits,
        )

    def _planning_service(self, workspace_id: str, tenant_id: str) -> CandidatePlanningService:
        return CandidatePlanningService(
            self._repository_factory(workspace_id, tenant_id),
            self._catalogue,
            self._target_profiles,
            self._registry,
            research_vocabulary=self._research_vocabulary,
        )

    def _research_service(self, workspace_id: str, tenant_id: str) -> ResearchService:
        if (
            self._research_vocabulary is None
            or self._research_source_factory is None
            or self._research_source_mode is None
            or self._research_runner is None
        ):
            raise OAKError("OAK-RESEARCH-UNAVAILABLE", "research is not configured on this server")
        return ResearchService(
            self._repository_factory(workspace_id, tenant_id),
            self._registry,
            self._catalogue,
            self._research_vocabulary,
            source_factory=self._research_source_factory,
            source_mode=self._research_source_mode,
            runner=self._research_runner,
            cache=self._research_cache,
        )

    def _report_service(self, workspace_id: str, tenant_id: str) -> ReportService:
        return ReportService(
            self._repository_factory(workspace_id, tenant_id),
            self._registry,
            self._report_renderer,
            oak_version=self._oak_version,
            narrator_factory=self._report_narrator_factory,
            proposal_limits=self._proposal_limits,
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
