# SPDX-License-Identifier: Apache-2.0
"""Shared candidate, evaluation, assurance and planning application operations."""

import copy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.compiler import (
    compile_catalogue,
    compile_review_plan,
    create_assurance_plan,
    create_evaluation_contract,
    create_selection_decision,
    evaluate_candidate,
    generate_candidates,
)
from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    DesignCase,
    DesignCaseStatus,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.ports import CataloguePort, TargetProfilePort, WorkspaceRepository

CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"


@dataclass(frozen=True, slots=True)
class CandidatesResult:
    case: dict[str, Any]
    candidates: tuple[dict[str, Any], ...]
    catalogue_snapshot: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "case_id": self.case["id"],
            "case_version": self.case["version"],
            "status": self.case["status"],
            "catalogue_snapshot": self.catalogue_snapshot,
            "candidates": list(self.candidates),
            "duplicate": self.duplicate,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case: dict[str, Any]
    evaluation: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {"case": self.case, "evaluation": self.evaluation, "duplicate": self.duplicate}


@dataclass(frozen=True, slots=True)
class SelectionResult:
    case: dict[str, Any]
    decision: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {"case": self.case, "decision": self.decision, "duplicate": self.duplicate}


@dataclass(frozen=True, slots=True)
class AssuranceResult:
    case: dict[str, Any]
    assurance_plan: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "assurance_plan": self.assurance_plan,
            "duplicate": self.duplicate,
        }


@dataclass(frozen=True, slots=True)
class PlanResult:
    case: dict[str, Any]
    decision: dict[str, Any]
    assurance_plan: dict[str, Any]
    semantic_manifest: dict[str, Any]
    deployment_bundle: dict[str, Any]
    runner_plan: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "decision": self.decision,
            "assurance_plan": self.assurance_plan,
            "semantic_manifest": self.semantic_manifest,
            "deployment_bundle": self.deployment_bundle,
            "runner_plan": self.runner_plan,
            "duplicate": self.duplicate,
        }


class CandidatePlanningService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        catalogue: CataloguePort,
        target_profiles: TargetProfilePort,
        registry: SchemaRegistry,
    ) -> None:
        self._repository = repository
        self._catalogue = catalogue
        self._target_profiles = target_profiles
        self._registry = registry

    def candidates(self, context: CommandContext) -> CandidatesResult:
        documents = self._catalogue.load()
        catalogue_input_digest = content_digest(
            canonical_json_bytes(
                {
                    "manifests": list(documents.manifests),
                    "patterns": list(documents.patterns),
                }
            )
        )
        input_digest = self._request_digest(
            context, {"catalogue_input_digest": catalogue_input_digest}
        )
        context = self._normalized_context(context, "candidates", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return self._candidates_result(duplicate, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.READY_FOR_CANDIDATES:
            raise OAKError(
                "OAK-CANDIDATES-STATE",
                "candidates require a case that is ready for candidates",
            )
        intent_ref = self._required_reference(current_document, "intent_ref")
        intent = self._repository.read_json_artifact(intent_ref)
        catalogue = compile_catalogue(
            documents.manifests,
            documents.patterns,
            self._registry,
            created_at=context.occurred_at,
        )
        evaluation_contract = create_evaluation_contract(intent, self._registry)
        candidate_artifacts = generate_candidates(
            intent,
            intent_ref,
            evaluation_contract.reference,
            catalogue,
            self._registry,
            generated_at=context.occurred_at,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/catalogue_snapshot_ref"] = (
            catalogue.snapshot.reference.to_document()
        )
        extensions["oak.community/pattern_refs"] = [
            artifact.reference.to_document() for artifact in catalogue.patterns
        ]
        successor = current.revise(
            status=DesignCaseStatus.CANDIDATES_READY,
            updated_at=context.occurred_at,
            evaluation_contract_ref=evaluation_contract.reference,
            candidate_refs=tuple(artifact.reference for artifact in candidate_artifacts),
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="candidates_generated",
            context=context,
            input_digest=input_digest,
            artifacts=(
                *catalogue.manifests,
                *catalogue.patterns,
                catalogue.snapshot,
                evaluation_contract,
                *candidate_artifacts,
            ),
        )
        return self._candidates_result(published, duplicate=False)

    def list_candidates(self) -> tuple[dict[str, Any], ...]:
        """Return the current immutable candidates in deterministic identity order."""

        current = self._require_case()
        return tuple(
            self._repository.read_json_artifact(ArtifactReference.from_document(item))
            for item in sorted(current["candidate_refs"], key=lambda item: str(item["id"]))
        )

    def evaluate(self, candidate_id: str, context: CommandContext) -> EvaluationResult:
        input_digest = self._request_digest(context, {"candidate_id": candidate_id})
        context = self._normalized_context(context, f"evaluate:{candidate_id}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return EvaluationResult(
                case=duplicate,
                evaluation=self._evaluation_for_candidate(duplicate, candidate_id),
                duplicate=True,
            )
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.CANDIDATES_READY:
            raise OAKError(
                "OAK-EVALUATE-STATE", "candidate evaluation requires candidates_ready state"
            )
        candidate = self._candidate_artifact(current_document, candidate_id)
        if self._optional_evaluation_artifact(current_document, candidate_id) is not None:
            raise OAKError(
                "OAK-EVALUATION-EXISTS",
                "candidate already has an immutable evaluation; retry with the original key",
            )
        candidate_document = self._artifact_document(candidate)
        contract_ref = self._required_reference(current_document, "evaluation_contract_ref")
        contract = self._repository.read_json_artifact(contract_ref)
        result = evaluate_candidate(
            candidate_document,
            candidate.reference,
            contract,
            contract_ref,
            self._registry,
            executed_at=context.occurred_at,
            executor=context.actor,
        )
        extensions = copy.deepcopy(current.extensions or {})
        evaluation_refs = list(extensions.get("oak.community/evaluation_refs", []))
        evaluation_refs.append(result.reference.to_document())
        evaluation_refs.sort(key=lambda item: (str(item["id"]), str(item["version"])))
        extensions["oak.community/evaluation_refs"] = evaluation_refs
        successor = current.revise(
            status=DesignCaseStatus.CANDIDATES_READY,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="candidate_evaluated",
            context=context,
            input_digest=input_digest,
            artifacts=(result,),
        )
        return EvaluationResult(
            case=published, evaluation=self._artifact_document(result), duplicate=False
        )

    def select(self, candidate_id: str, rationale: str, context: CommandContext) -> SelectionResult:
        normalized_rationale = rationale.strip()
        if not normalized_rationale or len(normalized_rationale) > 12_000:
            raise OAKError("OAK-SELECT-RATIONALE", "selection rationale is required and bounded")
        input_digest = self._request_digest(
            context, {"candidate_id": candidate_id, "rationale": normalized_rationale}
        )
        context = self._normalized_context(context, f"select:{candidate_id}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            decision_ref = self._extension_reference(
                duplicate, "oak.community/selection_decision_ref"
            )
            return SelectionResult(
                case=duplicate,
                decision=self._repository.read_json_artifact(decision_ref),
                duplicate=True,
            )
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.CANDIDATES_READY:
            raise OAKError("OAK-SELECT-STATE", "selection requires candidates_ready state")
        candidate = self._candidate_artifact(current_document, candidate_id)
        candidate_document = self._artifact_document(candidate)
        if candidate_document["status"] != "feasible":
            raise OAKError("OAK-SELECT-INFEASIBLE", "an infeasible candidate cannot be selected")
        evaluation = self._evaluation_artifact(current_document, candidate_id)
        evaluation_document = self._artifact_document(evaluation)
        if evaluation_document["status"] != "pass":
            raise OAKError(
                "OAK-SELECT-EVALUATION", "candidate evaluation must pass before selection"
            )
        alternatives = tuple(
            self._artifact_for_reference(
                ArtifactReference.from_document(item), "architecture_candidate"
            )
            for item in current_document["candidate_refs"]
            if item["id"] != candidate_id
        )
        dependency_refs = (
            self._required_reference(current_document, "evaluation_contract_ref"),
            self._extension_reference(current_document, "oak.community/catalogue_snapshot_ref"),
        )
        decision = create_selection_decision(
            candidate,
            alternatives,
            evaluation,
            dependency_refs,
            self._registry,
            rationale=normalized_rationale,
            owner=context.actor,
            decided_at=context.occurred_at,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/selection_decision_ref"] = decision.reference.to_document()
        successor = current.revise(
            status=DesignCaseStatus.CANDIDATE_SELECTED,
            updated_at=context.occurred_at,
            selected_candidate_ref=candidate.reference,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="candidate_selected",
            context=context,
            input_digest=input_digest,
            artifacts=(decision,),
        )
        return SelectionResult(
            case=published, decision=self._artifact_document(decision), duplicate=False
        )

    def assure(self, candidate_id: str, context: CommandContext) -> AssuranceResult:
        input_digest = self._request_digest(context, {"candidate_id": candidate_id})
        context = self._normalized_context(context, f"assure:{candidate_id}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            reference = self._required_reference(duplicate, "assurance_plan_ref")
            return AssuranceResult(
                case=duplicate,
                assurance_plan=self._repository.read_json_artifact(reference),
                duplicate=True,
            )
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.CANDIDATE_SELECTED:
            raise OAKError("OAK-ASSURE-STATE", "assurance requires candidate_selected state")
        selected = self._required_reference(current_document, "selected_candidate_ref")
        if selected.id != candidate_id:
            raise OAKError("OAK-ASSURE-CANDIDATE", "assurance candidate is not selected")
        candidate = self._artifact_for_reference(selected, "architecture_candidate")
        evaluation = self._evaluation_artifact(current_document, candidate_id)
        contract = self._artifact_for_reference(
            self._required_reference(current_document, "evaluation_contract_ref"),
            "evaluation_contract",
        )
        assurance = create_assurance_plan(
            candidate,
            contract,
            evaluation,
            self._registry,
            created_at=context.occurred_at,
        )
        successor = current.revise(
            status=DesignCaseStatus.ASSURANCE_PLANNED,
            updated_at=context.occurred_at,
            assurance_plan_ref=assurance.reference,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="assurance_planned",
            context=context,
            input_digest=input_digest,
            artifacts=(assurance,),
        )
        return AssuranceResult(
            case=published,
            assurance_plan=self._artifact_document(assurance),
            duplicate=False,
        )

    def plan(self, candidate_id: str, target_path: Path, context: CommandContext) -> PlanResult:
        target = self._target_profiles.load(target_path)
        return self.plan_document(candidate_id, target, context)

    def plan_document(
        self,
        candidate_id: str,
        target_document: dict[str, Any],
        context: CommandContext,
    ) -> PlanResult:
        target = self._target_profiles.validate_document(copy.deepcopy(target_document))
        input_digest = self._request_digest(
            context, {"candidate_id": candidate_id, "target": target}
        )
        context = self._normalized_context(context, f"plan:{candidate_id}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        if target["tenant_id"] != context.tenant_id:
            raise OAKError(
                "OAK-TARGET-TENANT", "target tenant does not match the command authority"
            )
        required_operations = {"inventory", "validate", "render", "plan", "verify"}
        allowed_operations = set(target["permissions"]["allowed_operations"])
        if not required_operations.issubset(allowed_operations):
            raise OAKError(
                "OAK-TARGET-CAPABILITY",
                "target does not allow every required read-only planning operation",
            )
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return self._plan_result(duplicate, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.ASSURANCE_PLANNED:
            raise OAKError("OAK-PLAN-STATE", "plan compilation requires assurance_planned state")
        selected = self._required_reference(current_document, "selected_candidate_ref")
        if selected.id != candidate_id:
            raise OAKError("OAK-PLAN-CANDIDATE", "plan candidate is not selected")
        current_case_ref = ArtifactReference.from_document(
            self._repository.manifest()["current_case_ref"]
        )
        intent_ref = self._required_reference(current_document, "intent_ref")
        intent = self._repository.read_json_artifact(intent_ref)
        candidate = self._artifact_for_reference(selected, "architecture_candidate")
        decision = self._artifact_for_reference(
            self._extension_reference(current_document, "oak.community/selection_decision_ref"),
            "architecture_decision",
        )
        assurance = self._artifact_for_reference(
            self._required_reference(current_document, "assurance_plan_ref"), "assurance_plan"
        )
        catalogue_snapshot = self._artifact_for_reference(
            self._extension_reference(current_document, "oak.community/catalogue_snapshot_ref"),
            "catalogue_snapshot",
        )
        compiled = compile_review_plan(
            case_ref=current_case_ref,
            intent=intent,
            intent_ref=intent_ref,
            evaluation_contract_ref=self._required_reference(
                current_document, "evaluation_contract_ref"
            ),
            candidate=candidate,
            decision=decision,
            assurance=assurance,
            target=target,
            catalogue_snapshot=catalogue_snapshot,
            registry=self._registry,
            created_at=context.occurred_at,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/semantic_manifest_ref"] = (
            compiled.semantic_manifest.reference.to_document()
        )
        successor = current.revise(
            status=DesignCaseStatus.BUNDLE_COMPILED,
            updated_at=context.occurred_at,
            deployment_bundle_ref=compiled.bundle.reference,
            runner_plan_ref=compiled.runner_plan.reference,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="bundle_compiled",
            context=context,
            input_digest=input_digest,
            artifacts=compiled.artifacts,
        )
        return self._plan_result(published, duplicate=False)

    def _publish(
        self,
        *,
        current: dict[str, Any],
        successor: DesignCase,
        event_type: str,
        context: CommandContext,
        input_digest: str,
        artifacts: tuple[Artifact, ...],
    ) -> dict[str, Any]:
        manifest = self._repository.manifest()
        intent_ref = self._required_reference(current, "intent_ref")
        intent = self._repository.read_json_artifact(intent_ref)
        source_record_ref = self._source_record_ref(intent)
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type=event_type,
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=intent_ref,
            source_record_ref=source_record_ref,
            extensions={
                "oak.community/artifact_refs": [
                    artifact.reference.to_document() for artifact in artifacts
                ]
            },
        )
        self._registry.validate("audit-event.schema.json", event_document)
        event = json_artifact(
            artifact_id=str(event_document["id"]),
            version=str(sequence),
            kind="audit_event",
            media_type=AUDIT_MEDIA_TYPE,
            document=event_document,
        )
        successor = successor.with_audit_head(event.digest)
        case_document = successor.to_document()
        self._registry.validate("design-case.schema.json", case_document)
        case = json_artifact(
            artifact_id=successor.id,
            version=successor.version,
            kind="design_case",
            media_type=CASE_MEDIA_TYPE,
            document=case_document,
        )
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(*artifacts, event, case),
                current_case_ref=case.reference,
                event_artifact=event,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        return committed.case_document

    def _candidates_result(self, case: dict[str, Any], *, duplicate: bool) -> CandidatesResult:
        candidates = tuple(
            self._repository.read_json_artifact(ArtifactReference.from_document(item))
            for item in sorted(case["candidate_refs"], key=lambda item: str(item["id"]))
        )
        snapshot_ref = self._extension_reference(case, "oak.community/catalogue_snapshot_ref")
        return CandidatesResult(
            case=case,
            candidates=candidates,
            catalogue_snapshot=self._repository.read_json_artifact(snapshot_ref),
            duplicate=duplicate,
        )

    def _plan_result(self, case: dict[str, Any], *, duplicate: bool) -> PlanResult:
        decision_ref = self._extension_reference(case, "oak.community/selection_decision_ref")
        semantic_ref = self._extension_reference(case, "oak.community/semantic_manifest_ref")
        return PlanResult(
            case=case,
            decision=self._repository.read_json_artifact(decision_ref),
            assurance_plan=self._repository.read_json_artifact(
                self._required_reference(case, "assurance_plan_ref")
            ),
            semantic_manifest=self._repository.read_json_artifact(semantic_ref),
            deployment_bundle=self._repository.read_json_artifact(
                self._required_reference(case, "deployment_bundle_ref")
            ),
            runner_plan=self._repository.read_json_artifact(
                self._required_reference(case, "runner_plan_ref")
            ),
            duplicate=duplicate,
        )

    def _evaluation_for_candidate(self, case: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        return self._artifact_document(self._evaluation_artifact(case, candidate_id))

    def _evaluation_artifact(self, case: dict[str, Any], candidate_id: str) -> Artifact:
        artifact = self._optional_evaluation_artifact(case, candidate_id)
        if artifact is not None:
            return artifact
        raise OAKError("OAK-EVALUATION-NOT-FOUND", "candidate has no evaluation result")

    def _optional_evaluation_artifact(
        self, case: dict[str, Any], candidate_id: str
    ) -> Artifact | None:
        for item in case.get("extensions", {}).get("oak.community/evaluation_refs", []):
            reference = ArtifactReference.from_document(item)
            artifact = self._artifact_for_reference(reference, "evaluation_result")
            document = self._artifact_document(artifact)
            if document["candidate_ref"]["id"] == candidate_id:
                return artifact
        return None

    def _candidate_artifact(self, case: dict[str, Any], candidate_id: str) -> Artifact:
        for item in case["candidate_refs"]:
            if item["id"] == candidate_id:
                return self._artifact_for_reference(
                    ArtifactReference.from_document(item), "architecture_candidate"
                )
        raise OAKError("OAK-CANDIDATE-NOT-FOUND", "candidate is not part of this design case")

    def _artifact_for_reference(self, reference: ArtifactReference, expected_kind: str) -> Artifact:
        entry = next(
            (
                item
                for item in self._repository.manifest()["artifact_index"]
                if item["id"] == reference.id and item["version"] == reference.version
            ),
            None,
        )
        if entry is None or entry["kind"] != expected_kind or entry["digest"] != reference.digest:
            raise OAKError("OAK-WORKSPACE-CORRUPT", "artifact reference is not indexed correctly")
        return Artifact(
            id=reference.id,
            version=reference.version,
            kind=expected_kind,
            media_type=reference.media_type,
            content=self._repository.read_artifact(reference),
        )

    @staticmethod
    def _artifact_document(artifact: Artifact) -> dict[str, Any]:
        import json

        document = json.loads(artifact.content)
        if not isinstance(document, dict):
            raise OAKError("OAK-WORKSPACE-CORRUPT", "canonical artifact is not an object")
        return document

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    def _check_tenant(self, context: CommandContext) -> None:
        if self._repository.manifest()["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")

    @staticmethod
    def _required_reference(document: dict[str, Any], field: str) -> ArtifactReference:
        value = document.get(field)
        if not isinstance(value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", f"required {field} artifact is missing")
        return ArtifactReference.from_document(value)

    @staticmethod
    def _extension_reference(document: dict[str, Any], key: str) -> ArtifactReference:
        value = document.get("extensions", {}).get(key)
        if not isinstance(value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", "required compiler dependency is missing")
        return ArtifactReference.from_document(value)

    @staticmethod
    def _source_record_ref(intent: dict[str, Any]) -> ArtifactReference | None:
        value = intent["extensions"].get("oak.community/source_record")
        return ArtifactReference.from_document(value) if isinstance(value, dict) else None

    @staticmethod
    def _check_context(context: CommandContext) -> None:
        if len(context.idempotency_key) < 16:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "idempotency key must contain 16 characters")
        if len(context.correlation_id) < 8:
            raise OAKError("OAK-CORRELATION-ID", "correlation ID must contain 8 characters")

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
