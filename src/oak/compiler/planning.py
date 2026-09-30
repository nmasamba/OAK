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
from oak.domain.runner_adapters import (
    ADAPTER_IDENTITY_BY_ID,
    CONTAINER_ADAPTER_ID,
    INSTALLATION_SCOPE_EXTENSION,
    ISOLATION_BY_ACKNOWLEDGEMENT,
    ISOLATION_STARTED_HARDENED,
    MAXIMUM_CONTAINERS,
    REVIEW_ADAPTER_DIGEST,
    REVIEW_ADAPTER_ID,
    REVIEW_ADAPTER_VERSION,
    REVIEW_PARAMETER_SCHEMA_DIGEST,
    container_name_for,
    installation_id_for,
)

BUNDLE_MEDIA_TYPE = "application/vnd.oak.deployment-bundle+json"
RUNNER_PLAN_MEDIA_TYPE = "application/vnd.oak.runner-plan+json"
REVIEW_MEDIA_TYPE = "application/vnd.oak.review-artifact+json"
ADAPTER_ID = REVIEW_ADAPTER_ID
ADAPTER_VERSION = REVIEW_ADAPTER_VERSION
ADAPTER_DIGEST = REVIEW_ADAPTER_DIGEST
PARAMETER_SCHEMA_DIGEST = REVIEW_PARAMETER_SCHEMA_DIGEST
# Canonical presentation order for operation kinds wherever compiled content lists them;
# the target profile's `permissions.allowed_operations` decides which of these appear.
OPERATION_KIND_ORDER = (
    "inventory",
    "validate",
    "render",
    "plan",
    "verify",
    "apply",
    "rollback",
    "destroy",
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
    installation_scope: str,
) -> CompiledReviewPlan:
    candidate_document = _document(candidate)
    _reject_superseded_execution(target)
    preflight_results = _target_preflight(candidate_document, target)
    blocked = [item["id"] for item in preflight_results if item["result"] == "fail"]
    if blocked:
        raise OAKError(
            "OAK-TARGET-INCOMPATIBLE",
            f"target failed required compiler preflight: {', '.join(blocked)}",
        )
    target_fingerprint = content_digest(canonical_json_bytes(target))
    allowed_kinds = [
        kind
        for kind in OPERATION_KIND_ORDER
        if kind in set(target["permissions"]["allowed_operations"])
    ]
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
            "operation_kinds": allowed_kinds,
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
            "reason": (
                "Compilation emits an inert, unsigned draft; execution authority is a "
                "separately signed plan signature plus per-action approvals, verified "
                "independently by the runner."
            ),
            "authorizes_execution": False,
        },
        registry,
    )
    # The policy is a function of the target, not a constant: the runner enforces these
    # clauses per requested operation kind, so a policy claiming read-only for a
    # mutation-capable target would deny the very plan this compile emits (RR-032).
    verification_policy = _review_artifact(
        f"verification-policy.{target['id']}",
        "verification_policy",
        "draft",
        {
            "allowed_status": "draft",
            "allowed_operation_kinds": allowed_kinds,
            "mutation_allowed": target["permissions"]["mutation_allowed"] is True,
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
        installation_scope=installation_scope,
        candidate_document=candidate_document,
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
            "install": [
                "Not provided by this bundle: execution requires a separately signed "
                "plan, per-action approvals, and independent runner verification."
            ],
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
            # A literal on purpose: tracking the repository version here would shift
            # every compiled digest on every release.
            "minimum_oak_version": "0.7.1",
            "target_constraints": _target_constraints(target),
            "known_incompatibilities": [
                "This bundle is not authorized for target execution on its own: dispatch "
                "requires a separately signed plan signature, current approvals, and "
                "independent runner verification."
            ],
        },
        "expires_at": _offset_timestamp(created_at, days=7),
        "extensions": {"oak.community/preflight_results": preflight_results},
    }


def _target_constraints(target: dict[str, Any]) -> list[str]:
    """Describe what the target actually permits, in its declared terms."""

    allowed = [
        kind
        for kind in OPERATION_KIND_ORDER
        if kind in set(target["permissions"]["allowed_operations"])
    ]
    listed = (
        " and ".join([", ".join(allowed[:-1]), allowed[-1]]) if len(allowed) > 1 else allowed[0]
    )
    mutation = target["permissions"]["mutation_allowed"] is True
    first = (
        "Non-production local target with mutation_allowed=true, acknowledged as "
        f"{target['execution']['mutation_acknowledgement']}"
        if mutation
        else "Non-production local target with mutation_allowed=false"
    )
    return [first, f"Only {listed} operations"]


def _runner_plan_document(
    *,
    case_ref: ArtifactReference,
    installation_scope: str,
    candidate_document: dict[str, Any],
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
    mutation = target["permissions"].get("mutation_allowed") is True
    if mutation:
        operations.extend(
            _mutation_operations(
                case_ref=case_ref,
                installation_scope=installation_scope,
                candidate_document=candidate_document,
                target=target,
                target_fingerprint=target_fingerprint,
                depends_on=previous[-1:],
            )
        )
    # A read-only plan's evidence policy is pinned byte for byte; only a plan that can
    # install admits the smoke-test metrics and the verified-removal results.
    evidence_categories = ["inventory", "preflight", "plan_diff", "status", "test_result"]
    if mutation:
        evidence_categories += ["aggregate_metric", "rollback_result"]
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
            "allowed_categories": evidence_categories,
            "maximum_bytes": 1_048_576,
            "redact_fields": ["credentials", "secrets", "environment"],
        },
        "extensions": {
            "oak.community/dispatch_allowed": False,
            # Only a plan that can install names its installation scope (the workspace),
            # which the runner needs to re-derive the installation identity; the
            # read-only plan's bytes are pinned and stay as they were.
            **({INSTALLATION_SCOPE_EXTENSION: installation_scope} if mutation else {}),
        },
    }


def _mutation_operations(
    *,
    case_ref: ArtifactReference,
    installation_scope: str,
    candidate_document: dict[str, Any],
    target: dict[str, Any],
    target_fingerprint: str,
    depends_on: list[str],
) -> list[dict[str, Any]]:
    execution = target.get("execution")
    if not isinstance(execution, dict):
        raise OAKError(
            "OAK-TARGET-EXECUTION",
            "mutation-capable target profile is missing its execution block",
        )
    allowed = set(target["permissions"]["allowed_operations"])
    isolation = ISOLATION_BY_ACKNOWLEDGEMENT[str(execution["mutation_acknowledgement"])]
    # One operation carries the whole topology: the runner refuses two operations of the
    # same kind, which keeps what it verified and what it executes the same list.
    installation_id = installation_id_for(
        case_ref.to_document(), str(target["id"]), installation_scope
    )
    parameters = {
        "case_id": case_ref.id,
        "target_id": str(target["id"]),
        "installation_id": installation_id,
        "isolation": isolation,
        "containers": _installation(installation_id, candidate_document, target),
    }
    identity = ADAPTER_IDENTITY_BY_ID[CONTAINER_ADAPTER_ID]
    verbs = ["get", "list", "create", "delete"]
    if isolation == ISOLATION_STARTED_HARDENED:
        # Starting runs the acknowledged image's own entrypoint; the envelope says so.
        verbs.append("execute")
    operations: list[dict[str, Any]] = []
    previous = list(depends_on)
    failure_by_kind = {
        "apply": "rollback",
        "rollback": "manual_recovery",
        "destroy": "manual_recovery",
    }
    for index, kind in enumerate(("apply", "rollback", "destroy"), start=1):
        if kind not in allowed:
            continue
        operation_id = f"operation.{kind}"
        operations.append(
            {
                "id": operation_id,
                "kind": kind,
                "adapter": dict(identity),
                "artifact_refs": [],
                "parameters": dict(parameters),
                "secret_references": [],
                "permissions": {
                    "resource_types": ["local-fixture-container"],
                    "verbs": list(verbs),
                    "namespaces": ["fixture"],
                    "network_destinations": [],
                },
                "timeout_seconds": 120,
                "retry_policy": {
                    "max_attempts": 1,
                    "backoff_seconds": 0,
                    "retryable_errors": [],
                },
                "idempotency_key": f"fixture-{kind}-operation-{index:02d}",
                "expected_state_digest": target_fingerprint,
                "failure_action": failure_by_kind[kind],
                "depends_on": previous[-1:],
            }
        )
        previous.append(operation_id)
    return operations


def installable_nodes(candidate_document: dict[str, Any]) -> list[tuple[str, str]]:
    """``(node id, component manifest id)`` for every topology node that has a component.

    A node without a component (a human role, say) has nothing to install. The component
    reference is ``<manifest id>@<version>``.
    """

    nodes: list[tuple[str, str]] = []
    for node in candidate_document["topology"]["nodes"]:
        reference = node.get("component_ref")
        if isinstance(reference, str) and reference:
            nodes.append((str(node["id"]), reference.rsplit("@", 1)[0]))
    return nodes


def _acknowledged_images(target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    execution = target.get("execution")
    entries = execution.get("component_images") if isinstance(execution, dict) else None
    if not isinstance(entries, list):
        return {}
    images: dict[str, dict[str, Any]] = {}
    for entry in entries:
        manifest_id = str(entry["manifest_id"])
        if manifest_id in images:
            raise OAKError(
                "OAK-TARGET-EXECUTION",
                f"execution.component_images lists {manifest_id} more than once",
            )
        images[manifest_id] = entry
    return images


def _installation(
    installation_id: str, candidate_document: dict[str, Any], target: dict[str, Any]
) -> list[dict[str, Any]]:
    images = _acknowledged_images(target)
    containers: list[dict[str, Any]] = []
    for node_id, manifest_id in installable_nodes(candidate_document):
        image = images.get(manifest_id)
        if image is None:  # pragma: no cover - preflight.installation refuses first
            raise OAKError(
                "OAK-TARGET-INCOMPATIBLE",
                f"target acknowledges no image for component {manifest_id}",
            )
        containers.append(
            {
                "node_id": node_id,
                "manifest_id": manifest_id,
                "container_name": container_name_for(installation_id, node_id),
                "image_reference": str(image["image_reference"]),
                "image_digest": str(image["image_digest"]),
            }
        )
    return containers


def _reject_superseded_execution(target: dict[str, Any]) -> None:
    """Refuse the single stand-in image that `component_images` superseded.

    Before this, a mutation target installed one container from its own image whatever
    the architecture was. Ignoring the old fields would silently change what a profile
    means, so a profile still declaring them is refused with the field to use instead.
    """

    execution = target.get("execution")
    if target["permissions"].get("mutation_allowed") is not True or not isinstance(execution, dict):
        return
    if "container_image_reference" in execution or "container_image_digest" in execution:
        raise OAKError(
            "OAK-TARGET-EXECUTION",
            "execution.container_image_reference and container_image_digest are superseded;"
            " declare execution.component_images, one acknowledged image per component",
        )


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
    results: list[dict[str, Any]] = [
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
            if required_operations.issubset(allowed)
            and (
                target["permissions"]["mutation_allowed"] is False
                or (
                    target.get("status") == "non-production-local"
                    and isinstance(target.get("execution"), dict)
                    and "rollback" in allowed
                )
            )
            else "fail",
            "reason": (
                "The target allows every required read-only operation and either no "
                "mutation or an acknowledged isolated reversible fixture mutation."
            ),
            "evidence": target["permissions"],
        },
        {
            "id": "preflight.rollback",
            "category": "rollback",
            "result": "pass"
            if target["permissions"]["mutation_allowed"] is False or "rollback" in allowed
            else "fail",
            "reason": (
                "Rollback is restoration of reviewed state, and any permitted mutation "
                "carries a typed rollback operation."
            ),
            "evidence": {"mutation_allowed": target["permissions"]["mutation_allowed"]},
        },
    ]
    if target["permissions"]["mutation_allowed"] is True:
        # Only a target that can install is asked whether it can install this
        # architecture; the read-only bundle's preflight list is pinned byte for byte.
        results.append(_installation_preflight(candidate, target))
    return results


def _installation_preflight(candidate: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    nodes = installable_nodes(candidate)
    images = _acknowledged_images(target)
    missing = sorted({manifest_id for _, manifest_id in nodes if manifest_id not in images})
    if not nodes:
        result, reason = "fail", "The selected candidate has no node with a component to install."
    elif len(nodes) > MAXIMUM_CONTAINERS:
        result, reason = "fail", "The candidate has more nodes than one install may create."
    elif missing:
        result = "fail"
        reason = (
            "The target acknowledges no image for "
            + ", ".join(missing)
            + "; declare each in execution.component_images."
        )
    else:
        result = "pass"
        reason = "Every installable node's component has an acknowledged, digest-pinned image."
    return {
        "id": "preflight.installation",
        "category": "compatibility",
        "result": result,
        "reason": reason,
        "evidence": {
            "nodes": [
                {"node_id": node_id, "manifest_id": manifest_id} for node_id, manifest_id in nodes
            ],
            "acknowledged_components": sorted(images),
            "missing_components": missing,
        },
    }


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
