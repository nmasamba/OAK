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


def _candidate_documents(documents: CatalogueDocuments) -> list[dict[str, object]]:
    registry = _registry()
    intent = _intent()
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
