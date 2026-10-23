# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-004: `oak research`, against a local workspace and against a server.

`--plan` prints the hosts and terms and sends nothing; `--consent <digest>` runs the
research (here through the fixture source, selected by `OAK_RESEARCH_FIXTURES`); `review`
records a decision with a rationale from a file, never a flag with no reason; and the
remote mode maps each onto the REST routes, passing the capability token from
`OAK_MODEL_TOKEN` as `oak report --narrative` does. The CLI never prompts.
"""

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

FIXTURES = ROOT / "tests/fixtures/research/e2e"
TOKEN = "research-cli-token-0123456789ab"
HARNESS = "research.item.github.fixture-forge.fixturelm-serve"
runner = CliRunner()
pytestmark = pytest.mark.integration


def _output(result: Any) -> str:
    return result.output + (result.stderr if hasattr(result, "stderr") else "")


def _ready_workspace(tmp_path: Path) -> Path:
    """The reference case stopped at `ready_for_candidates` (after the confirmation)."""

    from oak.bootstrap import create_design_case_service
    from oak.contracts import load_yaml_document
    from tests.runner_support import _context, _stamp

    stamp = _stamp(0)
    workspace = tmp_path / "workspace"
    design = create_design_case_service(workspace)
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=stamp)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(stamp, "harness-design-000001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context(stamp, "harness-confirm-000001", "0.1.1"))
    return workspace


def test_the_local_cli_plans_runs_reviews_and_generates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _ready_workspace(tmp_path)
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("OAK_ACTOR", raising=False)
    monkeypatch.setenv("OAK_RESEARCH_FIXTURES", str(FIXTURES))

    usage = runner.invoke(cli_app, ["research"])
    assert usage.exit_code == 2 and "OAK-RESEARCH-USAGE" in _output(usage)

    planned = runner.invoke(cli_app, ["research", "--plan", "--output", "json"])
    assert planned.exit_code == 0, _output(planned)
    plan = json.loads(planned.output)
    assert plan["source_mode"] == "fixture" and plan["hosts"] == [] and plan["allowed"] is True
    human = runner.invoke(cli_app, ["research", "--plan"])
    assert "Terms digest: " + plan["terms_digest"] in human.output
    assert "oak research --consent" in human.output

    wrong = runner.invoke(cli_app, ["research", "--consent", "sha256:" + "0" * 64])
    assert wrong.exit_code == 2 and "OAK-RESEARCH-CONSENT" in _output(wrong)

    ran = runner.invoke(
        cli_app, ["research", "--consent", plan["terms_digest"], "--output", "json"]
    )
    assert ran.exit_code == 0, _output(ran)
    result = json.loads(ran.output)
    assert result["snapshot"]["summary"] == {
        "found": 2,
        "passed": 1,
        "needs_review": 1,
        "failed": 0,
    }
    assert result["case"]["version"] == "0.1.3"
    listing = runner.invoke(cli_app, ["research", "--consent", plan["terms_digest"]])
    assert "need review 1" in listing.output

    rationale = tmp_path / "why.txt"
    rationale.write_text("Read the repository by hand.\n", encoding="utf-8")
    no_decision = runner.invoke(
        cli_app, ["research", "review", HARNESS, "--rationale-file", str(rationale)]
    )
    assert no_decision.exit_code == 2 and "OAK-RESEARCH-USAGE" in _output(no_decision)
    no_file = runner.invoke(cli_app, ["research", "review", HARNESS, "--accept"])
    assert no_file.exit_code == 2 and "OAK-RESEARCH-USAGE" in _output(no_file)
    reviewed = runner.invoke(
        cli_app, ["research", "review", HARNESS, "--accept", "--rationale-file", str(rationale)]
    )
    assert reviewed.exit_code == 0, _output(reviewed)
    assert "Recorded accept" in reviewed.output and "0.1.5" in reviewed.output

    generated = runner.invoke(cli_app, ["candidates", "--output", "json"])
    assert generated.exit_code == 0, _output(generated)
    ids = [item["id"] for item in json.loads(generated.output)["candidates"]]
    assert ids == [
        "candidate-00",
        "candidate-01",
        "candidate-03",
        "candidate-04",
        "candidate-05",
        "candidate-06",
    ]

    late = runner.invoke(cli_app, ["research", "--plan", "--output", "json"])
    assert json.loads(late.output)["allowed"] is False


class _LiveServer:
    def __init__(self, tmp_path: Path) -> None:
        self.control_plane, self.store = build_file_control_plane(tmp_path)
        application = create_app(
            control_plane=self.control_plane, clock=lambda: NOW, model_token=TOKEN
        )
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
        self.stop_draining = threading.Event()
        self.drainer = threading.Thread(target=self._drain, daemon=True)

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

    def _drain(self) -> None:
        while not self.stop_draining.is_set():
            drain_operations(self.control_plane, self.store)
            time.sleep(0.05)


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_LiveServer]:
    server = _LiveServer(tmp_path_factory.mktemp("research-remote"))
    server.start()
    yield server
    server.stop()


def _remote(server: _LiveServer, *arguments: str) -> Any:
    return runner.invoke(cli_app, ["--server", server.url, *arguments])


def test_the_remote_cli_plans_runs_with_the_token_reviews_and_generates(
    live_server: _LiveServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_MODEL_TOKEN", raising=False)
    brief = ROOT / "examples/briefs/public-manual-qa.yaml"
    answers = ROOT / "examples/briefs/public-manual-qa-answers.yaml"
    designed = _remote(live_server, "design", str(brief))
    assert designed.exit_code == 0, _output(designed)
    case_id = "design-case.public-manual-qa"
    confirmed = _remote(
        live_server, "confirm", case_id, "--answers", str(answers), "--output", "json"
    )
    assert confirmed.exit_code == 0, _output(confirmed)

    planned = _remote(live_server, "research", "--plan", "--case", case_id, "--output", "json")
    assert planned.exit_code == 0, _output(planned)
    plan = json.loads(planned.output)

    without_token = _remote(
        live_server, "research", "--consent", plan["terms_digest"], "--case", case_id
    )
    assert without_token.exit_code == 2 and "OAK-MODEL-TOKEN-REQUIRED" in _output(without_token)

    monkeypatch.setenv("OAK_MODEL_TOKEN", TOKEN)
    ran = _remote(
        live_server,
        "research",
        "--consent",
        plan["terms_digest"],
        "--case",
        case_id,
        "--output",
        "json",
    )
    assert ran.exit_code == 0, _output(ran)
    assert json.loads(ran.output)["snapshot"]["summary"]["needs_review"] == 1

    rationale = tmp_path / "why.txt"
    rationale.write_text("Read it by hand.", encoding="utf-8")
    reviewed = _remote(
        live_server,
        "research",
        "review",
        HARNESS,
        "--accept",
        "--rationale-file",
        str(rationale),
        "--case",
        case_id,
    )
    assert reviewed.exit_code == 0, _output(reviewed)
    assert "Recorded accept" in reviewed.output

    generated = _remote(live_server, "candidates", case_id, "--output", "json")
    assert generated.exit_code == 0, _output(generated)
    ids = [item["id"] for item in json.loads(generated.output)["candidates"]]
    assert "candidate-05" in ids and "candidate-06" in ids


def test_the_plan_offers_the_consent_command_only_when_research_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OAK-V1-005 (walkthrough V-2): before the questions are confirmed the plan is still a
    read, but it does not offer a `--consent` command it would refuse."""

    from oak.bootstrap import create_design_case_service
    from tests.runner_support import _context, _stamp

    workspace = tmp_path / "workspace"
    design = create_design_case_service(workspace)
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=_stamp(0))
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(_stamp(0), "harness-design-000001", None),
    )
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("OAK_RESEARCH_FIXTURES", str(FIXTURES))

    human = runner.invoke(cli_app, ["research", "--plan"])

    assert human.exit_code == 0, _output(human)
    assert "not allowed at this status" in human.output
    assert "oak research --consent" not in human.output
    assert "Research runs only while the case is ready_for_candidates" in human.output
