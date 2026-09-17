# SPDX-License-Identifier: Apache-2.0
"""Shared local DesignCase application operations."""

import copy
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.compiler import (
    DeterministicBriefInterpreter,
    validate_interpretation_proposal,
    verify_intent_provenance,
)
from oak.compiler.interpretation import MODEL_PROPOSED
from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    DesignCase,
    DesignCaseStatus,
    IngestedBrief,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.design_case import next_patch_version
from oak.ports import (
    BriefIntakePort,
    ModelInterpreterPort,
    ProposalLimits,
    WorkspaceRepository,
)

CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
INTENT_MEDIA_TYPE = "application/vnd.oak.system-intent+json"
SOURCE_MEDIA_TYPE = "application/vnd.oak.source-record+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"
PROPOSAL_MEDIA_TYPE = "application/vnd.oak.interpretation-proposal+json"
INTERPRETER_MODES = ("auto", "model", "deterministic")
STRUCTURED_FORMATS = frozenset({"yaml", "json"})
# Extension keys. Everything model-specific exists only when the model path ran, so a
# workspace with no model configured produces exactly the documents it produced before.
SOURCE_RECORD_EXTENSION = "oak.community/source_record"
SOURCE_ARTIFACT_REF_EXTENSION = "oak.community/artifact_ref"
PROPOSAL_REF_EXTENSION = "oak.community/interpretation_proposal_ref"
INTERPRETER_EXTENSION = "oak.community/interpreter"
MODEL_EXTENSION = "oak.community/model"
ModelInterpreterFactory = Callable[[], ModelInterpreterPort | None]


@dataclass(frozen=True, slots=True)
class CreateCaseResult:
    case: dict[str, Any]
    duplicate: bool


@dataclass(frozen=True, slots=True)
class DesignResult:
    case: dict[str, Any]
    intent: dict[str, Any] | None
    duplicate: bool
    interpreter: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionResult:
    case_id: str
    case_version: str
    status: str
    questions: tuple[dict[str, Any], ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_version": self.case_version,
            "status": self.status,
            "questions": list(self.questions),
        }


class DesignCaseService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        intake: BriefIntakePort,
        interpreter: DeterministicBriefInterpreter,
        registry: SchemaRegistry,
        *,
        model_interpreter_factory: ModelInterpreterFactory | None = None,
        proposal_limits: ProposalLimits | None = None,
    ) -> None:
        self._repository = repository
        self._intake = intake
        self._interpreter = interpreter
        self._registry = registry
        self._model_interpreter_factory = model_interpreter_factory
        self._proposal_limits = proposal_limits or ProposalLimits()

    def initialize(self, *, workspace_id: str, tenant_id: str, created_at: str) -> None:
        self._repository.initialize(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            created_at=created_at,
        )

    def design(
        self, brief_path: Path, context: CommandContext, *, interpreter: str = "auto"
    ) -> DesignResult:
        brief = self._intake.read(brief_path)
        create_identity = context.idempotency_key or content_digest(brief.content)
        create_context = replace(
            context,
            idempotency_key=(
                f"create:{hashlib.sha256(create_identity.encode('utf-8')).hexdigest()}"
            ),
            expected_version=None,
        )
        created = self._create_brief(brief, create_context)
        return self.interpret(
            replace(context, expected_version=str(created.case["version"])),
            interpreter=interpreter,
        )

    def create_content(
        self,
        *,
        original_name: str,
        content: bytes,
        context: CommandContext,
    ) -> CreateCaseResult:
        brief = self._intake.read_content(original_name=original_name, content=content)
        return self._create_brief(brief, context)

    def _create_brief(self, brief: IngestedBrief, context: CommandContext) -> CreateCaseResult:
        input_digest = self._request_digest(
            context,
            {
                "brief_id": brief.id,
                "brief_version": brief.version,
                "format": brief.format,
                "original_name": brief.original_name,
                "content_digest": content_digest(brief.content),
            },
        )
        context = self._normalized_context(context, "create", input_digest)
        self._check_context(context)
        manifest = self._repository.manifest()
        if manifest["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
        duplicate_case = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate_case is not None:
            return CreateCaseResult(case=duplicate_case, duplicate=True)
        raw_artifact = Artifact(
            id=brief.id,
            version=brief.version,
            kind="brief_source",
            media_type=brief.media_type,
            content=brief.content,
        )
        source_id = self._derived_id("source", brief.id)
        source_document = {
            "schema_version": "0.4.0",
            "id": source_id,
            "version": "0.1.0",
            "created_at": context.occurred_at,
            "trust": "untrusted",
            "format": brief.format,
            "original_name": brief.original_name,
            "content_ref": raw_artifact.reference.to_document(),
            "size_bytes": len(brief.content),
            "normalization": {"unicode": "NFC", "line_endings": "LF"},
            "extensions": {},
        }
        self._registry.validate("source-record.schema.json", source_document)
        source_artifact = json_artifact(
            artifact_id=source_id,
            version="0.1.0",
            kind="source_record",
            media_type=SOURCE_MEDIA_TYPE,
            document=source_document,
        )

        case_id = self._derived_id("design-case", brief.id)
        case = DesignCase(
            id=case_id,
            version="0.1.0",
            status=DesignCaseStatus.DRAFT,
            title=brief.title,
            tenant_id=context.tenant_id,
            created_at=context.occurred_at,
            updated_at=context.occurred_at,
            interface_origin=context.interface_origin,
            brief_refs=(raw_artifact.reference,),
            extensions={"oak.community/source_record_ref": source_artifact.reference.to_document()},
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=case.id,
            case_version=case.version,
            event_type="case_created",
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=None,
            source_record_ref=source_artifact.reference,
        )
        event_artifact = self._audit_artifact(event_document, sequence)
        case = case.with_audit_head(event_artifact.digest)
        case_artifact = self._case_artifact(case)
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(
                    raw_artifact,
                    source_artifact,
                    event_artifact,
                    case_artifact,
                ),
                current_case_ref=case_artifact.reference,
                event_artifact=event_artifact,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        return CreateCaseResult(case=committed.case_document, duplicate=committed.duplicate)

    def resolve_interpreter(self, interpreter: str = "auto") -> str:
        """Return ``model`` or ``deterministic`` for the current case; commits nothing.

        ``auto`` chooses the model only for a prose brief when a model adapter is configured;
        a structured brief is mapped deterministically unless the model is requested. The
        factory is consulted only when its answer can change the outcome.
        """

        if interpreter not in INTERPRETER_MODES:
            raise OAKError(
                "OAK-INTERPRETER-MODE", "interpreter must be auto, model or deterministic"
            )
        if interpreter != "auto":
            return interpreter
        if self._model_interpreter_factory is None:
            return "deterministic"
        source_document, _ = self._source_for(self._require_case())
        if str(source_document["format"]) in STRUCTURED_FORMATS:
            return "deterministic"
        return "model" if self._model_interpreter_factory() is not None else "deterministic"

    def interpret(self, context: CommandContext, *, interpreter: str = "auto") -> DesignResult:
        mode = self.resolve_interpreter(interpreter)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        source_document, source_ref = self._source_for(current_document)
        content_ref = ArtifactReference.from_document(source_document["content_ref"])
        source_content = self._repository.read_artifact(content_ref)
        adapter: ModelInterpreterPort | None = None
        if mode == "model":
            if self._model_interpreter_factory is not None:
                adapter = self._model_interpreter_factory()
            if adapter is None:
                raise OAKError(
                    "OAK-MODEL-NOT-CONFIGURED",
                    "no model is configured for interpretation; select one with "
                    "`oak models select <family> <model_id>` or interpret with "
                    "--interpreter deterministic",
                )
        request: dict[str, Any] = {
            "case_id": current.id,
            "source_ref": source_ref.to_document(),
            "content_digest": content_ref.digest,
        }
        if adapter is not None:
            request["interpreter"] = "model"
        input_digest = self._request_digest(context, request)
        context = self._normalized_context(context, "interpret", input_digest)
        self._check_context(context)
        manifest = self._repository.manifest()
        if manifest["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
        duplicate_case = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate_case is not None:
            duplicate_intent = self._intent_for_case(duplicate_case)
            return DesignResult(
                case=duplicate_case,
                intent=duplicate_intent,
                duplicate=True,
                interpreter=self._interpreter_of(duplicate_intent),
            )
        if current.status is not DesignCaseStatus.DRAFT:
            raise OAKError("OAK-INTERPRET-STATE", "only a draft case can be interpreted")
        brief = self._intake.read_content(
            original_name=str(source_document["original_name"]),
            content=source_content,
        )
        proposal: dict[str, Any] | None = None
        proposal_artifact: Artifact | None = None
        if adapter is not None:
            proposal = self._bind_proposal(adapter, source_document, source_ref, source_content)
            proposal_artifact = json_artifact(
                artifact_id=str(proposal["id"]),
                version=str(proposal["version"]),
                kind="interpretation_proposal",
                media_type=PROPOSAL_MEDIA_TYPE,
                document=proposal,
            )
        interpreted = self._interpreter.interpret(
            brief,
            created_at=context.occurred_at,
            proposal=proposal,
            registry=self._registry if proposal is not None else None,
        )
        intent_document = copy.deepcopy(interpreted.intent_document)
        intent_document["extensions"][SOURCE_RECORD_EXTENSION] = source_ref.to_document()
        if proposal_artifact is not None:
            intent_document["extensions"][PROPOSAL_REF_EXTENSION] = (
                proposal_artifact.reference.to_document()
            )
        self._registry.validate("system-intent.schema.json", intent_document)
        intent_artifact = json_artifact(
            artifact_id=str(intent_document["id"]),
            version=str(intent_document["version"]),
            kind="system_intent",
            media_type=INTENT_MEDIA_TYPE,
            document=intent_document,
        )
        status = (
            DesignCaseStatus.NEEDS_CONFIRMATION
            if interpreted.questions or self._has_unconfirmed_model_records(intent_document)
            else DesignCaseStatus.READY_FOR_CANDIDATES
        )
        successor = current.revise(
            status=status,
            updated_at=context.occurred_at,
            intent_ref=intent_artifact.reference,
            assumptions=interpreted.assumptions,
            unresolved_questions=tuple(
                question.case_document() for question in interpreted.questions
            ),
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"]
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type="brief_interpreted",
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=intent_artifact.reference,
            source_record_ref=source_ref,
            extensions=(
                {INTERPRETER_EXTENSION: self._interpreter_extension(proposal, proposal_artifact)}
                if proposal is not None and proposal_artifact is not None
                else None
            ),
        )
        event_artifact = self._audit_artifact(event_document, sequence)
        successor = successor.with_audit_head(event_artifact.digest)
        case_artifact = self._case_artifact(successor)
        artifacts: tuple[Artifact, ...] = (
            (intent_artifact, proposal_artifact, event_artifact, case_artifact)
            if proposal_artifact is not None
            else (intent_artifact, event_artifact, case_artifact)
        )
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=artifacts,
                current_case_ref=case_artifact.reference,
                event_artifact=event_artifact,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        committed_intent = self._intent_for_case(committed.case_document)
        return DesignResult(
            case=committed.case_document,
            intent=committed_intent,
            duplicate=committed.duplicate,
            interpreter=self._interpreter_of(committed_intent),
        )

    def questions(self) -> QuestionResult:
        case = self._require_case()
        return QuestionResult(
            case_id=str(case["id"]),
            case_version=str(case["version"]),
            status=str(case["status"]),
            questions=tuple(case["unresolved_questions"]),
        )

    def confirm(self, answers_document: dict[str, Any], context: CommandContext) -> DesignResult:
        self._registry.validate("confirmation-answers.schema.json", answers_document)
        try:
            input_digest = self._request_digest(context, {"answers": answers_document})
        except (TypeError, ValueError) as error:
            raise OAKError(
                "OAK-CONFIRM-MALFORMED", "confirmation input is not canonical JSON data"
            ) from error
        context = self._normalized_context(context, "confirm", input_digest)
        self._check_context(context)
        manifest = self._repository.manifest()
        if manifest["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
        duplicate_case = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate_case is not None:
            return DesignResult(
                case=duplicate_case,
                intent=self._intent_for_case(duplicate_case),
                duplicate=True,
            )
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if answers_document["design_case_id"] != current.id:
            raise OAKError("OAK-CONFIRM-CASE", "answers target a different design case")
        if current.status is not DesignCaseStatus.NEEDS_CONFIRMATION:
            raise OAKError(
                "OAK-CONFIRM-STATE",
                "claims can be confirmed only while the case needs confirmation",
            )
        intent = copy.deepcopy(self._intent_for_case(current_document))
        question_by_id = {
            str(question["id"]): question for question in current_document["unresolved_questions"]
        }
        answer_ids = [str(answer["question_id"]) for answer in answers_document["answers"]]
        if len(answer_ids) != len(set(answer_ids)):
            raise OAKError("OAK-CONFIRM-DUPLICATE", "each question may be answered once")

        confirmations = list(intent["extensions"].get("oak.community/confirmations", []))
        for answer in answers_document["answers"]:
            question_id = str(answer["question_id"])
            question = question_by_id.get(question_id)
            if question is None or question["status"] not in {"open", "bounded"}:
                raise OAKError("OAK-CONFIRM-QUESTION", "answer references no open question")
            self._apply_answer(intent, question, answer, context)
            confirmations.append(
                {
                    "question_id": question_id,
                    "decision": answer["decision"],
                    "value_digest": content_digest(
                        canonical_json_bytes({"value": answer["value"]})
                    ),
                    "rationale": answer["rationale"],
                    "actor": context.actor,
                    "decided_at": context.occurred_at,
                }
            )
        intent["extensions"]["oak.community/confirmations"] = confirmations
        self._sync_intent_questions(intent, question_by_id)
        open_questions = tuple(
            question for question in question_by_id.values() if question["status"] == "open"
        )
        # A model-proposed value that nobody has confirmed, corrected or rejected keeps the
        # case in confirmation whatever the question list says.
        unconfirmed_model = self._has_unconfirmed_model_records(intent)
        intent["status"] = "draft" if open_questions or unconfirmed_model else "clarified"
        old_intent_version = str(intent["version"])
        intent["version"] = next_patch_version(old_intent_version)
        intent["supersedes"] = f"{intent['id']}@{old_intent_version}"
        intent["created_at"] = context.occurred_at
        verify_intent_provenance(intent)
        self._registry.validate("system-intent.schema.json", intent)
        intent_artifact = json_artifact(
            artifact_id=str(intent["id"]),
            version=str(intent["version"]),
            kind="system_intent",
            media_type=INTENT_MEDIA_TYPE,
            document=intent,
        )

        case_status = (
            DesignCaseStatus.NEEDS_CONFIRMATION
            if open_questions or unconfirmed_model
            else DesignCaseStatus.READY_FOR_CANDIDATES
        )
        assumptions = self._updated_assumptions(
            current.assumptions, answers_document["answers"], question_by_id
        )
        successor = current.revise(
            status=case_status,
            updated_at=context.occurred_at,
            intent_ref=intent_artifact.reference,
            assumptions=assumptions,
            unresolved_questions=tuple(question_by_id.values()),
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        source_record_ref = self._source_record_ref(intent)
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type="claims_confirmed",
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=intent_artifact.reference,
            source_record_ref=source_record_ref,
        )
        event_artifact = self._audit_artifact(event_document, sequence)
        successor = successor.with_audit_head(event_artifact.digest)
        case_artifact = self._case_artifact(successor)
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(intent_artifact, event_artifact, case_artifact),
                current_case_ref=case_artifact.reference,
                event_artifact=event_artifact,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        return DesignResult(
            case=committed.case_document,
            intent=self._intent_for_case(committed.case_document),
            duplicate=committed.duplicate,
        )

    def optional_proposal(
        self, adapter: ModelInterpreterPort, limits: ProposalLimits
    ) -> dict[str, Any]:
        """Obtain and validate a proposal for the current case without committing it."""

        case = self._require_case()
        intent = self._intent_for_case(case)
        source_ref = self._source_record_ref(intent)
        if source_ref is None:
            raise OAKError("OAK-SOURCE-MISSING", "intent has no source record")
        source = self._repository.read_json_artifact(source_ref)
        content_ref = ArtifactReference.from_document(source["content_ref"])
        content = self._repository.read_artifact(content_ref)
        return self._bind_proposal(adapter, source, source_ref, content, limits=limits)

    def _bind_proposal(
        self,
        adapter: ModelInterpreterPort,
        source_document: dict[str, Any],
        source_ref: ArtifactReference,
        content: bytes,
        *,
        limits: ProposalLimits | None = None,
    ) -> dict[str, Any]:
        """Call the adapter with the source record augmented by its own artifact reference,
        then validate the proposal and its binding to that record."""

        limits = limits or self._proposal_limits
        augmented = copy.deepcopy(source_document)
        augmented["extensions"] = {
            **dict(augmented.get("extensions", {})),
            SOURCE_ARTIFACT_REF_EXTENSION: source_ref.to_document(),
        }
        proposal = adapter.propose(augmented, content, limits)
        validated = validate_interpretation_proposal(
            proposal, self._registry, limits.maximum_output_bytes
        )
        if validated["source_ref"] != source_ref.to_document():
            raise OAKError(
                "OAK-INTERPRETER-SOURCE",
                "optional proposal is not bound to the requested source record",
            )
        if "version" not in validated:
            validated = {**validated, "version": "0.1.0"}
        return validated

    def _source_for(
        self, case_document: dict[str, Any]
    ) -> tuple[dict[str, Any], ArtifactReference]:
        extensions = case_document.get("extensions", {})
        source_ref_document = extensions.get("oak.community/source_record_ref")
        if not isinstance(source_ref_document, dict):
            raise OAKError("OAK-SOURCE-MISSING", "draft case has no source record")
        source_ref = ArtifactReference.from_document(source_ref_document)
        return self._repository.read_json_artifact(source_ref), source_ref

    @staticmethod
    def _interpreter_of(intent: dict[str, Any]) -> str:
        return (
            "model" if PROPOSAL_REF_EXTENSION in intent.get("extensions", {}) else "deterministic"
        )

    @staticmethod
    def _interpreter_extension(
        proposal: dict[str, Any], proposal_artifact: Artifact
    ) -> dict[str, Any]:
        details = proposal.get("extensions", {}).get(MODEL_EXTENSION)
        model = details if isinstance(details, dict) else {}

        def text(key: str) -> str | None:
            value = model.get(key)
            return value if isinstance(value, str) and 0 < len(value) <= 200 else None

        return {
            "kind": "model",
            "family": text("family"),
            "model_id": text("model_id"),
            "provider_route": text("provider_route"),
            "proposal_digest": proposal_artifact.digest,
        }

    @staticmethod
    def _has_unconfirmed_model_records(intent: dict[str, Any]) -> bool:
        return any(
            record.get("source") == MODEL_PROPOSED and bool(record.get("confirmation_required"))
            for record in intent["provenance"].values()
        )

    def export_to(self, destination: Path) -> None:
        self._repository.export_to(destination)

    def import_from(self, source: Path) -> None:
        self._repository.import_from(source)

    def current(self) -> DesignResult:
        case = self._require_case()
        intent = self._intent_for_case(case) if isinstance(case.get("intent_ref"), dict) else None
        return DesignResult(case=case, intent=intent, duplicate=False)

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    def _intent_for_case(self, case: dict[str, Any]) -> dict[str, Any]:
        reference = case.get("intent_ref")
        if not isinstance(reference, dict):
            raise OAKError("OAK-INTENT-NOT-FOUND", "design case has no intent artifact")
        return self._repository.read_json_artifact(ArtifactReference.from_document(reference))

    def _case_artifact(self, case: DesignCase) -> Artifact:
        document = case.to_document()
        self._registry.validate("design-case.schema.json", document)
        return json_artifact(
            artifact_id=case.id,
            version=case.version,
            kind="design_case",
            media_type=CASE_MEDIA_TYPE,
            document=document,
        )

    def _audit_artifact(self, document: dict[str, Any], sequence: int) -> Artifact:
        self._registry.validate("audit-event.schema.json", document)
        return json_artifact(
            artifact_id=str(document["id"]),
            version=str(sequence),
            kind="audit_event",
            media_type=AUDIT_MEDIA_TYPE,
            document=document,
        )

    @staticmethod
    def _check_context(context: CommandContext) -> None:
        if len(context.idempotency_key) < 16:
            raise OAKError(
                "OAK-IDEMPOTENCY-KEY",
                "idempotency key must contain at least 16 characters",
            )
        if len(context.correlation_id) < 8:
            raise OAKError(
                "OAK-CORRELATION-ID",
                "correlation ID must contain at least 8 characters",
            )

    @staticmethod
    def _normalized_context(
        context: CommandContext, operation: str, input_digest: str
    ) -> CommandContext:
        digest_hex = input_digest.removeprefix("sha256:")
        return replace(
            context,
            idempotency_key=(context.idempotency_key or f"{operation}:{digest_hex}"),
            correlation_id=(context.correlation_id or f"correlation:{digest_hex[:24]}"),
        )

    @staticmethod
    def _derived_id(prefix: str, brief_id: str) -> str:
        return f"{prefix}.{brief_id.removeprefix('brief.')}"

    @staticmethod
    def _request_digest(context: CommandContext, input_document: dict[str, Any]) -> str:
        return content_digest(
            canonical_json_bytes(
                {
                    "actor": context.actor,
                    "tenant_id": context.tenant_id,
                    "input": input_document,
                }
            )
        )

    @staticmethod
    def _source_record_ref(intent: dict[str, Any]) -> ArtifactReference | None:
        reference = intent["extensions"].get("oak.community/source_record")
        return ArtifactReference.from_document(reference) if isinstance(reference, dict) else None

    @staticmethod
    def _sync_intent_questions(
        intent: dict[str, Any], questions: dict[str, dict[str, Any]]
    ) -> None:
        statuses = {identifier: question["status"] for identifier, question in questions.items()}
        for unresolved in intent["unresolved"]:
            unresolved["status"] = statuses[str(unresolved["id"])]

    @staticmethod
    def _updated_assumptions(
        assumptions: tuple[dict[str, Any], ...],
        answers: list[dict[str, Any]],
        questions: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        status_by_path = {
            questions[str(answer["question_id"])]["path"]: {
                "confirm": "confirmed",
                "correct": "corrected",
                "reject": "rejected",
                "accept_risk": "accepted_risk",
            }[str(answer["decision"])]
            for answer in answers
        }
        updated: list[dict[str, Any]] = []
        for assumption in assumptions:
            path = str(assumption["path"])
            status = next(
                (
                    decided
                    for answered, decided in status_by_path.items()
                    if path == answered or path.startswith(f"{answered}/")
                ),
                assumption["status"],
            )
            updated.append({**assumption, "status": status})
        return tuple(updated)

    def _apply_answer(
        self,
        intent: dict[str, Any],
        question: dict[str, Any],
        answer: dict[str, Any],
        context: CommandContext,
    ) -> None:
        path = str(question["path"])
        decision = str(answer["decision"])
        if decision in {"confirm", "accept_risk"}:
            current = self._pointer_get(intent, path)
            if current != answer["value"]:
                raise OAKError(
                    "OAK-CONFIRM-VALUE-MISMATCH",
                    "confirmed value does not match the current canonical claim",
                )
            self._confirm_provenance(intent, path, answer, context)
            question["status"] = "resolved" if decision == "confirm" else "accepted_risk"
            return
        if decision == "correct":
            self._pointer_set(intent, path, answer["value"])
            self._replace_provenance(intent, path, answer["value"], answer, context)
            question["status"] = "resolved"
            return
        if decision == "reject":
            if self._is_section_path(path):
                self._reject_section(intent, path)
            else:
                self._pointer_remove(intent, path)
                self._remove_provenance(intent, path)
            question["status"] = "open"
            return
        raise OAKError("OAK-CONFIRM-DECISION", "confirmation decision is unsupported")

    @staticmethod
    def _is_section_path(path: str) -> bool:
        parts = path.split("/")
        return len(parts) == 3 and parts[1] == "spec" and bool(parts[2])

    @classmethod
    def _reject_section(cls, intent: dict[str, Any], path: str) -> None:
        """Reject a section-level question.

        The claims under review at a section path are the model-proposed ones, so those
        values and their provenance are removed field by field while explicit brief values
        stay. A section that holds no model-proposed value (the deterministic hardware
        question) is emptied instead; a required section is never deleted.
        """

        section = path.split("/")[2]
        roots: set[str] = set()
        for record_path, record in intent["provenance"].items():
            if record.get("source") != MODEL_PROPOSED or not record_path.startswith(f"{path}/"):
                continue
            parts = record_path.split("/")
            width = 5 if len(parts) > 3 and parts[3] == "extensions" else 4
            roots.add("/".join(parts[:width]))
        if not roots:
            intent["spec"][section] = {}
            cls._remove_provenance(intent, path)
            return
        for root in sorted(roots):
            cls._pointer_remove(intent, root)
            cls._remove_provenance(intent, root)
        section_document = intent["spec"][section]
        if (
            isinstance(section_document.get("extensions"), dict)
            and not section_document["extensions"]
        ):
            del section_document["extensions"]

    @staticmethod
    def _pointer_parts(pointer: str) -> list[str]:
        if not pointer.startswith("/spec/"):
            raise OAKError("OAK-CONFIRM-PATH", "confirmation path is outside intent spec")
        return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]

    @classmethod
    def _pointer_get(cls, document: dict[str, Any], pointer: str) -> Any:
        current: Any = document
        try:
            for part in cls._pointer_parts(pointer):
                current = current[int(part)] if isinstance(current, list) else current[part]
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise OAKError("OAK-CONFIRM-PATH", "confirmation path has no current value") from error
        return current

    @classmethod
    def _pointer_set(cls, document: dict[str, Any], pointer: str, value: Any) -> None:
        parts = cls._pointer_parts(pointer)
        current: Any = document
        for index, part in enumerate(parts[:-1]):
            next_part = parts[index + 1]
            if isinstance(current, list):
                position = int(part)
                while len(current) <= position:
                    current.append({})
                current = current[position]
            else:
                if part not in current:
                    current[part] = [] if next_part.isdigit() else {}
                current = current[part]
        final = parts[-1]
        if isinstance(current, list):
            position = int(final)
            while len(current) <= position:
                current.append(None)
            current[position] = value
        else:
            current[final] = value

    @classmethod
    def _pointer_remove(cls, document: dict[str, Any], pointer: str) -> None:
        parts = cls._pointer_parts(pointer)
        current: Any = document
        try:
            for part in parts[:-1]:
                current = current[int(part)] if isinstance(current, list) else current[part]
            final = parts[-1]
            if isinstance(current, list):
                current.pop(int(final))
            else:
                current.pop(final)
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise OAKError("OAK-CONFIRM-PATH", "rejected claim path does not exist") from error

    @staticmethod
    def _confirm_provenance(
        intent: dict[str, Any],
        path: str,
        answer: dict[str, Any],
        context: CommandContext,
    ) -> None:
        matching = [
            record_path
            for record_path in intent["provenance"]
            if record_path == path or record_path.startswith(f"{path}/")
        ]
        if not matching:
            raise OAKError("OAK-CONFIRM-PROVENANCE", "claim has no provenance to confirm")
        for record_path in matching:
            record = intent["provenance"][record_path]
            record["confirmation_required"] = False
            record["confirmed_by"] = context.actor
            record["confirmed_at"] = context.occurred_at
            record["rationale"] = str(answer["rationale"])

    @classmethod
    def _replace_provenance(
        cls,
        intent: dict[str, Any],
        path: str,
        value: Any,
        answer: dict[str, Any],
        context: CommandContext,
    ) -> None:
        cls._remove_provenance(intent, path)

        def add(child: Any, child_path: str) -> None:
            if isinstance(child, dict):
                for key, nested in child.items():
                    escaped = str(key).replace("~", "~0").replace("/", "~1")
                    add(nested, f"{child_path}/{escaped}")
                return
            if isinstance(child, list):
                for index, nested in enumerate(child):
                    add(nested, f"{child_path}/{index}")
                return
            intent["provenance"][child_path] = {
                "source": "user_correction",
                "confidence": 1.0,
                "rationale": str(answer["rationale"]),
                "evidence_refs": [],
                "materiality": "high",
                "confirmation_required": False,
                "confirmed_by": context.actor,
                "confirmed_at": context.occurred_at,
            }

        add(value, path)

    @staticmethod
    def _remove_provenance(intent: dict[str, Any], path: str) -> None:
        for record_path in tuple(intent["provenance"]):
            if record_path == path or record_path.startswith(f"{path}/"):
                del intent["provenance"][record_path]
