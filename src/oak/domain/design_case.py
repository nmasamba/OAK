# SPDX-License-Identifier: Apache-2.0
"""Immutable DesignCase lifecycle and successor rules."""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from oak.domain.artifacts import ArtifactReference
from oak.domain.errors import OAKError


class DesignCaseStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_CONFIRMATION = "needs_confirmation"
    READY_FOR_CANDIDATES = "ready_for_candidates"
    CANDIDATES_READY = "candidates_ready"
    CANDIDATE_SELECTED = "candidate_selected"
    ASSURANCE_PLANNED = "assurance_planned"
    BUNDLE_COMPILED = "bundle_compiled"
    DEPLOYMENT_APPROVED = "deployment_approved"
    DEPLOYED = "deployed"
    OBSERVING = "observing"
    CLOSED = "closed"


ALLOWED_TRANSITIONS: dict[DesignCaseStatus, frozenset[DesignCaseStatus]] = {
    DesignCaseStatus.DRAFT: frozenset(
        {DesignCaseStatus.NEEDS_CONFIRMATION, DesignCaseStatus.READY_FOR_CANDIDATES}
    ),
    DesignCaseStatus.NEEDS_CONFIRMATION: frozenset({DesignCaseStatus.READY_FOR_CANDIDATES}),
    DesignCaseStatus.READY_FOR_CANDIDATES: frozenset({DesignCaseStatus.CANDIDATES_READY}),
    DesignCaseStatus.CANDIDATES_READY: frozenset({DesignCaseStatus.CANDIDATE_SELECTED}),
    DesignCaseStatus.CANDIDATE_SELECTED: frozenset({DesignCaseStatus.ASSURANCE_PLANNED}),
    DesignCaseStatus.ASSURANCE_PLANNED: frozenset({DesignCaseStatus.BUNDLE_COMPILED}),
    DesignCaseStatus.BUNDLE_COMPILED: frozenset({DesignCaseStatus.DEPLOYMENT_APPROVED}),
    DesignCaseStatus.DEPLOYMENT_APPROVED: frozenset({DesignCaseStatus.DEPLOYED}),
    DesignCaseStatus.DEPLOYED: frozenset({DesignCaseStatus.OBSERVING}),
    DesignCaseStatus.OBSERVING: frozenset({DesignCaseStatus.NEEDS_CONFIRMATION}),
    DesignCaseStatus.CLOSED: frozenset(),
}


def next_patch_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise OAKError("OAK-CASE-VERSION", "case version is not a supported semantic version")
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


@dataclass(frozen=True, slots=True)
class DesignCase:
    id: str
    version: str
    status: DesignCaseStatus
    title: str
    tenant_id: str
    created_at: str
    updated_at: str
    interface_origin: str
    brief_refs: tuple[ArtifactReference, ...]
    intent_ref: ArtifactReference | None = None
    decision_cost_model_ref: ArtifactReference | None = None
    regulatory_nexus_ref: ArtifactReference | None = None
    evaluation_contract_ref: ArtifactReference | None = None
    assumptions: tuple[dict[str, Any], ...] = ()
    unresolved_questions: tuple[dict[str, Any], ...] = ()
    candidate_refs: tuple[ArtifactReference, ...] = ()
    selected_candidate_ref: ArtifactReference | None = None
    assurance_plan_ref: ArtifactReference | None = None
    deployment_bundle_ref: ArtifactReference | None = None
    runner_plan_ref: ArtifactReference | None = None
    approvals: tuple[dict[str, Any], ...] = ()
    audit_head: str | None = None
    extensions: dict[str, Any] | None = None

    def revise(
        self,
        *,
        status: DesignCaseStatus,
        updated_at: str,
        intent_ref: ArtifactReference | None = None,
        evaluation_contract_ref: ArtifactReference | None = None,
        assumptions: tuple[dict[str, Any], ...] | None = None,
        unresolved_questions: tuple[dict[str, Any], ...] | None = None,
        candidate_refs: tuple[ArtifactReference, ...] | None = None,
        selected_candidate_ref: ArtifactReference | None = None,
        assurance_plan_ref: ArtifactReference | None = None,
        deployment_bundle_ref: ArtifactReference | None = None,
        runner_plan_ref: ArtifactReference | None = None,
        extensions: dict[str, Any] | None = None,
        audit_head: str | None = None,
    ) -> "DesignCase":
        if status != self.status and status not in ALLOWED_TRANSITIONS[self.status]:
            raise OAKError(
                "OAK-CASE-TRANSITION-DENIED",
                f"transition from {self.status.value} to {status.value} is not allowed",
            )
        return replace(
            self,
            version=next_patch_version(self.version),
            status=status,
            updated_at=updated_at,
            intent_ref=self.intent_ref if intent_ref is None else intent_ref,
            evaluation_contract_ref=(
                self.evaluation_contract_ref
                if evaluation_contract_ref is None
                else evaluation_contract_ref
            ),
            assumptions=self.assumptions if assumptions is None else assumptions,
            unresolved_questions=(
                self.unresolved_questions if unresolved_questions is None else unresolved_questions
            ),
            candidate_refs=self.candidate_refs if candidate_refs is None else candidate_refs,
            selected_candidate_ref=(
                self.selected_candidate_ref
                if selected_candidate_ref is None
                else selected_candidate_ref
            ),
            assurance_plan_ref=(
                self.assurance_plan_ref if assurance_plan_ref is None else assurance_plan_ref
            ),
            deployment_bundle_ref=(
                self.deployment_bundle_ref
                if deployment_bundle_ref is None
                else deployment_bundle_ref
            ),
            runner_plan_ref=self.runner_plan_ref if runner_plan_ref is None else runner_plan_ref,
            extensions=self.extensions if extensions is None else extensions,
            audit_head=self.audit_head if audit_head is None else audit_head,
        )

    def with_audit_head(self, audit_head: str) -> "DesignCase":
        return replace(self, audit_head=audit_head)

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": "0.4.0",
            "id": self.id,
            "version": self.version,
            "status": self.status.value,
            "title": self.title,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "interface_origin": self.interface_origin,
            "brief_refs": [reference.to_document() for reference in self.brief_refs],
            "intent_ref": self.intent_ref.to_document() if self.intent_ref else None,
            "decision_cost_model_ref": (
                self.decision_cost_model_ref.to_document() if self.decision_cost_model_ref else None
            ),
            "regulatory_nexus_ref": (
                self.regulatory_nexus_ref.to_document() if self.regulatory_nexus_ref else None
            ),
            "evaluation_contract_ref": (
                self.evaluation_contract_ref.to_document() if self.evaluation_contract_ref else None
            ),
            "assumptions": list(self.assumptions),
            "unresolved_questions": list(self.unresolved_questions),
            "candidate_refs": [reference.to_document() for reference in self.candidate_refs],
            "selected_candidate_ref": (
                self.selected_candidate_ref.to_document() if self.selected_candidate_ref else None
            ),
            "assurance_plan_ref": (
                self.assurance_plan_ref.to_document() if self.assurance_plan_ref else None
            ),
            "deployment_bundle_ref": (
                self.deployment_bundle_ref.to_document() if self.deployment_bundle_ref else None
            ),
            "runner_plan_ref": (
                self.runner_plan_ref.to_document() if self.runner_plan_ref else None
            ),
            "approvals": list(self.approvals),
            "audit_head": self.audit_head,
            "extensions": self.extensions or {},
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "DesignCase":
        def optional_reference(field: str) -> ArtifactReference | None:
            value = document[field]
            return ArtifactReference.from_document(value) if isinstance(value, dict) else None

        return cls(
            id=str(document["id"]),
            version=str(document["version"]),
            status=DesignCaseStatus(str(document["status"])),
            title=str(document["title"]),
            tenant_id=str(document["tenant_id"]),
            created_at=str(document["created_at"]),
            updated_at=str(document["updated_at"]),
            interface_origin=str(document["interface_origin"]),
            brief_refs=tuple(
                ArtifactReference.from_document(reference) for reference in document["brief_refs"]
            ),
            intent_ref=optional_reference("intent_ref"),
            decision_cost_model_ref=optional_reference("decision_cost_model_ref"),
            regulatory_nexus_ref=optional_reference("regulatory_nexus_ref"),
            evaluation_contract_ref=optional_reference("evaluation_contract_ref"),
            assumptions=tuple(document["assumptions"]),
            unresolved_questions=tuple(document["unresolved_questions"]),
            candidate_refs=tuple(
                ArtifactReference.from_document(reference)
                for reference in document["candidate_refs"]
            ),
            selected_candidate_ref=optional_reference("selected_candidate_ref"),
            assurance_plan_ref=optional_reference("assurance_plan_ref"),
            deployment_bundle_ref=optional_reference("deployment_bundle_ref"),
            runner_plan_ref=optional_reference("runner_plan_ref"),
            approvals=tuple(document["approvals"]),
            audit_head=(str(document["audit_head"]) if document["audit_head"] else None),
            extensions=dict(document["extensions"]),
        )
