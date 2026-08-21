# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-001 MCP journey over real frames against a real file-backed control plane."""

from pathlib import Path

import pytest
import yaml

from oak.application import CommandContext
from tests.mcp_support import NOW, ROOT, MCPClient, build_server, drain_operations

pytestmark = pytest.mark.integration

BRIEF = (ROOT / "examples" / "briefs" / "public-manual-qa.yaml").read_text(encoding="utf-8")
ANSWERS_PATH = ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml"
TARGET_PATH = ROOT / "examples" / "targets" / "local-fixture.yaml"


def _selection_context(key: str, version: str) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


def test_mcp_journey_reaches_bundle_compiled_with_selection_outside_mcp(tmp_path: Path) -> None:
    server, control_plane, store = build_server(tmp_path)
    client = MCPClient(server)

    created = client.call_ok(
        "oak_design_case_create",
        {
            "original_name": "public-manual-qa.yaml",
            "content": BRIEF,
            "idempotency_key": "mcp-create-brief-0001",
        },
    )
    case = created["case"]
    case_id = case["id"]
    assert case_id == "design-case.public-manual-qa"
    assert case["status"] == "draft"
    assert case["interface_origin"] == "mcp"
    assert created["duplicate"] is False

    duplicate = client.call_ok(
        "oak_design_case_create",
        {
            "original_name": "public-manual-qa.yaml",
            "content": BRIEF,
            "idempotency_key": "mcp-create-brief-0001",
        },
    )
    assert duplicate["duplicate"] is True

    interpreted = client.call_ok(
        "oak_design_case_interpret",
        {
            "case_id": case_id,
            "expected_version": str(case["version"]),
            "idempotency_key": "mcp-interpret-brief-0001",
        },
    )
    assert interpreted["case"]["status"] == "needs_confirmation"
    assert interpreted["intent"] is not None

    questions = client.call_ok("oak_questions_list", {"case_id": case_id})
    assert questions["case_id"] == case_id
    assert len(questions["questions"]) >= 1

    answers = yaml.safe_load(ANSWERS_PATH.read_text(encoding="utf-8"))
    confirmed = client.call_ok(
        "oak_claims_confirm",
        {
            "case_id": case_id,
            "answers": answers,
            "actor": "local-user",
            "expected_version": str(interpreted["case"]["version"]),
            "idempotency_key": "mcp-confirm-claims-0001",
        },
    )
    assert confirmed["case"]["status"] == "ready_for_candidates"

    submitted = client.call_ok(
        "oak_candidates_generate",
        {
            "case_id": case_id,
            "expected_version": str(confirmed["case"]["version"]),
            "idempotency_key": "mcp-generate-cand-0001",
        },
    )
    assert submitted["state"] == "queued"
    assert drain_operations(control_plane, store) == 1
    operation = client.call_ok("oak_operation_get", {"operation_id": submitted["operation_id"]})
    assert operation["state"] == "succeeded"
    assert operation["result"] is not None

    listed = client.call_ok("oak_candidates_list", {"case_id": case_id})
    candidate_ids = {item["id"] for item in listed["items"]}
    assert "candidate-03" in candidate_ids

    generated_version = operation["result"]["case_version"]
    evaluation = client.call_ok(
        "oak_candidate_evaluate",
        {
            "case_id": case_id,
            "candidate_id": "candidate-03",
            "expected_version": str(generated_version),
            "idempotency_key": "mcp-evaluate-cand-0001",
        },
    )
    assert drain_operations(control_plane, store) == 1
    evaluated = client.call_ok("oak_operation_get", {"operation_id": evaluation["operation_id"]})
    assert evaluated["state"] == "succeeded"

    # Candidate selection is a material decision and is deliberately not an MCP
    # tool; it happens through another interface against the same control plane.
    evaluated_version = evaluated["result"]["case"]["version"]
    selection = control_plane.select_candidate(
        case_id,
        "candidate-03",
        "balanced",
        _selection_context("cli-select-cand-0001", str(evaluated_version)),
    )
    assert selection.case["status"] == "candidate_selected"

    assured = client.call_ok(
        "oak_assurance_plan_create",
        {
            "case_id": case_id,
            "candidate_id": "candidate-03",
            "expected_version": str(selection.case["version"]),
            "idempotency_key": "mcp-assure-cand-0001",
        },
    )
    assert assured["case"]["status"] == "assurance_planned"

    target = yaml.safe_load(TARGET_PATH.read_text(encoding="utf-8"))
    compile_submission = client.call_ok(
        "oak_bundle_compile",
        {
            "case_id": case_id,
            "candidate_id": "candidate-03",
            "target": target,
            "expected_version": str(assured["case"]["version"]),
            "idempotency_key": "mcp-compile-bundle-01",
        },
    )
    assert drain_operations(control_plane, store) == 1
    compiled = client.call_ok(
        "oak_operation_get", {"operation_id": compile_submission["operation_id"]}
    )
    assert compiled["state"] == "succeeded"
    result = compiled["result"]
    assert result["case"]["status"] == "bundle_compiled"
    assert result["runner_plan"]["status"] == "draft"

    final = client.call_ok("oak_design_case_get", {"case_id": case_id})
    assert final["case"]["status"] == "bundle_compiled"
    assert final["case"]["version"] == "0.1.7"


def test_mcp_stale_version_and_unknown_case_fail_with_stable_codes(tmp_path: Path) -> None:
    server, _control_plane, _store = build_server(tmp_path)
    client = MCPClient(server)
    client.call_ok(
        "oak_design_case_create",
        {
            "original_name": "public-manual-qa.yaml",
            "content": BRIEF,
            "idempotency_key": "mcp-create-brief-0002",
        },
    )
    stale = client.call_error(
        "oak_design_case_interpret",
        {
            "case_id": "design-case.public-manual-qa",
            "expected_version": "9.9.9",
            "idempotency_key": "mcp-interpret-stale-01",
        },
    )
    assert stale["code"] == "OAK-EXPECTED-VERSION"
    assert stale["retriable"] is True

    missing = client.call_error("oak_design_case_get", {"case_id": "design-case.absent"})
    assert missing["code"] == "OAK-WORKSPACE-NOT-FOUND"
    assert missing["message"] == "The requested resource was not found."
