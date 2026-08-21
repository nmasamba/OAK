# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-002 remote CLI mode against a live loopback control plane."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from oak.interfaces.api.app import create_app
from oak.interfaces.cli.main import app as cli_app
from tests.mcp_support import NOW, ROOT, build_file_control_plane, drain_operations

pytestmark = pytest.mark.integration

BRIEF_PATH = ROOT / "examples" / "briefs" / "public-manual-qa.yaml"
ANSWERS_PATH = ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml"
TARGET_PATH = ROOT / "examples" / "targets" / "local-fixture.yaml"
CASE_ID = "design-case.public-manual-qa"

runner = CliRunner()


class _LiveServer:
    def __init__(self, tmp_path: Path) -> None:
        self.control_plane, self.store = build_file_control_plane(tmp_path)
        application = create_app(control_plane=self.control_plane, clock=lambda: NOW)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        config = uvicorn.Config(
            application,
            host="127.0.0.1",
            port=self.port,
            log_level="critical",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.stop_draining = threading.Event()
        self.drainer = threading.Thread(target=self._drain_loop, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.url}/healthz", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("the loopback API did not become healthy in time")
        self.drainer.start()

    def stop(self) -> None:
        self.stop_draining.set()
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.drainer.join(timeout=10)

    def _drain_loop(self) -> None:
        while not self.stop_draining.is_set():
            drain_operations(self.control_plane, self.store)
            time.sleep(0.05)


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_LiveServer]:
    server = _LiveServer(tmp_path_factory.mktemp("remote-cli"))
    server.start()
    yield server
    server.stop()


def _invoke(server_url: str, *arguments: str) -> Any:
    return runner.invoke(cli_app, ["--server", server_url, *arguments])


def _all_output(result: Any) -> str:
    try:
        stderr = result.stderr
    except (AttributeError, ValueError):
        stderr = ""
    return str(result.output) + str(stderr)


def _stdout_json(result: Any) -> dict[str, Any]:
    document = json.loads(result.output)
    assert isinstance(document, dict)
    return document


@pytest.fixture(scope="module")
def compiled_remote_case(
    live_server: _LiveServer, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    """Drive the full remote journey once per module and return its outputs."""

    tmp_path = tmp_path_factory.mktemp("remote-journey")
    designed = _invoke(live_server.url, "design", str(BRIEF_PATH), "--output", "json")
    assert designed.exit_code == 0, designed.output
    intent = _stdout_json(designed)
    assert intent["id"].startswith("intent.")

    questions = _invoke(live_server.url, "questions", CASE_ID, "--output", "json")
    assert questions.exit_code == 0, questions.output
    questions_document = _stdout_json(questions)
    assert questions_document["case_id"] == CASE_ID
    assert questions_document["status"] == "needs_confirmation"
    assert len(questions_document["questions"]) >= 1

    confirmed = _invoke(
        live_server.url,
        "confirm",
        CASE_ID,
        "--answers",
        str(ANSWERS_PATH),
        "--output",
        "json",
    )
    assert confirmed.exit_code == 0, confirmed.output
    assert _stdout_json(confirmed)["case"]["status"] == "ready_for_candidates"

    candidates = _invoke(live_server.url, "candidates", CASE_ID, "--output", "json")
    assert candidates.exit_code == 0, candidates.output
    candidates_document = _stdout_json(candidates)
    candidate_ids = {item["id"] for item in candidates_document["candidates"]}
    assert "candidate-03" in candidate_ids

    evaluated = _invoke(
        live_server.url,
        "evaluate",
        "candidate-03",
        "--case",
        CASE_ID,
        "--output",
        "json",
    )
    assert evaluated.exit_code == 0, evaluated.output
    assert _stdout_json(evaluated)["evaluation"]["status"] == "pass"

    rationale = tmp_path / "decision.md"
    rationale.write_text("balanced\n", encoding="utf-8")
    selected = _invoke(
        live_server.url,
        "select",
        "candidate-03",
        "--rationale-file",
        str(rationale),
        "--case",
        CASE_ID,
        "--output",
        "json",
    )
    assert selected.exit_code == 0, selected.output
    assert _stdout_json(selected)["case"]["status"] == "candidate_selected"

    assurance_directory = tmp_path / "assurance"
    assured = _invoke(
        live_server.url,
        "assure",
        "candidate-03",
        "--case",
        CASE_ID,
        "--output",
        str(assurance_directory),
    )
    assert assured.exit_code == 0, assured.output
    assert (assurance_directory / "assurance-plan.json").is_file()

    bundle_directory = tmp_path / "bundle"
    planned = _invoke(
        live_server.url,
        "plan",
        "candidate-03",
        "--case",
        CASE_ID,
        "--target",
        str(TARGET_PATH),
        "--output",
        str(bundle_directory),
    )
    assert planned.exit_code == 0, planned.output
    written = sorted(path.name for path in bundle_directory.iterdir())
    assert written == [
        "architecture-decision.json",
        "assurance-plan.json",
        "deployment-bundle.json",
        "runner-plan.json",
        "semantic-manifest.json",
    ]
    runner_plan = json.loads((bundle_directory / "runner-plan.json").read_text(encoding="utf-8"))
    serialized = json.dumps(runner_plan)
    assert '"command"' not in serialized and '"shell"' not in serialized
    assert runner_plan["status"] == "draft"

    final_case = live_server.control_plane.get_design_case(CASE_ID, tenant_id="local").case
    assert final_case["status"] == "bundle_compiled"
    assert final_case["version"] == "0.1.7"

    # The remote export interoperates with a plain local import.
    export_directory = tmp_path / "export"
    exported = _invoke(live_server.url, "export", CASE_ID, "--output", str(export_directory))
    assert exported.exit_code == 0, exported.output
    assert (export_directory / "manifest.json").is_file()
    assert (export_directory / "objects" / "sha256").is_dir()

    import_directory = tmp_path / "imported-workspace"
    imported_locally = runner.invoke(
        cli_app,
        [
            "import",
            str(export_directory),
            "--directory",
            str(import_directory),
            "--output",
            "json",
        ],
    )
    assert imported_locally.exit_code == 0, imported_locally.output
    imported_case = json.loads(imported_locally.output)["case"]
    assert imported_case["id"] == CASE_ID
    assert imported_case["version"] == "0.1.7"
    assert (
        imported_case["deployment_bundle_ref"]["digest"]
        == final_case["deployment_bundle_ref"]["digest"]
    )
    return {"final_case": final_case, "imported_case": imported_case}


def test_remote_journey_matches_local_semantics(
    compiled_remote_case: dict[str, Any],
) -> None:
    final_case = compiled_remote_case["final_case"]
    assert final_case["status"] == "bundle_compiled"
    assert final_case["version"] == "0.1.7"


def test_remote_state_denials_surface_the_stable_codes(
    live_server: _LiveServer, compiled_remote_case: dict[str, Any]
) -> None:
    # The module-scoped journey has already confirmed the case: with the default
    # derived idempotency key the retry converges on the original successor, the
    # same convergence the local CLI provides.
    replayed = _invoke(
        live_server.url,
        "confirm",
        CASE_ID,
        "--answers",
        str(ANSWERS_PATH),
        "--output",
        "json",
    )
    assert replayed.exit_code == 0, replayed.output
    assert _stdout_json(replayed)["duplicate"] is True

    # A fresh idempotency key is a new request, so the state machine denies it.
    confirmed_again = _invoke(
        live_server.url,
        "confirm",
        CASE_ID,
        "--answers",
        str(ANSWERS_PATH),
        "--idempotency-key",
        "confirm-remote-state-0001",
    )
    assert confirmed_again.exit_code == 2
    assert "OAK-CONFIRM-STATE" in _all_output(confirmed_again)

    generate_again = _invoke(live_server.url, "candidates", CASE_ID)
    assert generate_again.exit_code == 2
    assert "OAK-CANDIDATES-STATE" in _all_output(generate_again)

    unknown = _invoke(live_server.url, "questions", "design-case.absent")
    assert unknown.exit_code == 2
    assert "OAK-WORKSPACE-NOT-FOUND" in _all_output(unknown)
    assert "The requested resource was not found." in _all_output(unknown)


def test_local_only_commands_fail_closed_in_remote_mode(live_server: _LiveServer) -> None:
    for arguments in (
        ["init"],
        ["keys", "show"],
        ["sign"],
        ["approve", "dry_run"],
        ["revoke-approval", "dry_run", "--reason", "because"],
        ["dispatch", "inventory"],
        ["ingest"],
        ["gitops", "--output", "unused"],
        ["policy", "packs"],
        ["render", "--adapter", "renderer.local-manifests", "--output", "unused"],
        ["extensions", "list"],
    ):
        result = _invoke(live_server.url, *arguments)
        assert result.exit_code == 2, (arguments, result.output)
        assert "OAK-REMOTE-UNSUPPORTED" in _all_output(result), arguments


def test_remote_mode_requires_an_explicit_case(live_server: _LiveServer) -> None:
    result = _invoke(live_server.url, "questions")
    assert result.exit_code == 2
    assert "OAK-REMOTE-CASE-REQUIRED" in _all_output(result)


def test_unreachable_server_is_a_stable_retriable_error() -> None:
    result = _invoke("http://127.0.0.1:9", "questions", CASE_ID)
    assert result.exit_code == 2
    assert "OAK-REMOTE-UNAVAILABLE" in _all_output(result)


def test_non_http_server_url_is_refused() -> None:
    result = _invoke("ftp://127.0.0.1/x", "questions", CASE_ID)
    assert result.exit_code == 2
    assert "OAK-REMOTE-SERVER" in _all_output(result)
