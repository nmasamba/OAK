# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-004: the model path means the same thing on every interface.

The same prose brief and the same binding fake adapter run through the file-mode service,
REST (in-process ASGI over the loopback guard) and MCP. Each leg must produce the same
intent bytes, the same proposal digest, the same question ids, the two expected event
types and case version ``0.1.1``. Each leg must also refuse the model with one code when no
adapter is configured; REST must demand the capability token before spending a credential;
and MCP must stay deterministic unless the client opts in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.application import CommandContext, DesignCaseService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference
from oak.interfaces.api.app import create_app
from oak.interfaces.mcp.server import create_server
from oak.ports import ModelInterpreterPort
from tests.mcp_support import MCPClient, build_file_control_plane
from tests.model_support import BindingFakeModelInterpreter, model_factory

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
BRIEF_PATH = ROOT / "examples/briefs/public-manual-qa-prose.md"
BRIEF_TEXT = BRIEF_PATH.read_text(encoding="utf-8")
NOW = "2026-08-21T12:00:00Z"
TOKEN = "conformance-model-token-0123456789abcdef"
PROPOSAL_REF = "oak.community/interpretation_proposal_ref"
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")


MODES = ("online", "local")


def _adapter(mode: str = "online") -> BindingFakeModelInterpreter:
    if mode == "local":
        return BindingFakeModelInterpreter(
            extensions={
                "oak.community/model": {
                    "family": "local",
                    "model_id": "qwen3:8b",
                    "provider_route": None,
                }
            }
        )
    return BindingFakeModelInterpreter()


def _summary(
    case: dict[str, Any], intent: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "version": case["version"],
        "status": case["status"],
        "question_ids": [q["id"] for q in case["unresolved_questions"]],
        "intent_digest": case["intent_ref"]["digest"],
        "proposal_digest": intent["extensions"][PROPOSAL_REF]["digest"],
        "event_types": [event["event_type"] for event in events],
        "interpreter_extension": events[-1]["extensions"]["oak.community/interpreter"],
    }


# ----- file leg -----------------------------------------------------------------


def _file_leg(
    tmp_path: Path, adapter: ModelInterpreterPort | None, mode: str = "online"
) -> dict[str, Any]:
    workspace = tmp_path / "file"
    repository = FileWorkspaceRepository(workspace, REGISTRY)
    service = DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        REGISTRY,
        model_interpreter_factory=model_factory(adapter),
    )
    service.initialize(workspace_id="workspace.conformance", tenant_id="local", created_at=NOW)
    context = CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key="conform-model-design-01",
        expected_version=None,
        correlation_id="correlation-conform-model-design-01",
        interface_origin="cli",
        occurred_at=NOW,
    )
    result = service.design(BRIEF_PATH, context, interpreter=mode)
    assert result.intent is not None
    events = [
        repository.read_json_artifact(ArtifactReference.from_document(entry))
        for entry in repository.manifest()["audit_events"]
    ]
    return _summary(result.case, result.intent, events)


# ----- REST leg -----------------------------------------------------------------


class _Rest:
    def __init__(self, tmp_path: Path, adapter: ModelInterpreterPort | None) -> None:
        self.plane, _ = build_file_control_plane(
            tmp_path / "rest", model_interpreter_factory=model_factory(adapter)
        )
        app = create_app(control_plane=self.plane, clock=lambda: NOW, model_token=TOKEN)
        self.client = TestClient(app, base_url="http://127.0.0.1")

    def create(self) -> dict[str, Any]:
        response = self.client.post(
            "/v1/design-cases",
            headers={
                "Idempotency-Key": "conform-model-create-01",
                "X-Correlation-ID": "correlation-conform-model-create-01",
            },
            json={"original_name": BRIEF_PATH.name, "content": BRIEF_TEXT},
        )
        assert response.status_code == 201, response.text
        case: dict[str, Any] = response.json()["case"]
        return case

    def interpret(
        self,
        case_id: str,
        version: str,
        *,
        interpreter: str | None,
        token: str | None,
        key: str = "conform-model-interpret-01",
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Idempotency-Key": key,
            "X-Correlation-ID": f"correlation-{key}",
            "If-Match": f'"{version}"',
        }
        if token is not None:
            headers["X-OAK-Model-Token"] = token
        query = "" if interpreter is None else f"?interpreter={interpreter}"
        response = self.client.post(f"/v1/design-cases/{case_id}:interpret{query}", headers=headers)
        body: dict[str, Any] = response.json()
        return response.status_code, body

    def case(self, case_id: str) -> dict[str, Any]:
        response = self.client.get(f"/v1/design-cases/{case_id}")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def events(self, case_id: str) -> list[dict[str, Any]]:
        response = self.client.get(f"/v1/design-cases/{case_id}/audit")
        assert response.status_code == 200, response.text
        items: list[dict[str, Any]] = response.json()["items"]
        return items


def _rest_leg(
    tmp_path: Path, adapter: ModelInterpreterPort | None, mode: str = "online"
) -> dict[str, Any]:
    rest = _Rest(tmp_path, adapter)
    created = rest.create()
    case_id = str(created["id"])

    # Asking for the model by name without the token is refused, and nothing is committed.
    for token in (None, "wrong-token-0123456789"):
        status, problem = rest.interpret(case_id, "0.1.0", interpreter="online", token=token)
        assert status == 403, problem
        assert problem["code"] == "OAK-MODEL-TOKEN-REQUIRED"
    assert rest.case(case_id)["case"]["version"] == "0.1.0"
    assert len(rest.events(case_id)) == 1

    # An absent parameter — what a client written before the model path existed sends — is
    # deterministic. Without the token it succeeds rather than turning into a 403 the moment
    # somebody sets a model up. The deterministic interpreter never needs the token.
    status, deterministic = rest.interpret(
        case_id, "0.1.0", interpreter=None, token=None, key="conform-model-dry-run-01"
    )
    assert status == 200, deterministic
    assert PROPOSAL_REF not in deterministic["intent"]["extensions"]
    # ... but that committed a deterministic interpretation, so use a fresh leg for the
    # model run itself.
    rest = _Rest(tmp_path / "model-run", adapter)
    created = rest.create()
    case_id = str(created["id"])
    status, interpreted = rest.interpret(case_id, "0.1.0", interpreter=mode, token=TOKEN)
    assert status == 200, interpreted
    return _summary(interpreted["case"], interpreted["intent"], rest.events(case_id))


# ----- MCP leg ------------------------------------------------------------------


class _Mcp:
    def __init__(self, tmp_path: Path, adapter: ModelInterpreterPort | None) -> None:
        self.plane, _ = build_file_control_plane(
            tmp_path / "mcp", model_interpreter_factory=model_factory(adapter)
        )
        server = create_server(
            self.plane,
            server_version="conformance",
            local_actor="local-user",
            local_tenant="local",
            clock=lambda: NOW,
        )
        self.client = MCPClient(server)

    def create(self) -> dict[str, Any]:
        case: dict[str, Any] = self.client.call_ok(
            "oak_design_case_create",
            {
                "original_name": BRIEF_PATH.name,
                "content": BRIEF_TEXT,
                "idempotency_key": "conform-model-create-01",
            },
        )["case"]
        return case

    def interpret_arguments(
        self, case_id: str, version: str, interpreter: str | None
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "case_id": case_id,
            "expected_version": version,
            "idempotency_key": "conform-model-interpret-01",
        }
        if interpreter is not None:
            arguments["interpreter"] = interpreter
        return arguments

    def events(self, case_id: str) -> list[dict[str, Any]]:
        return list(self.plane.list_audit_events(case_id, tenant_id="local"))


def _mcp_leg(
    tmp_path: Path, adapter: ModelInterpreterPort | None, mode: str = "online"
) -> dict[str, Any]:
    mcp = _Mcp(tmp_path, adapter)
    created = mcp.create()
    case_id = str(created["id"])
    interpreted = mcp.client.call_ok(
        "oak_design_case_interpret", mcp.interpret_arguments(case_id, "0.1.0", mode)
    )
    return _summary(interpreted["case"], interpreted["intent"], mcp.events(case_id))


# ----- the comparisons ----------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_the_model_path_is_identical_across_file_rest_and_mcp(tmp_path: Path, mode: str) -> None:
    outcomes = {
        "file": _file_leg(tmp_path, _adapter(mode), mode),
        "rest": _rest_leg(tmp_path, _adapter(mode), mode),
        "mcp": _mcp_leg(tmp_path, _adapter(mode), mode),
    }
    reference = outcomes["file"]
    assert reference["version"] == "0.1.1"
    assert reference["status"] == "needs_confirmation"
    assert reference["event_types"] == ["case_created", "brief_interpreted"]
    assert reference["interpreter_extension"]["kind"] == "model"
    assert reference["interpreter_extension"]["mode"] == mode
    assert reference["interpreter_extension"]["family"] == (
        "local" if mode == "local" else "huggingface"
    )
    assert reference["interpreter_extension"]["proposal_digest"] == reference["proposal_digest"]
    assert len(reference["question_ids"]) == 9
    for name, outcome in outcomes.items():
        assert outcome == reference, (name, json.dumps(outcome, indent=1))


def test_every_interface_refuses_the_model_with_one_code_when_none_is_configured(
    tmp_path: Path,
) -> None:
    rest = _Rest(tmp_path, None)
    case_id = str(rest.create()["id"])
    status, problem = rest.interpret(case_id, "0.1.0", interpreter="online", token=TOKEN)
    assert status == 422, problem
    assert problem["code"] == "OAK-MODEL-NOT-CONFIGURED"
    assert rest.case(case_id)["case"]["version"] == "0.1.0"
    # An absent parameter is deterministic and needs no token whether or not a model exists.
    status, body = rest.interpret(case_id, "0.1.0", interpreter=None, token=None)
    assert status == 200, body
    assert PROPOSAL_REF not in body["intent"]["extensions"]

    mcp = _Mcp(tmp_path, None)
    case_id = str(mcp.create()["id"])
    denial = mcp.client.call_error(
        "oak_design_case_interpret", mcp.interpret_arguments(case_id, "0.1.0", "online")
    )
    assert denial["code"] == "OAK-MODEL-NOT-CONFIGURED"
    assert mcp.plane.get_design_case(case_id, tenant_id="local").case["version"] == "0.1.0"


def test_mcp_defaults_to_the_deterministic_interpreter_even_when_a_model_is_configured(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    mcp = _Mcp(tmp_path, adapter)
    case_id = str(mcp.create()["id"])
    interpreted = mcp.client.call_ok(
        "oak_design_case_interpret", mcp.interpret_arguments(case_id, "0.1.0", None)
    )
    assert adapter.calls == []
    assert PROPOSAL_REF not in interpreted["intent"]["extensions"]
    assert interpreted["case"]["version"] == "0.1.1"
    assert [q["id"] for q in interpreted["case"]["unresolved_questions"]] == [
        "question.accountable-owner",
        "question.model-hardware",
        "question.production-use",
        "question.action-autonomy",
        "question.data-classification",
    ]
    events = mcp.events(case_id)
    assert events[-1]["extensions"] == {}
    # The optional argument is closed to the three documented values; anything else is a
    # protocol-level argument error, so neither Sprint 9's `auto` nor `model` can be
    # requested over MCP at all.
    for spelling in ("auto", "model"):
        response = mcp.client.request(
            "tools/call",
            {
                "name": "oak_design_case_interpret",
                "arguments": mcp.interpret_arguments(case_id, "0.1.1", spelling),
            },
        )
        assert response["error"]["data"]["code"] == "OAK-REQUEST-INVALID", spelling
    assert adapter.calls == []
