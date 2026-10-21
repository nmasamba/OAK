# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-004: the research run, the review and generation against the merged snapshot.

ADR-0018, OAK-FR-CAT-001 to 005, OAK-NFR-SEC-003. The service checks the state, the
version and the consent before any request; a refused or repeated request sends nothing; a
run writes the snapshot and the quarantined manifests, sets the case extension and appends
`research_completed`; a review is a recorded decision bound to the snapshot; generation
compiles the merged snapshot, adds at most two researched designs from `candidate-05`,
and gives the same bytes for the same snapshot and reviews in a fresh interpreter.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.models.research_fixture import FixtureResearchSource
from oak.adapters.models.research_sources import run_research
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    CandidatePlanningService,
    CommandContext,
    DesignCaseService,
    ResearchService,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import (
    COMPARISON_EXTENSION,
    RESEARCH_EXTENSION,
    RESEARCH_REVIEW_REFS,
    RESEARCH_SNAPSHOT_REF,
    OAKError,
    canonical_json_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/research/live"
NOW = "2026-10-20T12:00:00Z"
WORKSPACE = "workspace.public-manual-qa"
HARNESS = "research.item.github.fixture-forge.fixturelm-serve"
MODEL = "research.item.hub.HuggingFaceTB.Fixturelm-4B"
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")
pytestmark = pytest.mark.integration


def _context(key: str, version: str | None = None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


class _CountingSource:
    """The fixture source behind a counter, so a test can prove no request was made."""

    def __init__(self, directory: Path = FIXTURES) -> None:
        self.directory = directory
        self.fetches = 0

    def factory(self, occurred_at: str) -> tuple[Any, str, frozenset[str]]:
        source = FixtureResearchSource(self.directory, occurred_at=occurred_at)

        def fetch(request: Any, *, deadline_seconds: float | None = None) -> Any:
            self.fetches += 1
            return source.fetch(request, deadline_seconds=deadline_seconds)

        return fetch, "fixture", frozenset()


def _ready_case(tmp_path: Path) -> FileWorkspaceRepository:
    repository = FileWorkspaceRepository(tmp_path / WORKSPACE, REGISTRY)
    design = DesignCaseService(
        repository, LocalBriefIntake(), DeterministicBriefInterpreter(), REGISTRY
    )
    design.initialize(workspace_id=WORKSPACE, tenant_id="local", created_at=NOW)
    design.design(ROOT / "examples/briefs/public-manual-qa.yaml", _context("research-design-0001"))
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context("research-confirm-0001", "0.1.1"))
    return repository


def _service(repository: FileWorkspaceRepository, source: _CountingSource) -> ResearchService:
    return ResearchService(
        repository,
        REGISTRY,
        LocalCatalogue(ROOT / "catalogue", REGISTRY),
        ResearchVocabularyLoader(ROOT / "catalogue"),
        source_factory=source.factory,
        source_mode=lambda: ("fixture", frozenset()),
        runner=run_research,
    )


def _planning(repository: FileWorkspaceRepository) -> CandidatePlanningService:
    return CandidatePlanningService(
        repository,
        LocalCatalogue(ROOT / "catalogue", REGISTRY),
        LocalTargetProfile(REGISTRY),
        REGISTRY,
        research_vocabulary=ResearchVocabularyLoader(ROOT / "catalogue"),
    )


def _event_types(repository: FileWorkspaceRepository, count: int = 1) -> list[str]:
    """The last `count` audit events' types, read through their references."""

    from oak.domain import ArtifactReference

    entries = repository.manifest()["audit_events"][-count:]
    return [
        str(repository.read_json_artifact(ArtifactReference.from_document(entry))["event_type"])
        for entry in entries
    ]


def _consent(service: ResearchService) -> dict[str, Any]:
    plan = service.plan()
    return {"hosts": list(plan.hosts), "terms_digest": plan.terms_digest}


# ----- the plan and the run ----------------------------------------------------------------


def test_the_plan_is_a_read_that_names_the_hosts_and_the_terms(tmp_path: Path) -> None:
    source = _CountingSource()
    service = _service(_ready_case(tmp_path), source)
    plan = service.plan()

    assert (plan.case_version, plan.status, plan.allowed) == ("0.1.2", "ready_for_candidates", True)
    assert plan.source_mode == "fixture" and plan.hosts == ()
    assert plan.terms["sent"]["hub"]["pipeline_tags"] == ["text-generation"]
    assert plan.terms_digest.startswith("sha256:")
    assert source.fetches == 0


def test_a_consented_run_records_the_snapshot_the_manifests_and_the_event(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)

    result = service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))

    assert result.duplicate is False
    assert result.snapshot["summary"] == {"found": 2, "passed": 1, "needs_review": 1, "failed": 0}
    case = result.case
    assert (case["version"], case["status"]) == ("0.1.3", "ready_for_candidates")
    reference = case["extensions"][RESEARCH_SNAPSHOT_REF]
    assert reference["id"] == "research.public-manual-qa" and reference["version"] == "0.1.0"
    assert case["extensions"][RESEARCH_REVIEW_REFS] == []
    manifest = repository.manifest()
    kinds = {(entry["kind"], entry["id"]) for entry in manifest["artifact_index"]}
    assert ("research_snapshot", "research.public-manual-qa") in kinds
    assert (
        "component_manifest",
        "component.research.hub.huggingfacetb.fixturelm-4b.run-1",
    ) in kinds
    assert (
        "component_manifest",
        "component.research.github.fixture-forge.fixturelm-serve.run-1",
    ) in kinds
    assert _event_types(repository) == ["research_completed"]
    stored = repository.read_json_artifact(
        __import__("oak.domain", fromlist=["ArtifactReference"]).ArtifactReference.from_document(
            {**reference, "media_type": "application/vnd.oak.research-snapshot+json"}
        )
    )
    assert stored == result.snapshot
    assert source.fetches == 12

    retried = service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))
    assert retried.duplicate is True and retried.case["version"] == "0.1.3"
    assert source.fetches == 12  # an idempotent retry sends nothing


@pytest.mark.parametrize(
    ("consent", "version", "code"),
    [
        ({"hosts": ["evil.invalid"], "terms_digest": "same"}, "0.1.2", "OAK-RESEARCH-CONSENT"),
        ({"hosts": [], "terms_digest": "sha256:" + "0" * 64}, "0.1.2", "OAK-RESEARCH-CONSENT"),
        ({"hosts": [], "terms_digest": "same"}, "0.1.1", "OAK-EXPECTED-VERSION"),
    ],
)
def test_a_wrong_consent_or_a_stale_version_sends_nothing(
    tmp_path: Path, consent: dict[str, Any], version: str, code: str
) -> None:
    source = _CountingSource()
    service = _service(_ready_case(tmp_path), source)
    if consent["terms_digest"] == "same":
        consent["terms_digest"] = service.plan().terms_digest

    with pytest.raises(OAKError) as refused:
        service.run(_context("research-run-wrong-0001", version), consent=consent)
    assert refused.value.code == code
    assert source.fetches == 0


def test_research_is_refused_once_candidates_exist(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    _planning(repository).candidates(_context("research-generate-0001", "0.1.2"))
    service = _service(repository, source)

    assert service.plan().allowed is False
    with pytest.raises(OAKError) as refused:
        service.run(_context("research-run-late-00001", "0.1.3"), consent=_consent(service))
    assert refused.value.code == "OAK-RESEARCH-STATE"
    assert source.fetches == 0


def test_a_second_run_replaces_the_reference_and_keeps_the_first_snapshot(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    first = service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))
    second = service.run(_context("research-run-00000002", "0.1.3"), consent=_consent(service))

    assert second.case["extensions"][RESEARCH_SNAPSHOT_REF]["version"] == "0.2.0"
    assert first.case["extensions"][RESEARCH_SNAPSHOT_REF]["version"] == "0.1.0"
    versions = sorted(
        entry["version"]
        for entry in repository.manifest()["artifact_index"]
        if entry["kind"] == "research_snapshot"
    )
    assert versions == ["0.1.0", "0.2.0"]
    assert _event_types(repository, 2) == ["research_completed", "research_completed"]


# ----- the review ----------------------------------------------------------------------------


def test_a_review_is_recorded_bound_to_the_snapshot_and_the_item(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    run = service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))

    reviewed = service.review(
        _context("research-review-000001", "0.1.3"),
        item_id=HARNESS,
        decision="accept",
        rationale="Read the repository by hand; the notes name the family.",
    )
    assert reviewed.duplicate is False
    assert reviewed.case["version"] == "0.1.4"
    review = reviewed.review
    assert (
        review["snapshot_ref"]["digest"] == run.case["extensions"][RESEARCH_SNAPSHOT_REF]["digest"]
    )
    harness = next(item for item in run.snapshot["items"] if item["id"] == HARNESS)
    assert review["item_response_digest"] == harness["response_digest"]
    assert review["decision"] == "accept" and review["actor"] == "local-user"
    assert reviewed.case["extensions"][RESEARCH_REVIEW_REFS][0]["id"] == review["id"]
    assert _event_types(repository) == ["research_item_reviewed"]
    REGISTRY.validate("research-review.schema.json", review)

    retried = service.review(
        _context("research-review-000001", "0.1.3"),
        item_id=HARNESS,
        decision="accept",
        rationale="Read the repository by hand; the notes name the family.",
    )
    assert retried.duplicate is True


@pytest.mark.parametrize(
    ("item_id", "decision", "rationale", "code"),
    [
        (MODEL, "accept", "fine", "OAK-RESEARCH-ITEM-STATE"),
        ("research.item.nobody", "accept", "fine", "OAK-RESEARCH-ITEM-UNKNOWN"),
        (HARNESS, "approve", "fine", "OAK-RESEARCH-REVIEW-DECISION"),
        (HARNESS, "accept", "   ", "OAK-RESEARCH-REVIEW-RATIONALE"),
        (HARNESS, "accept", "x" * 4001, "OAK-RESEARCH-REVIEW-SIZE"),
    ],
)
def test_a_review_outside_its_rules_is_refused(
    tmp_path: Path, item_id: str, decision: str, rationale: str, code: str
) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))

    with pytest.raises(OAKError) as refused:
        service.review(
            _context("research-review-bad-001", "0.1.3"),
            item_id=item_id,
            decision=decision,
            rationale=rationale,
        )
    assert refused.value.code == code
    assert _event_types(repository) == ["research_completed"]


def test_a_review_needs_a_snapshot_and_the_right_status(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    with pytest.raises(OAKError) as missing:
        service.review(
            _context("research-review-000009", "0.1.2"),
            item_id=HARNESS,
            decision="reject",
            rationale="no",
        )
    assert missing.value.code == "OAK-RESEARCH-MISSING"

    service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))
    _planning(repository).candidates(_context("research-generate-0001", "0.1.3"))
    with pytest.raises(OAKError) as late:
        service.review(
            _context("research-review-000010", "0.1.4"),
            item_id=HARNESS,
            decision="reject",
            rationale="no",
        )
    assert late.value.code == "OAK-RESEARCH-REVIEW-STATE"


# ----- generation against the merged snapshot ---------------------------------------------


def _generate(tmp_path: Path, *, accept: bool) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))
    version = "0.1.3"
    if accept:
        service.review(
            _context("research-review-000001", version),
            item_id=HARNESS,
            decision="accept",
            rationale="Reviewed by hand.",
        )
        version = "0.1.4"
    result = _planning(repository).candidates(_context("research-generate-0001", version))
    return {str(c["id"]): c for c in result.candidates}, result.catalogue_snapshot


def test_generating_without_a_review_adds_the_model_alone_from_candidate_05(tmp_path: Path) -> None:
    by_id, snapshot = _generate(tmp_path, accept=False)

    assert set(by_id) == {
        "candidate-00",
        "candidate-01",
        "candidate-03",
        "candidate-04",
        "candidate-05",
        "candidate-06",
    }
    assert (
        snapshot["id"] == "catalogue.research.public-manual-qa" and snapshot["version"] == "0.1.0"
    )
    assert (
        snapshot["extensions"]["oak.community/research"]["rule_set"]
        == "community-research-gates-1.0.0"
    )
    assert snapshot["extensions"]["oak.community/research"]["researched_manifest_ids"] == [
        "component.research.hub.huggingfacetb.fixturelm-4b.run-1"
    ]
    entry = next(
        e
        for e in snapshot["entries"]
        if e["manifest_ref"]["id"].startswith("component.research.hub")
    )
    assert entry["eligible"] is True
    assert "OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED" in entry["reasons"]  # kept as a review item
    for identifier, variant in (
        ("candidate-05", "balanced_enterprise"),
        ("candidate-06", "high_assurance_sovereign"),
    ):
        design = by_id[identifier]
        assert design["status"] == "infeasible"
        assert design["extensions"]["oak.community/pattern_variant"] == variant
        research = design["extensions"][RESEARCH_EXTENSION]
        assert research["model_source_id"] == "HuggingFaceTB/Fixturelm-4B"
        assert research["harness_item_id"] is None
        assert research["label_suffix"] == "new"
        comparison = design["extensions"][COMPARISON_EXTENSION]
        assert comparison["comparable"] is True
        assert comparison["pending_review"] == ["constraint.licence"]
        assert set(comparison["unknown_value"]) >= {
            "constraint.hardware",
            "constraint.compatibility",
            "constraint.deployment",
        }
        assert comparison["failed"] == []
        assert design["pareto"]["frontier_member"] is True
        assert sorted(comparison["uncompared_objectives"]) == [
            "energy",
            "latency_p95",
            "monthly_cost",
            "operability",
            "quality",
        ]
        roles = [node["role"] for node in design["topology"]["nodes"]]
        assert not any("Serving" in role for role in roles)
        assert all(objective["value"] is None for objective in design["objectives"])
        assert any("researched" in risk for risk in design["risks"])
    curated = by_id["candidate-03"]
    assert curated["status"] == "feasible"
    assert RESEARCH_EXTENSION not in curated["extensions"]
    assert curated["extensions"]["oak.community/catalogue_snapshot_ref"]["id"] == snapshot["id"]


def test_generating_after_an_accept_puts_the_harness_in_the_serving_role(tmp_path: Path) -> None:
    by_id, snapshot = _generate(tmp_path, accept=True)

    assert set(snapshot["extensions"]["oak.community/research"]["researched_manifest_ids"]) == {
        "component.research.hub.huggingfacetb.fixturelm-4b.run-1",
        "component.research.github.fixture-forge.fixturelm-serve.run-1",
    }
    design = by_id["candidate-05"]
    research = design["extensions"][RESEARCH_EXTENSION]
    assert research["harness_item_id"] == HARNESS
    assert research["harness_source_id"] == "fixture-forge/fixturelm-serve"
    assert research["pairing_claim_classes"] == [
        "claimed_by_release_notes",
        "published_by_source",
        "published_release",
        "served_by_live_route",
    ]
    nodes = {node["id"]: node for node in design["topology"]["nodes"]}
    assert "node.serving" in nodes
    assert nodes["node.serving"]["component_ref"].startswith(
        "component.research.github.fixture-forge.fixturelm-serve.run-1@"
    )
    assert any(
        edge["from"] == "node.serving" and edge["to"] == "node.generation"
        for edge in design["topology"]["edges"]
    )
    manifests = {component["manifest_id"] for component in design["components"]}
    assert "component.research.github.fixture-forge.fixturelm-serve.run-1" in manifests
    assert design["status"] == "infeasible"
    assert design["extensions"][COMPARISON_EXTENSION]["comparable"] is True


def test_the_same_snapshot_and_reviews_give_the_same_candidate_bytes_in_a_fresh_interpreter(
    tmp_path: Path,
) -> None:
    by_id, _ = _generate(tmp_path / "here", accept=True)
    digests = {
        identifier: canonical_json_bytes(candidate) for identifier, candidate in by_id.items()
    }
    program = "\n".join(
        (
            "import json, sys, pathlib, hashlib",
            f"sys.path.insert(0, {str(ROOT)!r})",
            "from tests.integration.test_research_service import _generate",
            "from oak.domain import canonical_json_bytes",
            f"by_id, _ = _generate(pathlib.Path({str(tmp_path / 'there')!r}), accept=True)",
            "digests = {k: hashlib.sha256(canonical_json_bytes(v)).hexdigest()"
            " for k, v in by_id.items()}",
            "print(json.dumps(digests))",
        )
    )
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    fresh = json.loads(completed.stdout.splitlines()[-1])
    import hashlib

    assert fresh == {k: hashlib.sha256(v).hexdigest() for k, v in digests.items()}


def test_a_rejected_harness_never_enters_a_design(tmp_path: Path) -> None:
    source = _CountingSource()
    repository = _ready_case(tmp_path)
    service = _service(repository, source)
    service.run(_context("research-run-00000001", "0.1.2"), consent=_consent(service))
    service.review(
        _context("research-review-000001", "0.1.3"),
        item_id=HARNESS,
        decision="reject",
        rationale="No.",
    )
    result = _planning(repository).candidates(_context("research-generate-0001", "0.1.4"))
    by_id = {str(c["id"]): c for c in result.candidates}
    assert by_id["candidate-05"]["extensions"][RESEARCH_EXTENSION]["harness_item_id"] is None
    assert (
        "component.research.github.fixture-forge.fixturelm-serve.run-1"
        not in result.catalogue_snapshot["extensions"]["oak.community/research"][
            "researched_manifest_ids"
        ]
    )


def test_an_unresearched_case_still_gives_four_curated_candidates(tmp_path: Path) -> None:
    repository = _ready_case(tmp_path)
    result = _planning(repository).candidates(_context("research-generate-0001", "0.1.2"))
    assert [c["id"] for c in result.candidates] == [
        "candidate-00",
        "candidate-01",
        "candidate-03",
        "candidate-04",
    ]
    assert result.catalogue_snapshot["id"] == "catalogue.community-fixture"
    assert all(RESEARCH_EXTENSION not in c["extensions"] for c in result.candidates)
