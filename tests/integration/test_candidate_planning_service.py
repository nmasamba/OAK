# SPDX-License-Identifier: Apache-2.0
"""OAK-S2-001 through OAK-S2-010 shared application integration tests."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import CandidatePlanningService, CommandContext, DesignCaseService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError

ROOT = Path(__file__).resolve().parents[2]
BASE_TIME = "2026-08-17T10:00:00Z"


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _context(key: str, expected: str | None, minute: int) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=expected,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=f"2026-08-17T10:{minute:02d}:00Z",
    )


def _services(workspace: Path) -> tuple[DesignCaseService, CandidatePlanningService]:
    registry = _registry()
    repository = FileWorkspaceRepository(workspace, registry)
    return (
        DesignCaseService(
            repository,
            LocalBriefIntake(),
            DeterministicBriefInterpreter(),
            registry,
        ),
        CandidatePlanningService(
            repository,
            LocalCatalogue(ROOT / "catalogue", registry),
            LocalTargetProfile(registry),
            registry,
        ),
    )


def _ready_services(tmp_path: Path) -> tuple[DesignCaseService, CandidatePlanningService, Path]:
    workspace = tmp_path / "workspace"
    design, planning = _services(workspace)
    design.initialize(
        workspace_id="workspace.public-manual-qa", tenant_id="local", created_at=BASE_TIME
    )
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context("design-candidate-planning-0001", None, 0),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    confirmed = design.confirm(answers, _context("confirm-candidate-planning-0001", "0.1.0", 1))
    assert confirmed.case["status"] == "ready_for_candidates"
    return design, planning, workspace


def test_full_candidate_to_plan_lineage_is_atomic_idempotent_and_non_executing(
    tmp_path: Path,
) -> None:
    _design, planning, workspace = _ready_services(tmp_path)
    candidate_context = _context("candidates-planning-flow-0001", "0.1.1", 2)

    candidates = planning.candidates(candidate_context)
    retry = planning.candidates(candidate_context)
    evaluation_context = _context("evaluate-planning-flow-0001", "0.1.2", 3)
    evaluation = planning.evaluate("candidate-03", evaluation_context)
    evaluation_retry = planning.evaluate("candidate-03", evaluation_context)
    before_re_evaluation = FileWorkspaceRepository(workspace, _registry()).manifest()
    with pytest.raises(OAKError) as re_evaluation:
        planning.evaluate(
            "candidate-03",
            _context("evaluate-planning-flow-again-0001", "0.1.3", 4),
        )
    assert re_evaluation.value.code == "OAK-EVALUATION-EXISTS"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before_re_evaluation
    selection_context = _context("select-planning-flow-0001", "0.1.3", 4)
    selection = planning.select(
        "candidate-03",
        "Select the balanced fixture to compare bounded generation with the retained baseline.",
        selection_context,
    )
    selection_retry = planning.select(
        "candidate-03",
        "Select the balanced fixture to compare bounded generation with the retained baseline.",
        selection_context,
    )
    assurance_context = _context("assure-planning-flow-0001", "0.1.4", 5)
    assurance = planning.assure("candidate-03", assurance_context)
    assurance_retry = planning.assure("candidate-03", assurance_context)
    target = load_yaml_document(
        (ROOT / "examples/targets/local-fixture.yaml").read_text(encoding="utf-8")
    )
    wrong_tenant_target = copy.deepcopy(target)
    wrong_tenant_target["tenant_id"] = "different-tenant"
    wrong_tenant_path = tmp_path / "wrong-tenant-target.yaml"
    wrong_tenant_path.write_text(yaml.safe_dump(wrong_tenant_target), encoding="utf-8")
    before_wrong_tenant = FileWorkspaceRepository(workspace, _registry()).manifest()
    with pytest.raises(OAKError) as wrong_tenant:
        planning.plan(
            "candidate-03",
            wrong_tenant_path,
            _context("plan-wrong-tenant-flow-0001", "0.1.5", 6),
        )
    assert wrong_tenant.value.code == "OAK-TARGET-TENANT"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before_wrong_tenant
    restricted_target = copy.deepcopy(target)
    restricted_target["permissions"]["allowed_operations"] = [
        "inventory",
        "validate",
        "render",
        "plan",
    ]
    restricted_target_path = tmp_path / "restricted-target.yaml"
    restricted_target_path.write_text(yaml.safe_dump(restricted_target), encoding="utf-8")
    with pytest.raises(OAKError) as restricted:
        planning.plan(
            "candidate-03",
            restricted_target_path,
            _context("plan-restricted-target-flow-0001", "0.1.5", 6),
        )
    assert restricted.value.code == "OAK-TARGET-CAPABILITY"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before_wrong_tenant
    undersized_target = copy.deepcopy(target)
    undersized_target["capacity"]["ram_gib"] = 1
    undersized_target_path = tmp_path / "undersized-target.yaml"
    undersized_target_path.write_text(yaml.safe_dump(undersized_target), encoding="utf-8")
    with pytest.raises(OAKError) as undersized:
        planning.plan(
            "candidate-03",
            undersized_target_path,
            _context("plan-undersized-target-flow-0001", "0.1.5", 6),
        )
    assert undersized.value.code == "OAK-TARGET-INCOMPATIBLE"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before_wrong_tenant
    plan_context = _context("plan-planning-flow-0001", "0.1.5", 6)
    plan = planning.plan(
        "candidate-03",
        ROOT / "examples/targets/local-fixture.yaml",
        plan_context,
    )
    plan_retry = planning.plan(
        "candidate-03",
        ROOT / "examples/targets/local-fixture.yaml",
        plan_context,
    )

    assert retry.duplicate is True
    assert retry.case == candidates.case
    assert len(candidates.candidates) == 4
    assert {item["status"] for item in candidates.candidates} == {"feasible", "infeasible"}
    assert evaluation.evaluation["status"] == "pass"
    assert evaluation_retry.duplicate is True
    assert selection.case["selected_candidate_ref"]["id"] == "candidate-03"
    assert selection_retry.duplicate is True
    assert assurance.assurance_plan["gate_blockers"][1]["status"] == "blocked"
    assert assurance_retry.duplicate is True
    assert plan.case["status"] == "bundle_compiled"
    assert plan.runner_plan["status"] == "draft"
    assert plan.runner_plan["target"]["tenant_id"] == "local"
    assert plan.runner_plan["target"]["network_mode"] == "disconnected"
    assert all(
        item["result"] in {"pass", "not_applicable"}
        for item in plan.deployment_bundle["extensions"]["oak.community/preflight_results"]
    )
    assert plan.runner_plan["approvals"] == []
    assert [item["kind"] for item in plan.runner_plan["operations"]] == [
        "inventory",
        "validate",
        "render",
        "plan",
        "verify",
    ]
    assert not _contains_forbidden_execution_key(plan.runner_plan)
    assert plan_retry.duplicate is True
    assert plan_retry.semantic_manifest == plan.semantic_manifest

    repository = FileWorkspaceRepository(workspace, _registry())
    manifest = repository.manifest()
    assert manifest["version"] == 7
    assert len(manifest["audit_events"]) == 7
    assert len(manifest["idempotency_records"]) == 7
    repository.export_to(tmp_path / "export")


def test_infeasible_or_unevaluated_candidate_cannot_be_selected(tmp_path: Path) -> None:
    _design, planning, workspace = _ready_services(tmp_path)
    planning.candidates(_context("candidates-denial-flow-0001", "0.1.1", 2))
    before = FileWorkspaceRepository(workspace, _registry()).manifest()

    with pytest.raises(OAKError) as infeasible:
        planning.select(
            "candidate-04",
            "Attempt to select a fixture whose accelerator requirement is unknown.",
            _context("select-infeasible-flow-0001", "0.1.2", 3),
        )
    assert infeasible.value.code == "OAK-SELECT-INFEASIBLE"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before

    with pytest.raises(OAKError) as unevaluated:
        planning.select(
            "candidate-03",
            "Attempt to select before deterministic evaluation exists.",
            _context("select-unevaluated-flow-0001", "0.1.2", 3),
        )
    assert unevaluated.value.code == "OAK-EVALUATION-NOT-FOUND"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before


def test_wrong_state_and_stale_version_leave_state_unchanged(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    design, planning = _services(workspace)
    design.initialize(workspace_id="workspace.denials", tenant_id="local", created_at=BASE_TIME)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context("design-denial-flow-0001", None, 0),
    )
    repository = FileWorkspaceRepository(workspace, _registry())
    before_confirmation = repository.manifest()
    with pytest.raises(OAKError) as state_error:
        planning.candidates(_context("candidates-wrong-state-0001", "0.1.0", 1))
    assert state_error.value.code == "OAK-CANDIDATES-STATE"
    assert repository.manifest() == before_confirmation

    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context("confirm-denial-flow-0001", "0.1.0", 1))
    before_stale = repository.manifest()
    with pytest.raises(OAKError) as stale:
        planning.candidates(_context("candidates-stale-flow-0001", "0.1.0", 2))
    assert stale.value.code == "OAK-EXPECTED-VERSION"
    assert repository.manifest() == before_stale


def _contains_forbidden_execution_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in {"command", "shell", "executable", "argv"}
            or _contains_forbidden_execution_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_execution_key(item) for item in value)
    return False
