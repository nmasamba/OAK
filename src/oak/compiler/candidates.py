# SPDX-License-Identifier: Apache-2.0
"""Provider-neutral candidate expansion, constraints, estimators and Pareto comparison."""

from typing import Any

from oak.compiler.catalogue import CompiledCatalogue
from oak.compiler.research_designs import ResearchedDesign
from oak.contracts import SchemaRegistry
from oak.domain import (
    COMPARISON_EXTENSION,
    COMPARISON_RULE_VERSION,
    RESEARCH_EXTENSION,
    Artifact,
    ArtifactReference,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)

CANDIDATE_MEDIA_TYPE = "application/vnd.oak.architecture-candidate+json"
EVALUATION_CONTRACT_MEDIA_TYPE = "application/vnd.oak.evaluation-contract+json"
CANDIDATE_IDS = {
    "simpler_baseline": "candidate-00",
    "minimum_sufficient": "candidate-01",
    "balanced_enterprise": "candidate-03",
    "high_assurance_sovereign": "candidate-04",
}
VARIANT_CONTRACT_VALUES = {
    "simpler_baseline": "other",
    "minimum_sufficient": "minimum_sufficient",
    "balanced_enterprise": "balanced_enterprise",
    "high_assurance_sovereign": "high_assurance_sovereign",
}


def create_evaluation_contract(intent: dict[str, Any], registry: SchemaRegistry) -> Artifact:
    intent_key = str(intent["id"]).removeprefix("intent.")
    dataset_digest = content_digest(canonical_json_bytes({"intent_spec": intent["spec"]}))
    document = {
        "schema_version": "0.3.0",
        "id": f"evaluation.{intent_key}",
        "version": "0.1.0",
        "status": "draft",
        "scope": "generated_system",
        "user_outcome": (
            "Return a supported answer with verifiable public passages or explicitly abstain."
        ),
        "baseline": "Deterministic lexical search returning cited passages.",
        "populations": [
            {
                "id": "population.public-fixture",
                "description": (
                    "Synthetic public questions with present, absent and conflicting answers."
                ),
                "subgroups": ["answer_present", "answer_absent", "conflicting_passages"],
            }
        ],
        "datasets": [
            {
                "id": "dataset.public-fixture",
                "purpose": "offline_test",
                "source": "Synthetic public-manual evaluation fixture",
                "version": "1.0.0",
                "digest": dataset_digest,
                "permitted_use": "Non-production offline OAK evaluation only",
                "leakage_review": "Fixture outcomes are not used as component input.",
                "retention": "Retain with the Apache-2.0 test fixture.",
            }
        ],
        "metrics": [
            _metric(
                "metric.citation-correctness",
                "Citation correctness",
                "quality",
                "at_least",
                "proportion",
                0.98,
            ),
            _metric(
                "metric.unsupported-assertion-rate",
                "Unsupported assertion rate",
                "safety",
                "at_most",
                "proportion",
                0.01,
            ),
            _metric(
                "metric.latency-p95",
                "Interactive latency p95",
                "latency",
                "at_most",
                "milliseconds",
                5000,
            ),
        ],
        "gates": [
            {
                "id": "gate.offline-fixture",
                "stage": "offline",
                "required_metric_ids": [
                    "metric.citation-correctness",
                    "metric.unsupported-assertion-rate",
                    "metric.latency-p95",
                ],
                "critical_failures": [
                    "A response is labelled supported when its citation does not entail it."
                ],
                "approver_roles": ["domain-reviewer", "security-reviewer"],
            }
        ],
        "monitoring": {
            "window": "Per immutable fixture run",
            "cadence": "On every candidate dependency digest change",
            "degradation_rules": ["Block when a required metric is unknown or fails."],
            "rollback_rules": ["Return to the deterministic cited-passage baseline."],
        },
        "owner": "community-fixture-owner",
        "expires_at": None,
        "extensions": {},
    }
    registry.validate("evaluation-contract.schema.json", document)
    return json_artifact(
        artifact_id=str(document["id"]),
        version=str(document["version"]),
        kind="evaluation_contract",
        media_type=EVALUATION_CONTRACT_MEDIA_TYPE,
        document=document,
    )


def generate_candidates(
    intent: dict[str, Any],
    intent_ref: ArtifactReference,
    evaluation_contract_ref: ArtifactReference,
    catalogue: CompiledCatalogue,
    registry: SchemaRegistry,
    *,
    generated_at: str,
    research_designs: tuple[ResearchedDesign, ...] = (),
) -> tuple[Artifact, ...]:
    documents: list[dict[str, Any]] = []
    manifest_artifacts = {artifact.id: artifact for artifact in catalogue.manifests}
    pattern_artifacts = {artifact.id: artifact for artifact in catalogue.patterns}
    plan: list[tuple[str, dict[str, Any], str, dict[str, Any] | None]] = [
        (pattern_id, pattern, CANDIDATE_IDS[str(pattern["variant"])], None)
        for pattern_id, pattern in sorted(
            catalogue.pattern_documents.items(),
            key=lambda item: CANDIDATE_IDS[str(item[1]["variant"])],
        )
    ]
    # Researched designs (ADR-0018): the curated pattern with a binding applied, numbered
    # from candidate-05 in pattern-id order, each carrying its research extension.
    plan.extend(
        (design.pattern_id, design.pattern, design.candidate_id, design.research)
        for design in research_designs
    )
    for pattern_id, pattern, candidate_id, research in plan:
        variant = str(pattern["variant"])
        components: list[tuple[dict[str, Any], Artifact, dict[str, Any]]] = []
        for requirement in pattern["component_requirements"]:
            manifest_id = str(requirement["manifest_id"])
            components.append(
                (
                    requirement,
                    manifest_artifacts[manifest_id],
                    catalogue.manifest_documents[manifest_id],
                )
            )
        constraints = _hard_constraints(intent, components, catalogue)
        feasible = all(item["result"] == "pass" for item in constraints)
        rejection_reasons = [
            f"{item['id']}: {item['reason']}"
            for item in constraints
            if item["result"] in {"fail", "unknown"}
        ]
        pattern_ref = pattern_artifacts[pattern_id].reference
        document: dict[str, Any] = {
            "schema_version": "0.3.0",
            "id": candidate_id,
            "version": "0.1.0",
            "variant": VARIANT_CONTRACT_VALUES[variant],
            "status": "feasible" if feasible else "infeasible",
            "intent_ref": intent_ref.to_document(),
            "evaluation_contract_ref": evaluation_contract_ref.to_document(),
            "generated_at": generated_at,
            "generator_version": "community-candidate-generator-1.0.0",
            "topology": _topology(pattern, components),
            "components": [
                {
                    "manifest_id": artifact.id,
                    "version": artifact.version,
                    "digest": artifact.digest,
                    "purpose": requirement["purpose"],
                    "required": requirement["required"],
                }
                for requirement, artifact, _manifest in components
            ],
            "hard_constraints": constraints,
            "objectives": _objectives(components),
            "pareto": {
                "frontier_member": False,
                "dominated_by": [],
                "preference_weights_ref": "community-fixture-weights-1.0.0",
                "sensitivity_summary": "Not compared until feasibility is established.",
            },
            "assumptions": [
                "Objective ranges are synthetic predictions for compiler verification only."
            ],
            "omissions": (
                ["No generated answer; the reviewer reads cited passages."]
                if variant == "simpler_baseline"
                else []
            ),
            "risks": _risks(variant, feasible, researched=research is not None),
            "operational_requirements": [
                "Operate without runtime egress and retain the public source digest."
            ],
            "rejection_reasons": rejection_reasons,
            "evidence_refs": sorted(
                {
                    str(evidence["id"])
                    for _requirement, _artifact, manifest in components
                    for evidence in manifest["evidence"]
                }
            ),
            "extensions": {
                "oak.community/catalogue_snapshot_ref": catalogue.snapshot.reference.to_document(),
                "oak.community/pattern_ref": pattern_ref.to_document(),
                "oak.community/pattern_variant": variant,
                "oak.community/estimator_metadata": _estimator_metadata(),
                "oak.community/target_requirements": _target_requirements(
                    [manifest for _requirement, _artifact, manifest in components]
                ),
            },
        }
        if research is not None:
            manifests = [manifest for _requirement, _artifact, manifest in components]
            document["extensions"][RESEARCH_EXTENSION] = research
            document["extensions"][COMPARISON_EXTENSION] = classify_comparison(
                constraints, manifests
            )
        documents.append(document)

    _apply_pareto(documents)
    for document in documents:
        document["extensions"]["oak.community/explanation"] = _explanation(document, documents)
        registry.validate("architecture-candidate.schema.json", document)
    return tuple(
        json_artifact(
            artifact_id=str(document["id"]),
            version=str(document["version"]),
            kind="architecture_candidate",
            media_type=CANDIDATE_MEDIA_TYPE,
            document=document,
        )
        for document in documents
    )


def _metric(
    identifier: str, name: str, kind: str, direction: str, unit: str, threshold: float
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "kind": kind,
        "direction": direction,
        "unit": unit,
        "aggregation": "Deterministic synthetic fixture result",
        "threshold": threshold,
        "subgroup_floor": None,
        "confidence_method": "Exact fixture cases; no production inference",
        "sample_requirement": "100 deterministic synthetic cases",
        "owner": "community-fixture-owner",
    }


def _hard_constraints(
    intent: dict[str, Any],
    components: list[tuple[dict[str, Any], Artifact, dict[str, Any]]],
    catalogue: CompiledCatalogue,
) -> list[dict[str, Any]]:
    spec = intent["spec"]
    manifests = [manifest for _requirement, _artifact, manifest in components]
    eligibility_failures = [
        artifact.id
        for _requirement, artifact, _manifest in components
        if not catalogue.eligibility[artifact.id][0]
    ]
    constraints = [
        _constraint(
            "constraint.catalogue-eligibility",
            "pass" if not eligibility_failures else "fail",
            "All component manifests are eligible under the snapshot policy."
            if not eligibility_failures
            else f"Ineligible manifests: {', '.join(sorted(eligibility_failures))}.",
            ["OAK-FR-CAT-001", "OAK-FR-CAT-004"],
        ),
        _hardware_constraint(spec.get("hardware", {}), manifests),
        _deployment_constraint(spec.get("deployment_environment", {}), manifests),
        _security_constraint(spec.get("security_tenancy", {}), manifests),
        _licence_constraint(manifests),
        _locality_constraint(spec.get("data", {}), manifests),
        _compatibility_constraint(manifests),
    ]
    return constraints


def _constraint(
    identifier: str, result: str, reason: str, requirement_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": identifier,
        "requirement_ids": requirement_ids,
        "kind": "hard",
        "expression": identifier.removeprefix("constraint.").replace("-", "_") + " == satisfied",
        "result": result,
        "reason": reason,
        "evidence_refs": [],
    }


def _hardware_constraint(
    hardware: dict[str, Any], manifests: list[dict[str, Any]]
) -> dict[str, Any]:
    unpublished = _unpublished_minimums(manifests)
    required_ram = max(
        float(item["targets"]["minimum_resources"].get("ram_gib", 0)) for item in manifests
    )
    required_storage = sum(
        float(item["targets"]["minimum_resources"].get("storage_gib", 0)) for item in manifests
    )
    required_accelerators = sorted(
        {value for item in manifests for value in item["targets"]["accelerators"]}
    )
    ram = hardware.get("ram_gib")
    storage = hardware.get("storage_gib")
    accelerators = hardware.get("accelerators")
    if unpublished:
        result, reason = (
            "unknown",
            f"Minimum resources are not published for {', '.join(unpublished)}.",
        )
    elif not isinstance(ram, (int, float)) or not isinstance(storage, (int, float)):
        result, reason = "unknown", "Target RAM or storage is unknown."
    elif float(ram) < required_ram or float(storage) < required_storage:
        result, reason = (
            "fail",
            f"Requires {required_ram:g} GiB RAM and {required_storage:g} GiB storage.",
        )
    elif required_accelerators:
        if not isinstance(accelerators, list):
            result, reason = "unknown", "Required accelerator compatibility is unconfirmed."
        elif not set(required_accelerators).issubset(set(accelerators)):
            result, reason = (
                "fail",
                "Declared accelerators do not satisfy component requirements.",
            )
        else:
            result, reason = "pass", "Declared hardware satisfies component minimum resources."
    else:
        result, reason = "pass", "Declared hardware satisfies component minimum resources."
    return _constraint("constraint.hardware", result, reason, ["OAK-FR-ARC-002"])


def _deployment_constraint(
    deployment: dict[str, Any], manifests: list[dict[str, Any]]
) -> dict[str, Any]:
    modes = deployment.get("modes")
    if not isinstance(modes, list):
        result, reason = "unknown", "Deployment mode is unknown."
    elif "local" not in modes:
        result, reason = "fail", "The fixture supports only the confirmed local deployment mode."
    elif any(not item["deployment"]["modes"] and _is_researched(item) for item in manifests):
        result, reason = (
            "unknown",
            "Deployment modes are not published for "
            + ", ".join(
                sorted(
                    str(item["id"])
                    for item in manifests
                    if not item["deployment"]["modes"] and _is_researched(item)
                )
            )
            + ".",
        )
    elif any(not item["deployment"]["modes"] for item in manifests):
        result, reason = "fail", "A component declares no supported deployment mode."
    else:
        result, reason = "pass", "The local fixture deployment mode is supported."
    return _constraint("constraint.deployment", result, reason, ["OAK-FR-ARC-002"])


def _security_constraint(
    security: dict[str, Any], manifests: list[dict[str, Any]]
) -> dict[str, Any]:
    del security
    external_calls = [call for item in manifests for call in item["deployment"]["external_calls"]]
    if external_calls:
        result, reason = "fail", "A component requires runtime external calls."
    else:
        result, reason = "pass", "No component requires runtime external calls."
    return _constraint("constraint.security", result, reason, ["OAK-NFR-SEC-003"])


def _licence_constraint(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = all(
        item["availability_class"] in {"osi_open_source_software", "osi_open_source_ai"}
        and item["licensing"]["transitive_review"] == "passed"
        for item in manifests
    )
    if allowed:
        reason = "All component and transitive licence reviews passed."
    elif _licence_reviews_pending(manifests):
        reason = "A component licence or transitive review is pending."
    else:
        reason = "A component licence or transitive review is not eligible."
    return _constraint(
        "constraint.licence",
        "pass" if allowed else "fail",
        reason,
        ["OAK-FR-CAT-002", "OAK-FR-CAT-003"],
    )


def _locality_constraint(data: dict[str, Any], manifests: list[dict[str, Any]]) -> dict[str, Any]:
    classifications = data.get("classifications")
    if not isinstance(classifications, list) or not classifications:
        result, reason = "unknown", "Data classification is unknown."
    elif any(value != "public" for value in classifications):
        result, reason = "fail", "The synthetic catalogue is eligible only for public fixture data."
    elif any(item["deployment"]["air_gap_suitability"] == "unsupported" for item in manifests):
        result, reason = "fail", "A component cannot satisfy local data handling."
    else:
        result, reason = "pass", "Public fixture data remains on the local target."
    return _constraint("constraint.data-locality", result, reason, ["OAK-FR-ARC-002"])


def _compatibility_constraint(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    requirements = _target_requirements(manifests)
    compatible = bool(
        all(item["interfaces"] for item in manifests)
        and requirements["operating_systems"]
        and requirements["cpu_architectures"]
    )
    unpublished = sorted(
        str(item["id"])
        for item in manifests
        if _is_researched(item)
        and (
            not item["interfaces"]
            or not item["targets"]["operating_systems"]
            or not item["targets"]["cpu_architectures"]
        )
    )
    if compatible:
        result, reason = "pass", "Every component exposes a versioned interface."
    elif unpublished:
        result, reason = (
            "unknown",
            "Interfaces, operating systems or CPU architectures are not published for "
            f"{', '.join(unpublished)}.",
        )
    else:
        result, reason = "fail", "A component has no compatible interface."
    return _constraint("constraint.compatibility", result, reason, ["OAK-FR-ARC-007"])


def _is_researched(manifest: dict[str, Any]) -> bool:
    return RESEARCH_EXTENSION in (manifest.get("extensions") or {})


def _unpublished_minimums(manifests: list[dict[str, Any]]) -> list[str]:
    """Researched manifests that publish no RAM or storage minimum; a curated one declares both."""

    return sorted(
        str(item["id"])
        for item in manifests
        if _is_researched(item)
        and (
            item["targets"]["minimum_resources"].get("ram_gib") is None
            or item["targets"]["minimum_resources"].get("storage_gib") is None
        )
    )


def _licence_reviews_pending(manifests: list[dict[str, Any]]) -> bool:
    """True when every licence shortfall is a review that has not happened yet.

    A failed review, a restricted class or a blocked licence is a real failure; a pending
    review or an unknown availability class is the honest state of a researched manifest
    nobody has reviewed, which the compare-only rule treats as pending (ADR-0018).
    """

    shortfall = False
    for item in manifests:
        licensing = item["licensing"]
        if item["availability_class"] not in {
            "osi_open_source_software",
            "osi_open_source_ai",
            "unknown",
        }:
            return False
        if licensing["transitive_review"] not in {"passed", "pending"}:
            return False
        for domain in ("software", "model", "data"):
            if licensing[domain]["review_status"] not in {"passed", "pending", "not_applicable"}:
                return False
            if licensing[domain]["classification"] in {
                "restricted",
                "source_available",
                "proprietary",
            }:
                return False
            if licensing[domain]["review_status"] == "pending":
                shortfall = True
        if licensing["transitive_review"] == "pending" or item["availability_class"] == "unknown":
            shortfall = True
        if shortfall and not _is_researched(item):
            # Only a researched manifest may stand on a pending review; a curated one
            # passes the curated rules or is ineligible.
            return False
    return shortfall


def classify_comparison(
    constraints: list[dict[str, Any]], manifests: list[dict[str, Any]]
) -> dict[str, Any]:
    """The compare-only rule's typed classification of a researched candidate (ADR-0018).

    A candidate whose hard-constraint results are each a pass, a pending review or an
    unpublished value is *comparable*: `_apply_pareto` includes it. It stays `infeasible`
    and `select` refuses it. Only a candidate that holds a researched component is ever
    classified; the classification is written to the candidate, never parsed from a reason.
    """

    pending: list[str] = []
    unknown: list[str] = []
    failed: list[str] = []
    researched = any(_is_researched(item) for item in manifests)
    for constraint in constraints:
        result = str(constraint["result"])
        identifier = str(constraint["id"])
        if result in {"pass", "not_applicable"}:
            continue
        if result == "unknown":
            unknown.append(identifier)
        elif (
            identifier == "constraint.licence"
            and researched
            and _licence_reviews_pending(manifests)
        ):
            pending.append(identifier)
        else:
            failed.append(identifier)
    return {
        "rule": COMPARISON_RULE_VERSION,
        "comparable": researched and not failed,
        "pending_review": sorted(pending),
        "unknown_value": sorted(unknown),
        "failed": sorted(failed),
        "uncompared_objectives": [],
    }


def _target_requirements(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    operating_systems = set(manifests[0]["targets"]["operating_systems"])
    cpu_architectures = set(manifests[0]["targets"]["cpu_architectures"])
    for manifest in manifests[1:]:
        operating_systems.intersection_update(manifest["targets"]["operating_systems"])
        cpu_architectures.intersection_update(manifest["targets"]["cpu_architectures"])
    return {
        "operating_systems": sorted(operating_systems),
        "cpu_architectures": sorted(cpu_architectures),
        "accelerators": sorted(
            {value for item in manifests for value in item["targets"]["accelerators"]}
        ),
        "drivers": sorted({value for item in manifests for value in item["targets"]["drivers"]}),
        "minimum_resources": _minimum_resources(manifests),
    }


def _minimum_resources(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    unpublished = _unpublished_minimums(manifests)
    if unpublished:
        return {
            "ram_gib": None,
            "storage_gib": None,
            "unknown_reason": f"Minimum resources are not published for {', '.join(unpublished)}.",
        }
    return {
        "ram_gib": max(
            float(item["targets"]["minimum_resources"].get("ram_gib", 0)) for item in manifests
        ),
        "storage_gib": sum(
            float(item["targets"]["minimum_resources"].get("storage_gib", 0)) for item in manifests
        ),
    }


def _topology(
    pattern: dict[str, Any],
    components: list[tuple[dict[str, Any], Artifact, dict[str, Any]]],
) -> dict[str, Any]:
    component_by_role = {
        str(requirement["role_id"]): artifact for requirement, artifact, _manifest in components
    }
    return {
        "nodes": [
            {
                "id": f"node.{str(role['id']).removeprefix('role.')}",
                "role": role["role"],
                "component_ref": (
                    f"{component_by_role[str(role['id'])].id}@{component_by_role[str(role['id'])].version}"
                ),
                "data_classifications": role["data_classifications"],
            }
            for role in pattern["roles"]
        ],
        "edges": [
            {
                **edge,
                "from": f"node.{str(edge['from']).removeprefix('role.')}",
                "to": f"node.{str(edge['to']).removeprefix('role.')}",
            }
            for edge in pattern["edges"]
        ],
        "systems_of_record": ["Content-digested public fixture corpus"],
        "trust_boundaries": ["Untrusted public content enters the bounded local index."],
    }


def _objectives(
    components: list[tuple[dict[str, Any], Artifact, dict[str, Any]]],
) -> list[dict[str, Any]]:
    manifests = [manifest for _r, _a, manifest in components]
    values = [
        manifest["extensions"].get("oak.community/objectives") or {} for manifest in manifests
    ]
    definitions = (
        ("monthly_cost", "minimize", "monthly_cost_usd", sum, "USD/month", 0.2, 0.10, "cost"),
        ("latency_p95", "minimize", "latency_p95_ms", max, "milliseconds", 0.2, 0.25, "latency"),
        (
            "quality",
            "maximize",
            "quality_score",
            max,
            "normalized_fixture_score",
            0.3,
            0.05,
            "quality",
        ),
        (
            "operability",
            "maximize",
            "operability_score",
            min,
            "normalized_fixture_score",
            0.2,
            0.08,
            "operability",
        ),
        ("energy", "minimize", "energy_wh", sum, "Wh/request", 0.1, 0.30, "energy"),
    )
    objectives: list[dict[str, Any]] = []
    for name, direction, key, aggregate, unit, weight, uncertainty, short in definitions:
        estimator = f"fixture-{short}-1.0.0"
        published: list[float] = []
        unpublished: list[str] = []
        for manifest, item in zip(manifests, values, strict=True):
            raw = item.get(key)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                published.append(float(raw))
            else:
                unpublished.append(str(manifest["id"]))
        if unpublished:
            # K4: never a fallback number. The aggregate keeps its fixture estimator, since
            # every fixture input stays a synthetic estimate, and says who published nothing.
            objectives.append(
                {
                    "name": name,
                    "direction": direction,
                    "value": None,
                    "lower": None,
                    "upper": None,
                    "unit": unit,
                    "weight": weight,
                    "confidence": 0.0,
                    "estimator_ref": estimator,
                    "unknown_reason": (
                        f"No {name.replace('_', ' ')} figure is published for "
                        f"{', '.join(sorted(unpublished))}."
                    ),
                }
            )
            continue
        value = aggregate(published)
        if direction == "maximize":
            lower, upper = max(0.0, value - uncertainty), min(1.0, value + uncertainty)
        else:
            lower, upper = value * (1.0 - uncertainty), value * (1.0 + uncertainty)
        objectives.append(
            {
                "name": name,
                "direction": direction,
                "value": round(value, 6),
                "lower": round(lower, 6),
                "upper": round(upper, 6),
                "unit": unit,
                "weight": weight,
                "confidence": 0.7,
                "estimator_ref": estimator,
            }
        )
    return objectives


def _apply_pareto(documents: list[dict[str, Any]]) -> None:
    compared = [
        document
        for document in documents
        if document["status"] == "feasible" or _is_comparable(document)
    ]
    for document in documents:
        if document not in compared:
            document["pareto"]["sensitivity_summary"] = (
                "Excluded because at least one hard constraint failed or remained unknown."
            )
            continue
        dominated_by = sorted(
            str(other["id"])
            for other in compared
            if other is not document and _dominates(other, document)
        )
        uncompared = sorted(
            str(objective["name"])
            for objective in document["objectives"]
            if objective.get("value") is None
        )
        if dominated_by:
            summary = f"Dominated under every declared objective by {', '.join(dominated_by)}."
        elif uncompared:
            summary = (
                "Not dominated, and not compared on "
                f"{', '.join(name.replace('_', ' ') for name in uncompared)}, whose values "
                "are unknown; an unknown never dominates and is never dominated."
            )
        else:
            summary = (
                "Frontier membership is stable; preference changes choose between simplicity, "
                "quality, operability, cost and energy."
            )
        document["pareto"] = {
            "frontier_member": not dominated_by,
            "dominated_by": dominated_by,
            "preference_weights_ref": "community-fixture-weights-1.0.0",
            "sensitivity_summary": summary,
        }
        comparison = document["extensions"].get(COMPARISON_EXTENSION)
        if isinstance(comparison, dict):
            comparison["uncompared_objectives"] = uncompared


def _is_comparable(document: dict[str, Any]) -> bool:
    comparison = document["extensions"].get(COMPARISON_EXTENSION)
    return isinstance(comparison, dict) and comparison.get("comparable") is True


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    right_by_name = {str(item["name"]): item for item in right["objectives"]}
    weakly_better = True
    strictly_better = False
    for objective in left["objectives"]:
        other = right_by_name[str(objective["name"])]
        if objective.get("value") is None or other.get("value") is None:
            # K4: an unknown never dominates and is never dominated.
            return False
        if objective["direction"] == "minimize":
            weakly_better &= float(objective["value"]) <= float(other["value"])
            strictly_better |= float(objective["value"]) < float(other["value"])
        else:
            weakly_better &= float(objective["value"]) >= float(other["value"])
            strictly_better |= float(objective["value"]) > float(other["value"])
    return weakly_better and strictly_better


def _risks(variant: str, feasible: bool, *, researched: bool = False) -> list[str]:
    if researched:
        return [
            "This design is researched: its licence reviews are pending and the figures its "
            "sources do not publish are unknown, so it is compared but cannot be selected."
        ]
    if not feasible:
        return ["The candidate is blocked and cannot be selected or compiled."]
    if variant == "simpler_baseline":
        return ["Recall may be lower for synonym or multi-passage questions."]
    if variant == "balanced_enterprise":
        return ["Generated wording requires citation verification and human review."]
    return ["Fixture estimates require observed calibration before any deployment decision."]


def _estimator_metadata() -> dict[str, Any]:
    return {
        "version": "community-fixture-estimators-1.0.0",
        "calibration": "Synthetic deterministic values; not calibrated for production use.",
        "evidence_population": "Public manual QA fixture on a declared x86_64 target.",
        "checked_at": "2026-08-16T12:00:00Z",
    }


def _explanation(document: dict[str, Any], all_documents: list[dict[str, Any]]) -> dict[str, Any]:
    satisfied = [
        {
            "constraint_id": item["id"],
            "reason": item["reason"],
            "requirement_ids": item.get("requirement_ids", []),
        }
        for item in document["hard_constraints"]
        if item["result"] == "pass"
    ]
    uncertainties = [
        {"constraint_id": item["id"], "reason": item["reason"]}
        for item in document["hard_constraints"]
        if item["result"] == "unknown"
    ]
    alternatives = [
        {
            "candidate_id": other["id"],
            "summary": (
                "infeasible under a hard constraint"
                if other["status"] == "infeasible"
                else "retained as a visible Pareto alternative"
            ),
        }
        for other in sorted(all_documents, key=lambda item: str(item["id"]))
        if other is not document
    ]
    return {
        "satisfied_requirements": satisfied,
        "uncertainties": uncertainties,
        "alternatives": alternatives,
        "method": "Deterministic rule and evidence summary; no private model reasoning.",
    }
