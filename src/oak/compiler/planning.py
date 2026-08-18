# SPDX-License-Identifier: Apache-2.0
"""Deterministic non-executing deployment bundle and typed runner-plan compiler."""

import copy
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)

BUNDLE_MEDIA_TYPE = "application/vnd.oak.deployment-bundle+json"
RUNNER_PLAN_MEDIA_TYPE = "application/vnd.oak.runner-plan+json"
REVIEW_MEDIA_TYPE = "application/vnd.oak.review-artifact+json"
ADAPTER_ID = "adapter.local-review"
ADAPTER_VERSION = "0.1.0"
ADAPTER_DIGEST = content_digest(
    canonical_json_bytes(
        {"id": ADAPTER_ID, "version": ADAPTER_VERSION, "authority": "read-only-planning"}
    )
)
PARAMETER_SCHEMA_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "allowed_keys": ["artifact", "mode", "target_profile_id"],
            "additional_properties": False,
        }
    )
)


@dataclass(frozen=True, slots=True)
class CompiledReviewPlan:
    review_artifacts: tuple[Artifact, ...]
    bundle: Artifact
    runner_plan: Artifact
    semantic_manifest: Artifact

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return (*self.review_artifacts, self.bundle, self.runner_plan)


def compile_review_plan(
    *,
    case_ref: ArtifactReference,
    intent: dict[str, Any],
    intent_ref: ArtifactReference,
    evaluation_contract_ref: ArtifactReference,
    candidate: Artifact,
    decision: Artifact,
    assurance: Artifact,
    target: dict[str, Any],
    catalogue_snapshot: Artifact,
    registry: SchemaRegistry,
    created_at: str,
) -> CompiledReviewPlan:
    candidate_document = _document(candidate)
    preflight_results = _target_preflight(candidate_document, target)
    blocked = [item["id"] for item in preflight_results if item["result"] == "fail"]
    if blocked:
        raise OAKError(
            "OAK-TARGET-INCOMPATIBLE",
            f"target failed required compiler preflight: {', '.join(blocked)}",
        )
    target_fingerprint = content_digest(canonical_json_bytes(target))
    semantic = _review_artifact(
        f"semantic.{candidate.id}.{target['id']}",
        "semantic_manifest",
        "generated",
        {
            "compiler_version": "community-local-plan-1.0.0",
            "intent_spec_digest": content_digest(canonical_json_bytes(intent["spec"])),
            "candidate": _semantic_candidate(candidate_document),
            "target_profile": target,
            "target_fingerprint": target_fingerprint,
            "component_lock": [
                {
                    "manifest_id": item["manifest_id"],
                    "version": item["version"],
                    "digest": item["digest"],
                }
                for item in candidate_document["components"]
            ],
            "operation_kinds": ["inventory", "validate", "render", "plan", "verify"],
        },
        registry,
    )
    sbom = _review_artifact(
        f"sbom.{candidate.id}",
        "sbom_summary",
        "generated",
        {
            "format": "OAK fixture component summary",
            "components": [
                {
                    "id": item["manifest_id"],
                    "version": item["version"],
                    "digest": item["digest"],
                }
                for item in candidate_document["components"]
            ],
        },
        registry,
    )
    provenance = _review_artifact(
        f"provenance.{candidate.id}",
        "provenance_summary",
        "generated",
        {
            "semantic_manifest_digest": semantic.digest,
            "candidate_digest": candidate.digest,
            "decision_digest": decision.digest,
            "assurance_digest": assurance.digest,
            "catalogue_snapshot_digest": catalogue_snapshot.digest,
        },
        registry,
    )
    signature = _review_artifact(
        f"signature.pending.{candidate.id}",
        "signature_marker",
        "not_signed",
        {
            "reason": "Sprint 2 compiles review artifacts only; signing is not implemented.",
            "authorizes_execution": False,
        },
        registry,
    )
    verification_policy = _review_artifact(
        "verification-policy.draft-local-review",
        "verification_policy",
        "draft",
        {
            "allowed_status": "draft",
            "allowed_operation_kinds": ["inventory", "validate", "render", "plan", "verify"],
            "mutation_allowed": False,
            "requires_signature_before_dispatch": True,
            "requires_approval_before_dispatch": True,
        },
        registry,
    )
    bundle_document = _bundle_document(
        intent_ref=intent_ref,
        evaluation_contract_ref=evaluation_contract_ref,
        candidate_document=candidate_document,
        decision=decision,
        target=target,
        target_fingerprint=target_fingerprint,
        semantic=semantic,
        sbom=sbom,
        provenance=provenance,
        signature=signature,
        verification_policy=verification_policy,
        preflight_results=preflight_results,
        created_at=created_at,
    )
    registry.validate("deployment-bundle.schema.json", bundle_document)
    bundle = json_artifact(
        artifact_id=str(bundle_document["id"]),
        version=str(bundle_document["version"]),
        kind="deployment_bundle",
        media_type=BUNDLE_MEDIA_TYPE,
        document=bundle_document,
    )
    runner_document = _runner_plan_document(
        case_ref=case_ref,
        bundle=bundle,
        target=target,
        target_fingerprint=target_fingerprint,
        semantic=semantic,
        signature=signature,
        verification_policy=verification_policy,
        created_at=created_at,
    )
    registry.validate("runner-plan.schema.json", runner_document)
    _reject_execution_fields(runner_document)
    runner_plan = json_artifact(
        artifact_id=str(runner_document["id"]),
        version=str(runner_document["version"]),
        kind="runner_plan",
        media_type=RUNNER_PLAN_MEDIA_TYPE,
        document=runner_document,
    )
    return CompiledReviewPlan(
        review_artifacts=(semantic, sbom, provenance, signature, verification_policy),
        bundle=bundle,
        runner_plan=runner_plan,
        semantic_manifest=semantic,
    )


def _review_artifact(
    identifier: str,
    artifact_type: str,
    status: str,
    content: dict[str, Any],
    registry: SchemaRegistry,
) -> Artifact:
    document = {
        "schema_version": "0.4.0",
        "id": identifier,
        "version": "0.1.0",
        "artifact_type": artifact_type,
        "status": status,
        "content": content,
        "extensions": {},
    }
    registry.validate("review-artifact.schema.json", document)
    return json_artifact(
        artifact_id=identifier,
        version="0.1.0",
        kind="review_artifact",
        media_type=REVIEW_MEDIA_TYPE,
        document=document,
    )


def _semantic_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate["id"],
        "version": candidate["version"],
        "variant": candidate["extensions"]["oak.community/pattern_variant"],
        "status": candidate["status"],
        "topology": candidate["topology"],
        "components": candidate["components"],
        "hard_constraints": candidate["hard_constraints"],
        "objectives": candidate["objectives"],
        "pareto": candidate["pareto"],
        "explanation": candidate["extensions"]["oak.community/explanation"],
        "estimator_metadata": candidate["extensions"]["oak.community/estimator_metadata"],
        "target_requirements": candidate["extensions"]["oak.community/target_requirements"],
    }


def _bundle_document(
    *,
    intent_ref: ArtifactReference,
    evaluation_contract_ref: ArtifactReference,
    candidate_document: dict[str, Any],
    decision: Artifact,
    target: dict[str, Any],
    target_fingerprint: str,
    semantic: Artifact,
    sbom: Artifact,
    provenance: Artifact,
    signature: Artifact,
    verification_policy: Artifact,
    preflight_results: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "0.3.0",
        "id": f"bundle.{candidate_document['id']}.{target['id']}",
        "version": "0.1.0",
        "status": "compiled",
        "created_at": created_at,
        "architecture_decision_ref": decision.reference.to_document(),
        "intent_ref": intent_ref.to_document(),
        "evaluation_contract_ref": evaluation_contract_ref.to_document(),
        "target": {
            "class": "local",
            "fingerprint": target_fingerprint,
            "environment": target["environment"],
            "tenant_id": target["tenant_id"],
            "network_mode": target["network"]["mode"],
        },
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION, "digest": ADAPTER_DIGEST},
        "component_lock": [
            {
                "manifest_id": item["manifest_id"],
                "version": item["version"],
                "digest": item["digest"],
                "licence_decision": "allowed",
                "source": "Digest-verified Community catalogue snapshot",
            }
            for item in candidate_document["components"]
        ],
        "artifacts": [semantic.reference.to_document()],
        "secret_references": [],
        "preflight_checks": [
            {
                "id": item["id"],
                "category": item["category"],
                "required": item["result"] != "not_applicable",
                "failure_action": "block",
            }
            for item in preflight_results
        ],
        "procedures": {
            "plan": ["Inspect the normalized semantic manifest and produce a read-only diff."],
            "install": ["Deferred until signed-plan, approval and runner gates are implemented."],
            "verify": [
                "Validate digests, target identity, no-egress policy and offline fixture results."
            ],
            "backup": ["Preserve the content-digested public fixture corpus."],
            "restore": ["Rebuild derived indexes from the public fixture corpus."],
            "rollback": ["Return to the deterministic cited-passage baseline."],
            "upgrade": ["Compile a new immutable candidate and bundle."],
            "downgrade": ["Restore a previously reviewed immutable bundle."],
            "uninstall": ["Remove only derived non-production fixture artifacts."],
            "decommission": ["Verify derived deletion and retain approved aggregate evidence."],
        },
        "supply_chain": {
            "bundle_digest": semantic.digest,
            "sbom_ref": sbom.reference.to_document(),
            "provenance_ref": provenance.reference.to_document(),
            "signature_ref": signature.reference.to_document(),
            "verification_policy_ref": verification_policy.reference.to_document(),
        },
        "approval_policy": {
            "required_roles": ["environment-owner", "security-reviewer"],
            "separation_of_duties": True,
            "target_bound": True,
            "digest_bound": True,
        },
        "compatibility": {
            "minimum_oak_version": "0.5.0.dev5",
            "target_constraints": [
                "Non-production local target with mutation_allowed=false",
                "Only inventory, validate, render, plan and verify operations",
            ],
            "known_incompatibilities": [
                "This Sprint 2 bundle is not authorized or signed for target execution."
            ],
        },
        "expires_at": _offset_timestamp(created_at, days=7),
        "extensions": {"oak.community/preflight_results": preflight_results},
    }


def _runner_plan_document(
    *,
    case_ref: ArtifactReference,
    bundle: Artifact,
    target: dict[str, Any],
    target_fingerprint: str,
    semantic: Artifact,
    signature: Artifact,
    verification_policy: Artifact,
    created_at: str,
) -> dict[str, Any]:
    operation_kinds = ("inventory", "validate", "render", "plan", "verify")
    operations = []
    previous: list[str] = []
    for index, kind in enumerate(operation_kinds, start=1):
        operation_id = f"operation.{kind}"
        operations.append(
            {
                "id": operation_id,
                "kind": kind,
                "adapter": {
                    "id": ADAPTER_ID,
                    "version": ADAPTER_VERSION,
                    "digest": ADAPTER_DIGEST,
                    "parameter_schema_digest": PARAMETER_SCHEMA_DIGEST,
                },
                "artifact_refs": [semantic.reference.to_document()],
                "parameters": {
                    "mode": "read-only",
                    "target_profile_id": target["id"],
                    "artifact": semantic.id,
                },
                "secret_references": [],
                "permissions": {
                    "resource_types": ["local-fixture-review"],
                    "verbs": ["get", "list"],
                    "namespaces": ["fixture"],
                    "network_destinations": [],
                },
                "timeout_seconds": 60,
                "retry_policy": {
                    "max_attempts": 1,
                    "backoff_seconds": 0,
                    "retryable_errors": [],
                },
                "idempotency_key": f"fixture-{kind}-operation-{index:02d}",
                "expected_state_digest": target_fingerprint,
                "failure_action": "block",
                "depends_on": previous[-1:],
            }
        )
        previous.append(operation_id)
    plan_digest = content_digest(
        canonical_json_bytes(
            {
                "bundle_semantic_digest": semantic.digest,
                "target_fingerprint": target_fingerprint,
                "operations": operations,
            }
        )
    )
    return {
        "schema_version": "0.4.0",
        "id": f"runner-plan.{bundle.id}",
        "version": "0.1.0",
        "status": "draft",
        "created_at": created_at,
        "expires_at": _offset_timestamp(created_at, days=1),
        "design_case_ref": case_ref.to_document(),
        "bundle_ref": bundle.reference.to_document(),
        "target": {
            "id": target["id"],
            "fingerprint": target_fingerprint,
            "tenant_id": target["tenant_id"],
            "environment": target["environment"],
            "network_mode": _runner_network_mode(str(target["network"]["mode"])),
        },
        "operations": operations,
        "approvals": [],
        "supply_chain": {
            "plan_digest": plan_digest,
            "signature_ref": signature.reference.to_document(),
            "verification_policy_ref": verification_policy.reference.to_document(),
        },
        "lease_policy": {"maximum_seconds": 300, "heartbeat_seconds": 30, "require_nonce": True},
        "evidence_policy": {
            "allowed_categories": ["inventory", "preflight", "plan_diff", "status", "test_result"],
            "maximum_bytes": 1_048_576,
            "redact_fields": ["credentials", "secrets", "environment"],
        },
        "extensions": {"oak.community/dispatch_allowed": False},
    }


def _reject_execution_fields(document: Any) -> None:
    if isinstance(document, dict):
        for key, value in document.items():
            if str(key).casefold() in {"command", "shell", "executable", "argv"}:
                raise ValueError("runner plan contains a forbidden execution field")
            _reject_execution_fields(value)
    elif isinstance(document, list):
        for value in document:
            _reject_execution_fields(value)


def _runner_network_mode(target_mode: str) -> str:
    mapping = {
        "local": "local",
        "isolated-no-egress": "disconnected",
        "outbound-only": "outbound_only",
        "disconnected": "disconnected",
        "air-gapped": "air_gapped",
    }
    return mapping[target_mode]


def _target_preflight(candidate: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = candidate["extensions"]["oak.community/target_requirements"]
    minimum = requirements["minimum_resources"]
    capacity_passes = float(target["capacity"]["ram_gib"]) >= float(minimum["ram_gib"]) and float(
        target["capacity"]["storage_gib"]
    ) >= float(minimum["storage_gib"])
    platform = target["platform"]
    compatibility_passes = (
        platform["operating_system"] in requirements["operating_systems"]
        and platform["architecture"] in requirements["cpu_architectures"]
        and set(requirements["accelerators"]).issubset(platform["accelerators"])
        and set(requirements["drivers"]).issubset(platform["drivers"])
    )
    allowed = set(target["permissions"]["allowed_operations"])
    required_operations = {"inventory", "validate", "render", "plan", "verify"}
    return [
        {
            "id": "preflight.capacity",
            "category": "capacity",
            "result": "pass" if capacity_passes else "fail",
            "reason": "Declared RAM and storage satisfy component minimums."
            if capacity_passes
            else "Declared RAM or storage is below component minimums.",
            "evidence": {"declared": target["capacity"], "required": minimum},
        },
        {
            "id": "preflight.compatibility",
            "category": "compatibility",
            "result": "pass" if compatibility_passes else "fail",
            "reason": "Declared platform satisfies component compatibility requirements."
            if compatibility_passes
            else "Declared platform does not satisfy component compatibility requirements.",
            "evidence": {
                "declared": platform,
                "required": {
                    key: requirements[key]
                    for key in (
                        "operating_systems",
                        "cpu_architectures",
                        "accelerators",
                        "drivers",
                    )
                },
            },
        },
        {
            "id": "preflight.network",
            "category": "network",
            "result": "pass",
            "reason": "The plan requests no network destinations or target ports.",
            "evidence": {
                "declared_mode": target["network"]["mode"],
                "network_destinations": [],
            },
        },
        {
            "id": "preflight.certificate",
            "category": "certificate",
            "result": "not_applicable",
            "reason": "The non-executing local plan opens no target transport.",
            "evidence": {"target_transport": None},
        },
        {
            "id": "preflight.policy",
            "category": "policy",
            "result": "pass"
            if target["permissions"]["mutation_allowed"] is False
            and required_operations.issubset(allowed)
            else "fail",
            "reason": "The target allows every required read-only operation and no mutation.",
            "evidence": target["permissions"],
        },
        {
            "id": "preflight.rollback",
            "category": "rollback",
            "result": "pass",
            "reason": "No target mutation occurs; rollback remains restoration of reviewed state.",
            "evidence": {"mutation_allowed": False},
        },
    ]


def _offset_timestamp(value: str, *, days: int) -> str:
    from datetime import datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(days=days)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _document(artifact: Artifact) -> dict[str, Any]:
    import json

    document = json.loads(artifact.content)
    if not isinstance(document, dict):  # pragma: no cover - guaranteed by construction
        raise TypeError("canonical artifact must contain an object")
    return copy.deepcopy(document)
