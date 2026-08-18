# SPDX-License-Identifier: Apache-2.0
"""OAK-S1-001 through OAK-S1-008 shared application integration tests."""

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from oak.adapters.intake import LocalBriefIntake
from oak.adapters.models import FakeModelInterpreter
from oak.adapters.persistence import FileWorkspaceRepository
from oak.application import CommandContext, DesignCaseService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError
from oak.ports import ProposalLimits

ROOT = Path(__file__).resolve().parents[2]
DESIGN_TIME = "2026-08-17T10:00:00Z"
CONFIRM_TIME = "2026-08-17T10:05:00Z"


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _service(workspace: Path) -> DesignCaseService:
    return DesignCaseService(
        FileWorkspaceRepository(workspace, _registry()),
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        _registry(),
    )


def _context(
    *,
    key: str,
    expected: str | None,
    occurred_at: str,
) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=expected,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=occurred_at,
    )


def _initialized_service(tmp_path: Path) -> tuple[DesignCaseService, Path]:
    workspace = tmp_path / "workspace"
    service = _service(workspace)
    service.initialize(
        workspace_id="workspace.public-manual-qa",
        tenant_id="local",
        created_at=DESIGN_TIME,
    )
    return service, workspace


def _designed_service(tmp_path: Path) -> tuple[DesignCaseService, Path]:
    service, workspace = _initialized_service(tmp_path)
    service.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(
            key="design-public-manual-qa-0001",
            expected=None,
            occurred_at=DESIGN_TIME,
        ),
    )
    return service, workspace


def test_design_creates_one_atomic_case_intent_source_and_audit_lineage(
    tmp_path: Path,
) -> None:
    service, workspace = _initialized_service(tmp_path)
    context = _context(
        key="design-public-manual-qa-0001",
        expected=None,
        occurred_at=DESIGN_TIME,
    )

    first = service.design(ROOT / "examples/briefs/public-manual-qa.yaml", context)
    retry = service.design(ROOT / "examples/briefs/public-manual-qa.yaml", context)

    assert first.duplicate is False
    assert retry.duplicate is True
    assert retry.case == first.case
    assert first.case["status"] == "needs_confirmation"
    assert first.case["version"] == "0.1.1"
    assert first.intent is not None
    assert first.intent["id"] == "intent.public-manual-qa"
    assert len(service.questions().questions) == 5
    manifest = FileWorkspaceRepository(workspace, _registry()).manifest()
    assert manifest["version"] == 2
    assert len(manifest["artifact_index"]) == 7
    assert len(manifest["audit_events"]) == 2
    _registry().validate("design-case.schema.json", first.case)
    _registry().validate("system-intent.schema.json", first.intent)


def test_confirmation_creates_one_successor_and_identical_retry_converges(
    tmp_path: Path,
) -> None:
    service, workspace = _designed_service(tmp_path)
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    context = _context(
        key="confirm-public-manual-qa-0001",
        expected="0.1.1",
        occurred_at=CONFIRM_TIME,
    )

    first = service.confirm(answers, context)
    retry = service.confirm(answers, context)

    assert first.duplicate is False
    assert retry.duplicate is True
    assert first.case["version"] == "0.1.2"
    assert first.intent["version"] == "0.1.1"
    assert first.case["status"] == "ready_for_candidates"
    statuses = {
        question["id"]: question["status"] for question in first.case["unresolved_questions"]
    }
    assert statuses["question.data-classification"] == "resolved"
    assert statuses["question.action-autonomy"] == "resolved"
    assert statuses["question.production-use"] == "resolved"
    assert statuses["question.model-hardware"] == "resolved"
    assert statuses["question.data-volume"] == "resolved"
    manifest = FileWorkspaceRepository(workspace, _registry()).manifest()
    assert manifest["version"] == 3
    assert len(manifest["audit_events"]) == 3
    assert len(manifest["idempotency_records"]) == 3


def test_confirm_correct_reject_and_accept_risk_are_distinct_successor_decisions(
    tmp_path: Path,
) -> None:
    service, _workspace = _designed_service(tmp_path)
    current = service.current()
    hardware = current.intent["spec"]["hardware"]
    answers = {
        "answers_version": "0.1.0",
        "design_case_id": "design-case.public-manual-qa",
        "answers": [
            {
                "question_id": "question.model-hardware",
                "decision": "confirm",
                "value": hardware,
                "rationale": "The fixture hardware values are accepted for local evaluation.",
            },
            {
                "question_id": "question.data-classification",
                "decision": "correct",
                "value": "internal",
                "rationale": "Use the stricter synthetic classification for this test.",
            },
            {
                "question_id": "question.action-autonomy",
                "decision": "reject",
                "value": None,
                "rationale": "No autonomy claim is accepted yet.",
            },
            {
                "question_id": "question.production-use",
                "decision": "accept_risk",
                "value": False,
                "rationale": "The bounded fixture risk is accepted by the named local actor.",
            },
        ],
    }

    result = service.confirm(
        answers,
        _context(
            key="confirm-decision-types-0001",
            expected="0.1.1",
            occurred_at=CONFIRM_TIME,
        ),
    )

    assert result.intent["spec"]["data"]["classifications"] == ["internal"]
    assert "autonomy" not in result.intent["spec"]["decision"]
    statuses = {
        question["id"]: question["status"] for question in result.case["unresolved_questions"]
    }
    assert statuses["question.model-hardware"] == "resolved"
    assert statuses["question.data-classification"] == "resolved"
    assert statuses["question.action-autonomy"] == "open"
    assert statuses["question.production-use"] == "accepted_risk"
    assert len(result.intent["extensions"]["oak.community/confirmations"]) == 4
    _registry().validate("system-intent.schema.json", result.intent)


def test_invalid_confirmation_and_reused_key_leave_workspace_unchanged(tmp_path: Path) -> None:
    service, workspace = _designed_service(tmp_path)
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    invalid = copy.deepcopy(answers)
    invalid["answers"][0]["value"] = "restricted"
    before = FileWorkspaceRepository(workspace, _registry()).manifest()
    context = _context(
        key="confirm-public-manual-qa-0001",
        expected="0.1.1",
        occurred_at=CONFIRM_TIME,
    )

    with pytest.raises(OAKError) as mismatch:
        service.confirm(invalid, context)
    assert mismatch.value.code == "OAK-CONFIRM-VALUE-MISMATCH"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before

    non_json = copy.deepcopy(answers)
    non_json["answers"][0]["value"] = b"not JSON"
    with pytest.raises(OAKError) as malformed:
        service.confirm(non_json, context)
    assert malformed.value.code == "OAK-CONFIRM-MALFORMED"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before

    service.confirm(answers, context)
    changed = copy.deepcopy(answers)
    changed["answers"][0]["rationale"] = "Different normalized input"
    with pytest.raises(OAKError) as reused:
        service.confirm(changed, context)
    assert reused.value.code == "OAK-IDEMPOTENCY-CONFLICT"


def test_optional_proposal_is_read_only_and_provider_failure_adds_no_event(
    tmp_path: Path,
) -> None:
    service, workspace = _designed_service(tmp_path)
    proposal = load_yaml_document(
        (ROOT / "examples/example-interpretation-proposal.yaml").read_text(encoding="utf-8")
    )
    proposal["source_ref"] = service.current().intent["extensions"]["oak.community/source_record"]
    before = FileWorkspaceRepository(workspace, _registry()).manifest()

    assert service.optional_proposal(FakeModelInterpreter(proposal), ProposalLimits()) == proposal
    with pytest.raises(OAKError) as unavailable:
        service.optional_proposal(FakeModelInterpreter(unavailable=True), ProposalLimits())
    assert unavailable.value.code == "OAK-INTERPRETER-UNAVAILABLE"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before

    mismatched = copy.deepcopy(proposal)
    mismatched["source_ref"]["id"] = "source.different"
    with pytest.raises(OAKError) as source_error:
        service.optional_proposal(FakeModelInterpreter(mismatched), ProposalLimits())
    assert source_error.value.code == "OAK-INTERPRETER-SOURCE"
    assert FileWorkspaceRepository(workspace, _registry()).manifest() == before


def test_idempotent_result_is_not_returned_across_tenant_or_actor_context(
    tmp_path: Path,
) -> None:
    service, _workspace = _initialized_service(tmp_path)
    brief = ROOT / "examples/briefs/public-manual-qa.yaml"
    context = _context(
        key="design-public-manual-qa-0001",
        expected=None,
        occurred_at=DESIGN_TIME,
    )
    service.design(brief, context)

    with pytest.raises(OAKError) as tenant_error:
        service.design(brief, replace(context, tenant_id="different-tenant"))
    assert tenant_error.value.code == "OAK-TENANT-MISMATCH"

    with pytest.raises(OAKError) as actor_error:
        service.design(brief, replace(context, actor="different-local-user"))
    assert actor_error.value.code == "OAK-IDEMPOTENCY-CONFLICT"
