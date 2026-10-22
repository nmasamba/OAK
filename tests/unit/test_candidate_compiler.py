# SPDX-License-Identifier: Apache-2.0
"""OAK-S2-001 through OAK-S2-006 deterministic compiler tests."""

import copy
import json
from pathlib import Path

import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.compiler import (
    compile_catalogue,
    create_evaluation_contract,
    evaluate_candidate,
    generate_candidates,
)
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import ArtifactReference, OAKError
from oak.ports import CatalogueDocuments

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = "2026-08-17T10:00:00Z"


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _documents() -> CatalogueDocuments:
    return LocalCatalogue(ROOT / "catalogue", _registry()).load()


def _intent() -> dict[str, object]:
    document = load_yaml_document(
        (ROOT / "examples/example-intent.yaml").read_text(encoding="utf-8")
    )
    document["spec"]["hardware"] = {
        "cpu_architectures": ["x86_64"],
        "ram_gib": 32,
        "storage_gib": 100,
    }
    document["spec"]["deployment_environment"] = {
        "modes": ["local"],
        "network_constraints": ["isolated-no-egress-after-setup"],
    }
    document["spec"]["data"] = {"classifications": ["public"]}
    return document


def _reference(identifier: str, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        id=identifier,
        version="0.1.0",
        digest="sha256:" + "a" * 64,
        media_type=media_type,
    )


def _candidate_documents(
    documents: CatalogueDocuments, intent: dict[str, object] | None = None
) -> list[dict[str, object]]:
    registry = _registry()
    intent = intent if intent is not None else _intent()
    catalogue = compile_catalogue(
        documents.manifests, documents.patterns, registry, created_at=FIXED_TIME
    )
    contract = create_evaluation_contract(intent, registry)
    artifacts = generate_candidates(
        intent,
        _reference("intent.public-manual-qa", "application/vnd.oak.system-intent+json"),
        contract.reference,
        catalogue,
        registry,
        generated_at=FIXED_TIME,
    )
    return [json.loads(artifact.content) for artifact in artifacts]


def test_catalogue_snapshot_and_candidates_ignore_input_order() -> None:
    documents = _documents()
    reversed_documents = CatalogueDocuments(
        manifests=tuple(reversed(documents.manifests)),
        patterns=tuple(reversed(documents.patterns)),
    )

    first_catalogue = compile_catalogue(
        documents.manifests, documents.patterns, _registry(), created_at=FIXED_TIME
    )
    second_catalogue = compile_catalogue(
        reversed_documents.manifests,
        reversed_documents.patterns,
        _registry(),
        created_at=FIXED_TIME,
    )
    first_candidates = _candidate_documents(documents)
    second_candidates = _candidate_documents(reversed_documents)

    assert first_catalogue.snapshot.digest == second_catalogue.snapshot.digest
    assert first_candidates == second_candidates


def test_candidate_set_includes_baseline_variants_and_excludes_unknown_from_frontier() -> None:
    candidates = _candidate_documents(_documents())
    by_id = {str(candidate["id"]): candidate for candidate in candidates}

    assert set(by_id) == {"candidate-00", "candidate-01", "candidate-03", "candidate-04"}
    assert by_id["candidate-00"]["extensions"]["oak.community/pattern_variant"] == (
        "simpler_baseline"
    )
    assert by_id["candidate-03"]["status"] == "feasible"
    assert by_id["candidate-03"]["pareto"]["frontier_member"] is True
    assert {item["name"] for item in by_id["candidate-03"]["objectives"]} == {
        "monthly_cost",
        "latency_p95",
        "quality",
        "operability",
        "energy",
    }
    assert all(
        item["lower"] is not None and item["upper"] is not None and item["estimator_ref"]
        for item in by_id["candidate-03"]["objectives"]
    )
    assert (
        by_id["candidate-03"]["extensions"]["oak.community/estimator_metadata"]["version"]
        == "community-fixture-estimators-1.0.0"
    )
    assert by_id["candidate-04"]["status"] == "infeasible"
    assert by_id["candidate-04"]["pareto"]["frontier_member"] is False
    hardware = next(
        item
        for item in by_id["candidate-04"]["hard_constraints"]
        if item["id"] == "constraint.hardware"
    )
    assert hardware["result"] == "unknown"


def test_ineligible_manifest_cannot_produce_a_feasible_candidate() -> None:
    documents = _documents()
    manifests = [copy.deepcopy(item) for item in documents.manifests]
    lexical = next(item for item in manifests if item["id"] == "component.fixture-lexical-search")
    lexical["status"] = "revoked"
    poisoned = CatalogueDocuments(manifests=tuple(manifests), patterns=documents.patterns)

    catalogue = compile_catalogue(
        poisoned.manifests, poisoned.patterns, _registry(), created_at=FIXED_TIME
    )
    assert catalogue.eligibility["component.fixture-lexical-search"] == (
        False,
        ("OAK-CAT-STATUS-NOT-ELIGIBLE",),
    )
    baseline = _candidate_documents(poisoned)[0]
    assert baseline["status"] == "infeasible"
    assert baseline["pareto"]["frontier_member"] is False


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (
            lambda item: item.update({"next_review_at": "2026-08-17T09:00:00Z"}),
            "OAK-CAT-EVIDENCE-STALE",
        ),
        (
            lambda item: item.update({"availability_class": "open_weight_restricted"}),
            "OAK-CAT-AVAILABILITY-BLOCKED",
        ),
    ),
)
def test_stale_or_restricted_manifest_is_not_eligible(mutation: object, reason: str) -> None:
    documents = _documents()
    manifests = [copy.deepcopy(item) for item in documents.manifests]
    lexical = next(item for item in manifests if item["id"] == "component.fixture-lexical-search")
    assert callable(mutation)
    mutation(lexical)

    catalogue = compile_catalogue(
        tuple(manifests), documents.patterns, _registry(), created_at=FIXED_TIME
    )

    eligible, reasons = catalogue.eligibility["component.fixture-lexical-search"]
    assert eligible is False
    assert reason in reasons


def test_incomplete_or_aliased_catalogue_document_is_rejected(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalogue"
    components = catalogue / "components"
    patterns = catalogue / "patterns"
    components.mkdir(parents=True)
    patterns.mkdir()
    (components / "invalid.yaml").write_text("id: component.incomplete\n", encoding="utf-8")
    (patterns / "aliased.yaml").write_text(
        "value: &payload poisoned\ncopy: *payload\n", encoding="utf-8"
    )

    with pytest.raises(OAKError) as captured:
        LocalCatalogue(catalogue, _registry()).load()

    assert captured.value.code == "OAK-CATALOGUE-INVALID"


def test_pattern_role_and_component_capability_are_validated() -> None:
    documents = _documents()
    patterns = [copy.deepcopy(item) for item in documents.patterns]
    balanced = next(item for item in patterns if item["id"] == "pattern.balanced")
    balanced["component_requirements"][0]["role_id"] = "role.unknown"

    with pytest.raises(OAKError) as captured:
        compile_catalogue(
            documents.manifests,
            tuple(patterns),
            _registry(),
            created_at=FIXED_TIME,
        )

    assert captured.value.code == "OAK-CATALOGUE-PATTERN"


def test_reference_evaluation_exposes_pass_fail_and_blocked_states() -> None:
    registry = _registry()
    intent = _intent()
    documents = _documents()
    catalogue = compile_catalogue(
        documents.manifests, documents.patterns, registry, created_at=FIXED_TIME
    )
    contract = create_evaluation_contract(intent, registry)
    contract_document = json.loads(contract.content)
    candidates = generate_candidates(
        intent,
        _reference("intent.public-manual-qa", "application/vnd.oak.system-intent+json"),
        contract.reference,
        catalogue,
        registry,
        generated_at=FIXED_TIME,
    )
    by_id = {artifact.id: artifact for artifact in candidates}

    passing = evaluate_candidate(
        json.loads(by_id["candidate-03"].content),
        by_id["candidate-03"].reference,
        contract_document,
        contract.reference,
        registry,
        executed_at=FIXED_TIME,
        executor="fixture",
    )
    stricter = copy.deepcopy(contract_document)
    stricter["metrics"][0]["threshold"] = 1.0
    failing = evaluate_candidate(
        json.loads(by_id["candidate-03"].content),
        by_id["candidate-03"].reference,
        stricter,
        contract.reference,
        registry,
        executed_at=FIXED_TIME,
        executor="fixture",
    )
    blocked = evaluate_candidate(
        json.loads(by_id["candidate-04"].content),
        by_id["candidate-04"].reference,
        contract_document,
        contract.reference,
        registry,
        executed_at=FIXED_TIME,
        executor="fixture",
    )

    assert json.loads(passing.content)["status"] == "pass"
    assert json.loads(failing.content)["status"] == "fail"
    assert json.loads(blocked.content)["status"] == "blocked"


# ----- Sprint 14, K4 and the compare-only rule (ADR-0018) -------------------------------


def _objective(name: str, direction: str, value: float | None) -> dict[str, object]:
    objective: dict[str, object] = {
        "name": name,
        "direction": direction,
        "value": value,
        "lower": value,
        "upper": value,
        "unit": "USD/month" if name == "monthly_cost" else "normalized_fixture_score",
        "weight": 0.2,
        "confidence": 0.7 if value is not None else 0.0,
        "estimator_ref": f"fixture-{name}-1.0.0",
    }
    if value is None:
        objective["unknown_reason"] = f"No {name} figure is published for component.research.x."
    return objective


def _synthetic_candidate(
    identifier: str,
    status: str,
    cost: float | None,
    quality: float | None,
    *,
    comparable: bool | None = None,
) -> dict[str, object]:
    extensions: dict[str, object] = {}
    if comparable is not None:
        extensions["oak.community/comparison"] = {
            "rule": "community-compare-only-1.0.0",
            "comparable": comparable,
            "pending_review": ["constraint.licence"],
            "unknown_value": ["constraint.hardware"],
            "failed": [],
            "uncompared_objectives": [],
        }
    return {
        "id": identifier,
        "status": status,
        "objectives": [
            _objective("monthly_cost", "minimize", cost),
            _objective("quality", "maximize", quality),
        ],
        "pareto": {
            "frontier_member": False,
            "dominated_by": [],
            "preference_weights_ref": "community-fixture-weights-1.0.0",
            "sensitivity_summary": "Not compared until feasibility is established.",
        },
        "extensions": extensions,
    }


def test_an_unknown_objective_never_dominates_and_is_never_dominated() -> None:
    from oak.compiler.candidates import _apply_pareto

    better = _synthetic_candidate("candidate-a", "feasible", 10.0, 0.9)
    worse = _synthetic_candidate("candidate-b", "feasible", 20.0, 0.8)
    # Cheaper than both and feasible, but its quality is unknown: it can neither dominate
    # nor be dominated, and the frontier says which objective it could not compare.
    partial = _synthetic_candidate("candidate-c", "feasible", 5.0, None)
    documents = [worse, partial, better]

    _apply_pareto(documents)

    assert worse["pareto"]["dominated_by"] == ["candidate-a"]
    assert better["pareto"] == {
        "frontier_member": True,
        "dominated_by": [],
        "preference_weights_ref": "community-fixture-weights-1.0.0",
        "sensitivity_summary": (
            "Frontier membership is stable; preference changes choose between simplicity, "
            "quality, operability, cost and energy."
        ),
    }
    assert partial["pareto"]["frontier_member"] is True
    assert partial["pareto"]["dominated_by"] == []
    assert "not compared on quality" in partial["pareto"]["sensitivity_summary"]
    assert (
        "unknown never dominates and is never dominated" in partial["pareto"]["sensitivity_summary"]
    )


def test_a_comparable_researched_design_joins_the_comparison_but_stays_infeasible() -> None:
    from oak.compiler.candidates import _apply_pareto

    curated = _synthetic_candidate("candidate-03", "feasible", 20.0, 0.8)
    # The compare-only rule: infeasible only through a pending review and an unknown value,
    # with both objectives published, so it can dominate a curated design on the numbers.
    researched = _synthetic_candidate("candidate-05", "infeasible", 10.0, 0.9, comparable=True)
    excluded = _synthetic_candidate("candidate-06", "infeasible", 1.0, 1.0, comparable=False)
    documents = [curated, researched, excluded]

    _apply_pareto(documents)

    assert researched["status"] == "infeasible"
    assert researched["pareto"]["frontier_member"] is True
    assert researched["pareto"]["dominated_by"] == []
    assert researched["extensions"]["oak.community/comparison"]["uncompared_objectives"] == []
    assert curated["pareto"]["dominated_by"] == ["candidate-05"]
    assert excluded["pareto"]["frontier_member"] is False
    assert excluded["pareto"]["sensitivity_summary"] == (
        "Excluded because at least one hard constraint failed or remained unknown."
    )
    assert "candidate-06" not in curated["pareto"]["dominated_by"]


def _researched(manifest: dict[str, object], **licence: str) -> dict[str, object]:
    document = copy.deepcopy(manifest)
    document["extensions"]["oak.community/research"] = {  # type: ignore[index]
        "source": "fixture",
        "source_id": "HuggingFaceTB/Fixturelm-4B",
        "tier": "trusted",
        "commit_id": "0123456789abcdef0123456789abcdef01234567",
        "digest_covers": "source listing",
    }
    licensing = document["licensing"]
    assert isinstance(licensing, dict)
    licensing["transitive_review"] = licence.get("transitive", "pending")
    licensing["model"]["review_status"] = licence.get("review", "pending")
    document["availability_class"] = licence.get("availability", "unknown")
    return document


def _constraint(identifier: str, result: str) -> dict[str, object]:
    return {"id": identifier, "kind": "hard", "expression": "x", "result": result, "reason": "r"}


def test_the_compare_only_rule_classifies_pending_reviews_and_unknowns_only() -> None:
    from oak.compiler.candidates import classify_comparison

    documents = _documents()
    model = next(
        item for item in documents.manifests if item["id"] == "component.fixture-local-model"
    )
    constraints = [
        _constraint("constraint.catalogue-eligibility", "pass"),
        _constraint("constraint.hardware", "unknown"),
        _constraint("constraint.licence", "fail"),
        _constraint("constraint.security", "pass"),
    ]

    pending = classify_comparison(constraints, [_researched(model)])
    assert pending == {
        "rule": "community-compare-only-1.0.0",
        "comparable": True,
        "pending_review": ["constraint.licence"],
        "unknown_value": ["constraint.hardware"],
        "failed": [],
        "uncompared_objectives": [],
    }

    failed_review = classify_comparison(constraints, [_researched(model, review="failed")])
    assert failed_review["comparable"] is False
    assert failed_review["failed"] == ["constraint.licence"]

    restricted = classify_comparison(
        constraints, [_researched(model, availability="open_weight_restricted")]
    )
    assert restricted["comparable"] is False

    real_failure = classify_comparison(
        [*constraints, _constraint("constraint.security", "fail")], [_researched(model)]
    )
    assert real_failure["failed"] == ["constraint.security"]
    assert real_failure["comparable"] is False

    curated_only = classify_comparison(constraints, [model])
    assert curated_only["comparable"] is False
    assert curated_only["pending_review"] == []
    assert curated_only["failed"] == ["constraint.licence"]


def test_every_curated_manifest_declares_its_minimums_so_the_curated_bytes_hold() -> None:
    for manifest in _documents().manifests:
        minimums = manifest["targets"]["minimum_resources"]
        assert isinstance(minimums.get("ram_gib"), (int, float)), manifest["id"]
        assert isinstance(minimums.get("storage_gib"), (int, float)), manifest["id"]
        objectives = manifest["extensions"]["oak.community/objectives"]
        assert set(objectives) == {
            "monthly_cost_usd",
            "latency_p95_ms",
            "quality_score",
            "operability_score",
            "energy_wh",
        }, manifest["id"]
        assert "oak.community/research" not in manifest["extensions"], manifest["id"]


def test_a_researched_component_with_nothing_published_yields_unknowns_never_zero() -> None:
    documents = _documents()
    manifests = [copy.deepcopy(item) for item in documents.manifests]
    model = next(item for item in manifests if item["id"] == "component.fixture-local-model")
    researched = _researched(model)
    researched["extensions"]["oak.community/objectives"] = {}  # type: ignore[index]
    researched["targets"]["minimum_resources"] = {}  # type: ignore[index]
    researched["targets"]["operating_systems"] = []  # type: ignore[index]
    researched["targets"]["cpu_architectures"] = []  # type: ignore[index]
    researched["deployment"]["modes"] = []  # type: ignore[index]
    manifests[manifests.index(model)] = researched
    poisoned = CatalogueDocuments(manifests=tuple(manifests), patterns=documents.patterns)

    by_id = {str(c["id"]): c for c in _candidate_documents(poisoned)}
    balanced = by_id["candidate-03"]

    assert balanced["status"] == "infeasible"
    constraints = {str(c["id"]): c for c in balanced["hard_constraints"]}
    assert constraints["constraint.hardware"]["result"] == "unknown"
    assert (
        "not published for component.fixture-local-model"
        in constraints["constraint.hardware"]["reason"]
    )
    assert constraints["constraint.compatibility"]["result"] == "unknown"
    assert constraints["constraint.deployment"]["result"] == "unknown"
    assert constraints["constraint.licence"]["result"] == "fail"
    assert (
        constraints["constraint.licence"]["reason"]
        == "A component licence or transitive review is pending."
    )
    requirements = balanced["extensions"]["oak.community/target_requirements"]
    assert requirements["minimum_resources"]["ram_gib"] is None
    assert requirements["minimum_resources"]["storage_gib"] is None
    assert "not published" in requirements["minimum_resources"]["unknown_reason"]
    for objective in balanced["objectives"]:
        assert objective["value"] is None and objective["lower"] is None
        assert objective["confidence"] == 0.0
        assert objective["estimator_ref"].startswith("fixture-")
        assert "component.fixture-local-model" in objective["unknown_reason"]
    # The designs that do not hold the researched component are exactly as before.
    reference = {str(c["id"]): c for c in _candidate_documents(documents)}
    for identifier in ("candidate-00", "candidate-01", "candidate-04"):
        assert by_id[identifier]["objectives"] == reference[identifier]["objectives"]
        assert by_id[identifier]["hard_constraints"] == reference[identifier]["hard_constraints"]


# ----- the closing review's fixes (OAK-S14-007) ---------------------------------------------


def _researched_pair() -> tuple[list[dict[str, object]], dict[str, object]]:
    """The fixture manifests with the local model researched, and that researched model."""

    documents = _documents()
    manifests = [copy.deepcopy(item) for item in documents.manifests]
    model = next(item for item in manifests if item["id"] == "component.fixture-local-model")
    researched = _researched(model)
    manifests[manifests.index(model)] = researched
    return manifests, researched


def test_a_weight_floor_above_the_declared_memory_fails_the_hardware_constraint() -> None:
    """U-9: the floor is a lower bound, so exceeding the declared memory is enough to fail;
    a floor within it says nothing and the constraint keeps its other answer."""

    from oak.compiler.candidates import _hardware_constraint

    manifests, researched = _researched_pair()
    research = researched["extensions"]["oak.community/research"]  # type: ignore[index]
    assert isinstance(research, dict)
    research["weight_floor_gib"] = 745.0
    hardware = {"cpu_architectures": ["x86_64"], "ram_gib": 32, "storage_gib": 100}
    failed = _hardware_constraint(hardware, manifests)
    assert failed["result"] == "fail"
    assert failed["reason"] == (
        "The estimated weight floor of 745 GiB for component.fixture-local-model exceeds the "
        "declared 32 GiB of memory."
    )
    research["weight_floor_gib"] = 2.0
    assert _hardware_constraint(hardware, manifests)["result"] != "fail"
    # With an accelerator declared, the accelerator's memory is the one compared (the
    # fixture GPU model is left out so its own accelerator requirement does not decide).
    plain = [item for item in manifests if item["id"] != "component.fixture-high-assurance-model"]
    research["weight_floor_gib"] = 40.0
    accelerated = {**hardware, "accelerators": ["cuda"], "vram_gib": 24}
    assert _hardware_constraint(accelerated, plain)["result"] == "fail"
    assert _hardware_constraint({**accelerated, "vram_gib": 48}, plain)["result"] != "fail"


def test_absent_evidence_is_unknown_for_a_researched_component_never_a_pass() -> None:
    """D-4: a researched manifest's empty external-call list and unknown air-gap suitability
    are "nobody published it", so security and data locality read unknown with the reason."""

    from oak.compiler.candidates import _locality_constraint, _security_constraint

    manifests, researched = _researched_pair()
    deployment = researched["deployment"]
    assert isinstance(deployment, dict)
    deployment["external_calls"] = []
    deployment["air_gap_suitability"] = "unknown"
    security = _security_constraint({}, manifests)
    assert security["result"] == "unknown"
    assert security["reason"] == (
        "Runtime external calls are not published for component.fixture-local-model."
    )
    locality = _locality_constraint({"classifications": ["public"]}, manifests)
    assert locality["result"] == "unknown"
    assert locality["reason"] == (
        "Air-gap suitability is not published for component.fixture-local-model."
    )
    curated = [item for item in manifests if item is not researched]
    assert _security_constraint({}, curated)["result"] == "pass"
    assert _locality_constraint({"classifications": ["public"]}, curated)["result"] == "pass"


def test_a_researched_design_that_is_not_comparable_never_says_it_is_compared() -> None:
    """D-5: the risk sentence reads the classification; an excluded design says so."""

    from oak.compiler.candidates import _risks

    compared = _risks("balanced_enterprise", False, researched=True, comparable=True)
    excluded = _risks("balanced_enterprise", False, researched=True, comparable=False)
    assert compared == [
        "This design is researched: its licence reviews are pending and the figures its "
        "sources do not publish are unknown, so it is compared but cannot be selected."
    ]
    assert excluded == [
        "This design is researched and a hard constraint failed, so it is not compared and "
        "cannot be selected."
    ]
    from oak.compiler.candidates import classify_comparison

    manifests, _researched_model = _researched_pair()
    constraints = [
        _constraint("constraint.licence", "fail"),
        _constraint("constraint.data-locality", "fail"),
    ]
    comparison = classify_comparison(constraints, manifests)
    assert comparison["comparable"] is False
    assert comparison["failed"] == ["constraint.data-locality"]
    assert comparison["pending_review"] == ["constraint.licence"]


def test_the_licence_pending_rule_ignores_the_order_of_a_designs_manifests() -> None:
    """D-6: a curated role before or after the researched one gives the same answer."""

    from oak.compiler.candidates import _licence_reviews_pending, classify_comparison

    manifests, _ = _researched_pair()
    forward, backward = manifests, list(reversed(manifests))
    assert _licence_reviews_pending(forward) is True
    assert _licence_reviews_pending(backward) is True
    constraints = [_constraint("constraint.licence", "fail")]
    assert classify_comparison(constraints, forward) == classify_comparison(constraints, backward)
