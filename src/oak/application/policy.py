# SPDX-License-Identifier: Apache-2.0
"""Governed policy-pack evaluation into canonical, engine-neutral decisions."""

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    DesignCase,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.policy_rules import pack_effective_window
from oak.ports import WorkspaceRepository
from oak.ports.policy import PolicyEnginePort, PolicyPackStorePort

PACK_MEDIA_TYPE = "application/vnd.oak.policy-pack+json"
DECISION_MEDIA_TYPE = "application/vnd.oak.policy-decision+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"
CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
DEFAULT_ENGINE = "builtin"


@dataclass(frozen=True, slots=True)
class PolicyEvaluationResult:
    case: dict[str, Any]
    decision: dict[str, Any]
    duplicate: bool


class PolicyService:
    """Evaluate governed packs over the current case through the policy port."""

    def __init__(
        self,
        repository: WorkspaceRepository,
        registry: SchemaRegistry,
        packs: PolicyPackStorePort,
        engine_loaders: Mapping[str, Callable[[], PolicyEnginePort]],
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._packs = packs
        self._engine_loaders = dict(engine_loaders)

    def list_packs(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": str(pack["id"]),
                "version": str(pack["version"]),
                "name": str(pack["name"]),
                "status": str(pack["status"]),
                "effective_from": str(pack["effective_from"]),
                "expires_at": pack["expires_at"],
                "scope": pack["scope"],
            }
            for pack in self._packs.list_packs()
        )

    def evaluate(
        self,
        pack_id: str,
        context: CommandContext,
        *,
        engine: str = DEFAULT_ENGINE,
    ) -> PolicyEvaluationResult:
        loader = self._engine_loaders.get(engine)
        if loader is None:
            raise OAKError("OAK-POLICY-ENGINE-UNKNOWN", "policy engine is not registered")
        pack = self._packs.load(pack_id)
        pack_artifact = json_artifact(
            artifact_id=str(pack["id"]),
            version=str(pack["version"]),
            kind="policy_pack",
            media_type=PACK_MEDIA_TYPE,
            document=pack,
        )
        current_document = self._require_case()
        subject = self._subject(current_document)
        subject_digest = content_digest(canonical_json_bytes(subject))
        input_digest = self._request_digest(
            context,
            {
                "action": "policy_evaluate",
                "pack_digest": pack_artifact.digest,
                "subject_digest": subject_digest,
            },
        )
        context = self._normalized_context(context, "policy-evaluate", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        # Whether the pack may be used at all is a precondition of the command, not
        # part of its idempotent result. The derived idempotency key is a function of
        # pack and subject with no time component, so checking after the duplicate
        # short-circuit would replay a stale decision once the pack expired instead
        # of refusing it.
        effective, reason = pack_effective_window(pack, at=context.occurred_at)
        if not effective:
            raise OAKError(reason, "policy pack is not effective at evaluation time")
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return PolicyEvaluationResult(
                case=duplicate,
                decision=self._latest_decision(duplicate),
                duplicate=True,
            )
        engine_port = loader()
        evaluation = engine_port.evaluate(pack, subject)
        current = DesignCase.from_document(current_document)
        decision_document: dict[str, Any] = {
            "schema_version": "0.1.0",
            "id": f"policy-decision.{pack['id']}.{pack['version']}.case-{current.version}",
            "version": "0.1.0",
            "status": "evaluated",
            "case_id": current.id,
            "pack_ref": pack_artifact.reference.to_document(),
            "subject_digest": subject_digest,
            "evaluated_at": context.occurred_at,
            "effective": True,
            "outcome": evaluation.outcome,
            "rule_results": [
                {
                    "rule_id": result.rule_id,
                    "matched": result.matched,
                    "outcome": result.outcome,
                    "reason_code": result.reason_code,
                    "obligations": list(result.obligations),
                }
                for result in evaluation.rule_results
            ],
            "reasons": list(evaluation.reasons),
            "obligations": list(evaluation.obligations),
            "extensions": {},
        }
        self._registry.validate("policy-decision.schema.json", decision_document)
        decision_artifact = json_artifact(
            artifact_id=str(decision_document["id"]),
            version=str(decision_document["version"]),
            kind="policy_decision",
            media_type=DECISION_MEDIA_TYPE,
            document=decision_document,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/policy_pack_refs"] = self._appended_references(
            extensions.get("oak.community/policy_pack_refs"),
            pack_artifact.reference,
        )
        extensions["oak.community/policy_decision_refs"] = self._appended_references(
            extensions.get("oak.community/policy_decision_refs"),
            decision_artifact.reference,
        )
        successor = current.revise(
            status=current.status,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            context=context,
            input_digest=input_digest,
            artifacts=(pack_artifact, decision_artifact),
            engine_id=engine_port.engine_id,
        )
        return PolicyEvaluationResult(
            case=published,
            decision=dict(json.loads(decision_artifact.content.decode("utf-8"))),
            duplicate=False,
        )

    def _subject(self, case_document: dict[str, Any]) -> dict[str, Any]:
        intent_value = case_document.get("intent_ref")
        if not isinstance(intent_value, dict):
            raise OAKError("OAK-POLICY-SUBJECT", "policy evaluation requires an interpreted intent")
        intent = self._repository.read_json_artifact(ArtifactReference.from_document(intent_value))
        subject: dict[str, Any] = {
            "case_id": str(case_document["id"]),
            "intent_spec": intent["spec"],
            "candidate": None,
        }
        selected = case_document.get("selected_candidate_ref")
        if isinstance(selected, dict):
            candidate = self._repository.read_json_artifact(
                ArtifactReference.from_document(selected)
            )
            pattern_value = candidate["extensions"].get("oak.community/pattern_ref")
            hard_requirements: list[Any] = []
            if isinstance(pattern_value, dict):
                pattern = self._repository.read_json_artifact(
                    ArtifactReference.from_document(pattern_value)
                )
                hard_requirements = list(pattern["hard_requirements"])
            subject["candidate"] = {
                "id": str(candidate["id"]),
                "variant": str(candidate["extensions"]["oak.community/pattern_variant"]),
                "components": [
                    {
                        "manifest_id": str(component["manifest_id"]),
                        "version": str(component["version"]),
                    }
                    for component in candidate["components"]
                ],
                "hard_requirements": hard_requirements,
            }
        return subject

    def _latest_decision(self, case_document: dict[str, Any]) -> dict[str, Any]:
        references = case_document.get("extensions", {}).get(
            "oak.community/policy_decision_refs", []
        )
        if not references:
            raise OAKError("OAK-DEPENDENCY-MISSING", "case has no recorded policy decision")
        return self._repository.read_json_artifact(ArtifactReference.from_document(references[-1]))

    @staticmethod
    def _appended_references(existing: Any, reference: ArtifactReference) -> list[dict[str, Any]]:
        references = [dict(item) for item in existing] if isinstance(existing, list) else []
        document = reference.to_document()
        if document not in references:
            references.append(document)
        return references

    def _publish(
        self,
        *,
        current: dict[str, Any],
        successor: DesignCase,
        context: CommandContext,
        input_digest: str,
        artifacts: tuple[Artifact, ...],
        engine_id: str,
    ) -> dict[str, Any]:
        manifest = self._repository.manifest()
        intent_ref = ArtifactReference.from_document(current["intent_ref"])
        intent = self._repository.read_json_artifact(intent_ref)
        source_value = intent["extensions"].get("oak.community/source_record")
        source_record_ref = (
            ArtifactReference.from_document(source_value)
            if isinstance(source_value, dict)
            else None
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type="policy_evaluated",
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
                ],
                "oak.community/policy_engine": engine_id,
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

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    def _check_tenant(self, context: CommandContext) -> None:
        if self._repository.manifest()["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")

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
