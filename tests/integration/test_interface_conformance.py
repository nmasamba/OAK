# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-004 one fixture across local CLI (file mode), REST, MCP, and remote CLI.

Each leg runs the same scenario against its own isolated environment in the same
PostgreSQL instance (the file leg uses the file workspace), with one fixed clock,
then the canonical outcomes are compared: candidate/bundle/semantic digests,
question sets, denial codes, idempotent retry convergence, and audit event
sequences. Transport metadata (interface_origin) is asserted per leg.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import pytest
from typer.testing import CliRunner

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import (
    FileWorkspaceRepository,
    PostgreSQLOperationStore,
    PostgreSQLOutboxStore,
    PostgreSQLWorkspaceRepository,
    create_postgresql_engine,
)
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    CandidatePlanningService,
    CommandContext,
    CommunityControlPlane,
    DesignCaseService,
    OperationService,
    OperationWorker,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError
from oak.interfaces.api.app import create_app
from oak.interfaces.cli.main import app as cli_app
from oak.interfaces.mcp.server import create_server
from tests.mcp_support import MCPClient

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-21T12:00:00Z"
LATER = "2026-08-21T12:05:00Z"
CASE_ID = "design-case.public-manual-qa"
BRIEF_PATH = ROOT / "examples" / "briefs" / "public-manual-qa.yaml"
ANSWERS_PATH = ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml"
TARGET_PATH = ROOT / "examples" / "targets" / "local-fixture.yaml"
BRIEF_TEXT = BRIEF_PATH.read_text(encoding="utf-8")
EXPECTED_EVENT_TYPES = [
    "case_created",
    "brief_interpreted",
    "claims_confirmed",
    "candidates_generated",
    "candidate_evaluated",
    "candidate_selected",
    "assurance_planned",
    "bundle_compiled",
]

pytestmark = pytest.mark.integration

cli_runner = CliRunner()


def _answers() -> dict[str, Any]:
    return load_yaml_document(ANSWERS_PATH.read_text(encoding="utf-8"))


def _target() -> dict[str, Any]:
    return load_yaml_document(TARGET_PATH.read_text(encoding="utf-8"))


def _context(key: str, version: str | None, *, origin: str = "cli") -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin=origin,
        occurred_at=NOW,
    )


class _PersistentLeg:
    """A PostgreSQL-backed control plane isolated by environment id."""

    def __init__(self, tmp_path: Path, database_url: str, label: str) -> None:
        self.engine = create_postgresql_engine(database_url)
        registry = SchemaRegistry.from_directory(ROOT / "schemas")
        suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
        self.environment_id = f"conf-{label}-{suffix}"
        artifact_root = tmp_path / f"artifacts-{label}"

        def repository_factory(workspace_id: str, tenant_id: str) -> PostgreSQLWorkspaceRepository:
            return PostgreSQLWorkspaceRepository(
                self.engine,
                registry,
                artifact_root,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                environment_id=self.environment_id,
            )

        self.store = PostgreSQLOperationStore(
            self.engine, tenant_id="local", environment_id=self.environment_id
        )

        def operation_service_factory(tenant_id: str) -> OperationService:
            assert tenant_id == "local"
            return OperationService(self.store, environment_id=self.environment_id)

        self.control_plane = CommunityControlPlane(
            repository_factory,
            operation_service_factory,
            LocalBriefIntake(),
            DeterministicBriefInterpreter(),
            LocalCatalogue(ROOT / "catalogue", registry),
            LocalTargetProfile(registry),
            registry,
            lambda tenant_id: PostgreSQLOutboxStore(
                self.engine, tenant_id=tenant_id, environment_id=self.environment_id
            ),
        )
        self.worker = OperationWorker(
            self.store,
            {
                "generate_candidates": self.control_plane.execute_operation,
                "evaluate_candidate": self.control_plane.execute_operation,
                "compile_bundle": self.control_plane.execute_operation,
            },
        )

    def drain(self) -> None:
        while (
            self.worker.run_once(worker_id="conformance-worker", now=NOW, lease_expires_at=LATER)
            is not None
        ):
            pass

    def close(self) -> None:
        self.engine.dispose()


class LegDriver(Protocol):
    origin_label: str

    def create(self) -> dict[str, Any]: ...

    def interpret(self, expected: str) -> dict[str, Any]: ...

    def stale_confirm_code(self) -> str | None: ...

    def confirm(self, expected: str) -> dict[str, Any]: ...

    def confirm_retry_duplicate(self, expected: str) -> bool: ...

    def forbidden_confirm_code(self) -> str: ...

    def generate(self, expected: str) -> None: ...

    def evaluate(self, expected: str) -> None: ...

    def select(self, expected: str) -> None: ...

    def assure(self, expected: str) -> None: ...

    def compile(self, expected: str) -> None: ...

    def final_case(self) -> dict[str, Any]: ...

    def audit(self) -> list[dict[str, Any]]: ...


def run_scenario(driver: LegDriver) -> dict[str, Any]:
    created = driver.create()
    assert created["id"] == CASE_ID
    interpreted = driver.interpret(str(created["version"]))
    question_ids = [question["id"] for question in interpreted["unresolved_questions"]]
    stale_code = driver.stale_confirm_code()
    confirmed = driver.confirm(str(interpreted["version"]))
    duplicate = driver.confirm_retry_duplicate(str(interpreted["version"]))
    forbidden_code = driver.forbidden_confirm_code()
    driver.generate(str(confirmed["version"]))
    generated_version = str(driver.final_case()["version"])
    driver.evaluate(generated_version)
    evaluated_version = str(driver.final_case()["version"])
    driver.select(evaluated_version)
    selected_version = str(driver.final_case()["version"])
    driver.assure(selected_version)
    assured_version = str(driver.final_case()["version"])
    driver.compile(assured_version)
    case = driver.final_case()
    events = driver.audit()
    origins = {str(event["interface_origin"]) for event in events}
    assert origins <= {driver.origin_label, "cli"}, origins
    return {
        "question_ids": question_ids,
        "stale_code": stale_code,
        "duplicate_retry": duplicate,
        "forbidden_code": forbidden_code,
        "candidate_digests": sorted(ref["digest"] for ref in case["candidate_refs"]),
        "selected_digest": case["selected_candidate_ref"]["digest"],
        "assurance_digest": case["assurance_plan_ref"]["digest"],
        "bundle_digest": case["deployment_bundle_ref"]["digest"],
        "plan_digest": case["runner_plan_ref"]["digest"],
        "semantic_digest": case["extensions"]["oak.community/semantic_manifest_ref"]["digest"],
        "final_version": str(case["version"]),
        "final_status": str(case["status"]),
        "event_types": [str(event["event_type"]) for event in events],
    }


class FileDriver:
    """Local file mode: the same application services the local CLI wires."""

    origin_label = "cli"

    def __init__(self, tmp_path: Path) -> None:
        registry = SchemaRegistry.from_directory(ROOT / "schemas")
        self.workspace = tmp_path / "file-workspace"
        repository = FileWorkspaceRepository(self.workspace, registry)
        self.repository = repository
        self.design = DesignCaseService(
            repository, LocalBriefIntake(), DeterministicBriefInterpreter(), registry
        )
        self.planning = CandidatePlanningService(
            repository,
            LocalCatalogue(ROOT / "catalogue", registry),
            LocalTargetProfile(registry),
            registry,
        )
        self.design.initialize(
            workspace_id="workspace.public-manual-qa", tenant_id="local", created_at=NOW
        )

    def create(self) -> dict[str, Any]:
        return self.design.create_content(
            original_name="public-manual-qa.yaml",
            content=BRIEF_TEXT.encode("utf-8"),
            context=_context("conform-create-brief-01", None),
        ).case

    def interpret(self, expected: str) -> dict[str, Any]:
        return self.design.interpret(_context("conform-interpret-01", expected)).case

    def stale_confirm_code(self) -> str | None:
        try:
            self.design.confirm(_answers(), _context("conform-confirm-stale-01", "9.9.9"))
        except OAKError as error:
            return error.code
        raise AssertionError("stale confirm was accepted")

    def confirm(self, expected: str) -> dict[str, Any]:
        return self.design.confirm(_answers(), _context("conform-confirm-01", expected)).case

    def confirm_retry_duplicate(self, expected: str) -> bool:
        return self.design.confirm(_answers(), _context("conform-confirm-01", expected)).duplicate

    def forbidden_confirm_code(self) -> str:
        try:
            self.design.confirm(
                _answers(),
                _context("conform-confirm-late-01", str(self.final_case()["version"])),
            )
        except OAKError as error:
            return error.code
        raise AssertionError("late confirm was accepted")

    def generate(self, expected: str) -> None:
        self.planning.candidates(_context("conform-candidates-01", expected))

    def evaluate(self, expected: str) -> None:
        self.planning.evaluate("candidate-03", _context("conform-evaluate-01", expected))

    def select(self, expected: str) -> None:
        self.planning.select("candidate-03", "balanced", _context("conform-select-01", expected))

    def assure(self, expected: str) -> None:
        self.planning.assure("candidate-03", _context("conform-assure-01", expected))

    def compile(self, expected: str) -> None:
        self.planning.plan_document(
            "candidate-03", _target(), _context("conform-compile-01", expected)
        )

    def final_case(self) -> dict[str, Any]:
        return self.design.current().case

    def audit(self) -> list[dict[str, Any]]:
        from oak.domain import ArtifactReference

        events = []
        for entry in self.repository.manifest()["artifact_index"]:
            if str(entry["kind"]) != "audit_event":
                continue
            reference = ArtifactReference(
                id=str(entry["id"]),
                version=str(entry["version"]),
                digest=str(entry["digest"]),
                media_type=str(entry["media_type"]),
            )
            events.append(self.repository.read_json_artifact(reference))
        events.sort(key=lambda event: int(event["sequence"]))
        return events


class RestDriver:
    """Raw REST over a live loopback server, drained by a direct worker."""

    origin_label = "api"

    def __init__(self, leg: _PersistentLeg, base_url: str) -> None:
        self.leg = leg
        self.base_url = base_url

    def _request(
        self,
        method: str,
        path: str,
        *,
        key: str | None = None,
        version: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if key is not None:
            headers["Idempotency-Key"] = key
            headers["X-Correlation-ID"] = f"correlation-{key}"
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _operation(self, submitted: dict[str, Any]) -> None:
        self.leg.drain()
        status, operation = self._request("GET", f"/v1/operations/{submitted['operation_id']}")
        assert status == 200 and operation["state"] == "succeeded", operation

    def create(self) -> dict[str, Any]:
        status, document = self._request(
            "POST",
            "/v1/design-cases",
            key="conform-create-brief-01",
            body={"original_name": "public-manual-qa.yaml", "content": BRIEF_TEXT},
        )
        assert status == 201, document
        return document["case"]

    def interpret(self, expected: str) -> dict[str, Any]:
        status, document = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:interpret",
            key="conform-interpret-01",
            version=expected,
        )
        assert status == 200, document
        return document["case"]

    def stale_confirm_code(self) -> str | None:
        status, problem = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:confirm",
            key="conform-confirm-stale-01",
            version="9.9.9",
            body={"answers": _answers()},
        )
        assert status == 409, problem
        return str(problem["code"])

    def confirm(self, expected: str) -> dict[str, Any]:
        status, document = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:confirm",
            key="conform-confirm-01",
            version=expected,
            body={"answers": _answers()},
        )
        assert status == 200, document
        return document["case"]

    def confirm_retry_duplicate(self, expected: str) -> bool:
        status, document = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:confirm",
            key="conform-confirm-01",
            version=expected,
            body={"answers": _answers()},
        )
        assert status == 200, document
        return bool(document["duplicate"])

    def forbidden_confirm_code(self) -> str:
        status, problem = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:confirm",
            key="conform-confirm-late-01",
            version=str(self.final_case()["version"]),
            body={"answers": _answers()},
        )
        assert status == 409, problem
        return str(problem["code"])

    def generate(self, expected: str) -> None:
        status, submitted = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:generate-candidates",
            key="conform-candidates-01",
            version=expected,
        )
        assert status == 202, submitted
        self._operation(submitted)

    def evaluate(self, expected: str) -> None:
        status, submitted = self._request(
            "POST",
            "/v1/candidates/candidate-03:evaluate",
            key="conform-evaluate-01",
            version=expected,
            body={"case_id": CASE_ID},
        )
        assert status == 202, submitted
        self._operation(submitted)

    def select(self, expected: str) -> None:
        status, document = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:select-candidate",
            key="conform-select-01",
            version=expected,
            body={"candidate_id": "candidate-03", "rationale": "balanced"},
        )
        assert status == 200, document

    def assure(self, expected: str) -> None:
        status, document = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:create-assurance-plan",
            key="conform-assure-01",
            version=expected,
            body={"candidate_id": "candidate-03"},
        )
        assert status == 200, document

    def compile(self, expected: str) -> None:
        status, submitted = self._request(
            "POST",
            f"/v1/design-cases/{CASE_ID}:compile",
            key="conform-compile-01",
            version=expected,
            body={"candidate_id": "candidate-03", "target": _target()},
        )
        assert status == 202, submitted
        self._operation(submitted)

    def final_case(self) -> dict[str, Any]:
        status, document = self._request("GET", f"/v1/design-cases/{CASE_ID}")
        assert status == 200, document
        return document["case"]

    def audit(self) -> list[dict[str, Any]]:
        return list(self.leg.control_plane.list_audit_events(CASE_ID, tenant_id="local"))


class McpDriver:
    """Real MCP frames; candidate selection happens out of band by design."""

    origin_label = "mcp"

    def __init__(self, leg: _PersistentLeg) -> None:
        self.leg = leg
        server = create_server(
            leg.control_plane,
            server_version="conformance",
            local_actor="local-user",
            local_tenant="local",
            clock=lambda: NOW,
        )
        self.client = MCPClient(server)

    def _operation(self, submitted: dict[str, Any]) -> None:
        self.leg.drain()
        operation = self.client.call_ok(
            "oak_operation_get", {"operation_id": submitted["operation_id"]}
        )
        assert operation["state"] == "succeeded", operation

    def create(self) -> dict[str, Any]:
        return self.client.call_ok(
            "oak_design_case_create",
            {
                "original_name": "public-manual-qa.yaml",
                "content": BRIEF_TEXT,
                "idempotency_key": "conform-create-brief-01",
            },
        )["case"]

    def interpret(self, expected: str) -> dict[str, Any]:
        return self.client.call_ok(
            "oak_design_case_interpret",
            {
                "case_id": CASE_ID,
                "expected_version": expected,
                "idempotency_key": "conform-interpret-01",
            },
        )["case"]

    def stale_confirm_code(self) -> str | None:
        denial = self.client.call_error(
            "oak_claims_confirm",
            {
                "case_id": CASE_ID,
                "answers": _answers(),
                "actor": "local-user",
                "expected_version": "9.9.9",
                "idempotency_key": "conform-confirm-stale-01",
            },
        )
        return str(denial["code"])

    def confirm(self, expected: str) -> dict[str, Any]:
        return self.client.call_ok(
            "oak_claims_confirm",
            {
                "case_id": CASE_ID,
                "answers": _answers(),
                "actor": "local-user",
                "expected_version": expected,
                "idempotency_key": "conform-confirm-01",
            },
        )["case"]

    def confirm_retry_duplicate(self, expected: str) -> bool:
        return bool(
            self.client.call_ok(
                "oak_claims_confirm",
                {
                    "case_id": CASE_ID,
                    "answers": _answers(),
                    "actor": "local-user",
                    "expected_version": expected,
                    "idempotency_key": "conform-confirm-01",
                },
            )["duplicate"]
        )

    def forbidden_confirm_code(self) -> str:
        denial = self.client.call_error(
            "oak_claims_confirm",
            {
                "case_id": CASE_ID,
                "answers": _answers(),
                "actor": "local-user",
                "expected_version": str(self.final_case()["version"]),
                "idempotency_key": "conform-confirm-late-01",
            },
        )
        return str(denial["code"])

    def generate(self, expected: str) -> None:
        submitted = self.client.call_ok(
            "oak_candidates_generate",
            {
                "case_id": CASE_ID,
                "expected_version": expected,
                "idempotency_key": "conform-candidates-01",
            },
        )
        self._operation(submitted)

    def evaluate(self, expected: str) -> None:
        submitted = self.client.call_ok(
            "oak_candidate_evaluate",
            {
                "case_id": CASE_ID,
                "candidate_id": "candidate-03",
                "expected_version": expected,
                "idempotency_key": "conform-evaluate-01",
            },
        )
        self._operation(submitted)

    def select(self, expected: str) -> None:
        # Deliberately not an MCP tool: the material decision is made through
        # another interface against the same control plane.
        self.leg.control_plane.select_candidate(
            CASE_ID, "candidate-03", "balanced", _context("conform-select-01", expected)
        )

    def assure(self, expected: str) -> None:
        self.client.call_ok(
            "oak_assurance_plan_create",
            {
                "case_id": CASE_ID,
                "candidate_id": "candidate-03",
                "expected_version": expected,
                "idempotency_key": "conform-assure-01",
            },
        )

    def compile(self, expected: str) -> None:
        submitted = self.client.call_ok(
            "oak_bundle_compile",
            {
                "case_id": CASE_ID,
                "candidate_id": "candidate-03",
                "target": _target(),
                "expected_version": expected,
                "idempotency_key": "conform-compile-01",
            },
        )
        self._operation(submitted)

    def final_case(self) -> dict[str, Any]:
        return self.client.call_ok("oak_design_case_get", {"case_id": CASE_ID})["case"]

    def audit(self) -> list[dict[str, Any]]:
        return list(self.leg.control_plane.list_audit_events(CASE_ID, tenant_id="local"))


class RemoteCliDriver:
    """The installed CLI in --server mode against a live loopback server."""

    origin_label = "api"

    def __init__(self, leg: _PersistentLeg, base_url: str, tmp_path: Path) -> None:
        self.leg = leg
        self.base_url = base_url
        self.tmp_path = tmp_path

    def _invoke(self, *arguments: str) -> Any:
        result = cli_runner.invoke(cli_app, ["--server", self.base_url, *arguments])
        return result

    def _invoke_json(self, *arguments: str) -> dict[str, Any]:
        result = self._invoke(*arguments, "--output", "json")
        assert result.exit_code == 0, result.output
        document = json.loads(result.output)
        assert isinstance(document, dict)
        return document

    def create(self) -> dict[str, Any]:
        # oak design is create + interpret in one command; create() returns the
        # case as of creation for version bookkeeping, so this driver defers the
        # combined command to interpret().
        return {"id": CASE_ID, "version": "0.1.0"}

    def interpret(self, expected: str) -> dict[str, Any]:
        del expected
        self._invoke_json("design", str(BRIEF_PATH))
        return self.final_case()

    def stale_confirm_code(self) -> str | None:
        # The remote CLI always fetches the current version before confirming,
        # so a stale expected version cannot be injected through it.
        return None

    def confirm(self, expected: str) -> dict[str, Any]:
        del expected
        document = self._invoke_json("confirm", CASE_ID, "--answers", str(ANSWERS_PATH))
        return document["case"]

    def confirm_retry_duplicate(self, expected: str) -> bool:
        del expected
        document = self._invoke_json("confirm", CASE_ID, "--answers", str(ANSWERS_PATH))
        return bool(document["duplicate"])

    def forbidden_confirm_code(self) -> str:
        result = self._invoke(
            "confirm",
            CASE_ID,
            "--answers",
            str(ANSWERS_PATH),
            "--idempotency-key",
            "conform-confirm-late-01",
        )
        assert result.exit_code == 2, result.output
        try:
            stderr = str(result.stderr)
        except (AttributeError, ValueError):
            stderr = ""
        combined = str(result.output) + stderr
        return combined.split(":", 1)[0].strip()

    def generate(self, expected: str) -> None:
        del expected
        self._invoke_json("candidates", CASE_ID)

    def evaluate(self, expected: str) -> None:
        del expected
        self._invoke_json("evaluate", "candidate-03", "--case", CASE_ID)

    def select(self, expected: str) -> None:
        del expected
        rationale = self.tmp_path / "decision.md"
        rationale.write_text("balanced\n", encoding="utf-8")
        self._invoke_json(
            "select",
            "candidate-03",
            "--rationale-file",
            str(rationale),
            "--case",
            CASE_ID,
        )

    def assure(self, expected: str) -> None:
        del expected
        destination = self.tmp_path / "assurance"
        result = self._invoke(
            "assure", "candidate-03", "--case", CASE_ID, "--output", str(destination)
        )
        assert result.exit_code == 0, result.output

    def compile(self, expected: str) -> None:
        del expected
        destination = self.tmp_path / "bundle"
        result = self._invoke(
            "plan",
            "candidate-03",
            "--case",
            CASE_ID,
            "--target",
            str(TARGET_PATH),
            "--output",
            str(destination),
        )
        assert result.exit_code == 0, result.output

    def final_case(self) -> dict[str, Any]:
        return self.leg.control_plane.get_design_case(CASE_ID, tenant_id="local").case

    def audit(self) -> list[dict[str, Any]]:
        return list(self.leg.control_plane.list_audit_events(CASE_ID, tenant_id="local"))


class _Uvicorn:
    def __init__(self, control_plane: CommunityControlPlane) -> None:
        import uvicorn

        application = create_app(control_plane=control_plane, clock=lambda: NOW)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=self.port,
                log_level="critical",
                access_log=False,
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> _Uvicorn:
        self.thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.url}/healthz", timeout=0.5) as response:
                    if response.status == 200:
                        return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the loopback API did not become healthy in time")

    def __exit__(self, *exc_info: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def database_url() -> str:
    import os

    url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for interface conformance tests")
    return url


def test_the_same_fixture_produces_identical_outcomes_across_all_interfaces(
    tmp_path: Path, database_url: str
) -> None:
    outcomes: dict[str, dict[str, Any]] = {}
    origins: dict[str, list[str]] = {}

    file_driver = FileDriver(tmp_path)
    outcomes["file"] = run_scenario(file_driver)
    origins["file"] = [str(e["interface_origin"]) for e in file_driver.audit()]

    rest_leg = _PersistentLeg(tmp_path, database_url, "rest")
    try:
        with _Uvicorn(rest_leg.control_plane) as server:
            rest_driver = RestDriver(rest_leg, server.url)
            outcomes["rest"] = run_scenario(rest_driver)
            origins["rest"] = [str(e["interface_origin"]) for e in rest_driver.audit()]
    finally:
        rest_leg.close()

    mcp_leg = _PersistentLeg(tmp_path / "mcp", database_url, "mcp")
    try:
        mcp_driver = McpDriver(mcp_leg)
        outcomes["mcp"] = run_scenario(mcp_driver)
        origins["mcp"] = [str(e["interface_origin"]) for e in mcp_driver.audit()]
    finally:
        mcp_leg.close()

    cli_leg = _PersistentLeg(tmp_path / "cli", database_url, "cli")
    stop = threading.Event()

    def drain_loop() -> None:
        while not stop.is_set():
            cli_leg.drain()
            time.sleep(0.05)

    drainer = threading.Thread(target=drain_loop, daemon=True)
    try:
        with _Uvicorn(cli_leg.control_plane) as server:
            drainer.start()
            cli_driver = RemoteCliDriver(cli_leg, server.url, tmp_path / "cli-out")
            (tmp_path / "cli-out").mkdir()
            outcomes["remote-cli"] = run_scenario(cli_driver)
            origins["remote-cli"] = [str(e["interface_origin"]) for e in cli_driver.audit()]
    finally:
        stop.set()
        drainer.join(timeout=10)
        cli_leg.close()

    # Canonical meaning must be identical across every interface.
    reference = outcomes["file"]
    for name, outcome in outcomes.items():
        assert outcome["event_types"] == EXPECTED_EVENT_TYPES, name
        assert outcome["final_status"] == "bundle_compiled", name
        assert outcome["final_version"] == "0.1.7", name
        assert outcome["question_ids"] == reference["question_ids"], name
        assert outcome["candidate_digests"] == reference["candidate_digests"], name
        assert outcome["selected_digest"] == reference["selected_digest"], name
        assert outcome["assurance_digest"] == reference["assurance_digest"], name
        assert outcome["bundle_digest"] == reference["bundle_digest"], name
        assert outcome["semantic_digest"] == reference["semantic_digest"], name
        assert outcome["duplicate_retry"] is True, name
        assert outcome["forbidden_code"] == "OAK-CONFIRM-STATE", name

    # The runner plan binds the exact case document (`design_case_ref.digest`),
    # and the case document carries its transport lineage — `interface_origin`
    # and the `audit_head` chain with per-request idempotency keys — so the plan
    # digest is deliberately lineage-specific, not cross-interface equal. That
    # is the same reason the Sprint 3 parity test compares a semantic case
    # projection rather than the raw case digest. Every semantic artifact the
    # plan transports (bundle, manifest, candidates, decision, assurance) is
    # digest-identical above; only the case-lineage binding differs.
    assert all(outcome["plan_digest"].startswith("sha256:") for outcome in outcomes.values())
    assert outcomes["rest"]["plan_digest"] != outcomes["file"]["plan_digest"]

    # A stale expected version is denied with one stable code everywhere the
    # transport can express one; the remote CLI fetches the current version.
    for name in ("file", "rest", "mcp"):
        assert outcomes[name]["stale_code"] == "OAK-EXPECTED-VERSION", name
    assert outcomes["remote-cli"]["stale_code"] is None

    # interface_origin is audit metadata that names the transport actually used.
    assert set(origins["file"]) == {"cli"}
    assert set(origins["rest"]) == {"api"}
    assert set(origins["remote-cli"]) == {"api"}
    assert origins["mcp"] == ["mcp", "mcp", "mcp", "mcp", "mcp", "cli", "mcp", "mcp"]
