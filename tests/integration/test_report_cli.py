# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-004: `oak report`, against a local workspace and against a server.

Recording is explicit (`--record`). Reading writes the recorded bytes only after checking
them against the digest the case names, and says when the case has moved on since.
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

from oak.bootstrap import create_candidate_planning_service
from oak.domain import content_digest
from oak.interfaces.api.app import create_app
from oak.interfaces.cli.main import app as cli_app
from tests.mcp_support import NOW, ROOT, build_file_control_plane, drain_operations
from tests.report_pdf_support import parse_pdf
from tests.report_support import FIXED_CLOCK, build_reference_case
from tests.runner_support import _context

pytestmark = pytest.mark.integration
runner = CliRunner()
CASE_ID = "design-case.public-manual-qa"


def _output(result: Any) -> str:
    try:
        stderr = result.stderr
    except (AttributeError, ValueError):
        stderr = ""
    return str(result.output) + str(stderr)


def _case(workspace: Path) -> dict[str, Any]:
    manifest = json.loads((workspace / ".oak" / "manifest.json").read_text(encoding="utf-8"))
    digest = manifest["current_case_ref"]["digest"].removeprefix("sha256:")
    return dict(json.loads((workspace / ".oak" / "objects" / "sha256" / digest).read_bytes()))


def test_the_local_cli_records_reads_and_flags_a_stale_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = build_reference_case(tmp_path, "candidate_selected")
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("OAK_ACTOR", raising=False)

    missing = runner.invoke(cli_app, ["report"])
    assert missing.exit_code == 2
    assert "OAK-REPORT-MISSING" in _output(missing)

    no_file = runner.invoke(cli_app, ["report", "--format", "pdf"])
    assert no_file.exit_code == 2
    assert "OAK-REPORT-OUTPUT" in _output(no_file)

    pdf_path = tmp_path / "report.pdf"
    recorded = runner.invoke(
        cli_app, ["report", "--record", "--format", "pdf", "--output", str(pdf_path)]
    )
    assert recorded.exit_code == 0, _output(recorded)
    entry = _case(workspace)["extensions"]["oak.community/report"]
    assert entry["made_from_case_version"] == "0.1.5"
    assert "digest matches" in recorded.output
    assert content_digest(pdf_path.read_bytes()) == entry["pdf_ref"]["digest"]
    assert len(parse_pdf(pdf_path.read_bytes()).pages) > 20

    document = runner.invoke(cli_app, ["report"])
    assert document.exit_code == 0
    assert json.loads(document.output)["id"] == "report.public-manual-qa.from-0.1.5"
    assert "moved on" not in _output(document)

    create_candidate_planning_service(workspace).assure(
        "candidate-03", _context(FIXED_CLOCK, "report-cli-assure-0001", "0.1.6")
    )
    stale = runner.invoke(cli_app, ["report", "--output", str(tmp_path / "report.json")])
    assert stale.exit_code == 0
    assert "The case moved on since this report" in _output(stale)
    assert (
        content_digest((tmp_path / "report.json").read_bytes()) == entry["document_ref"]["digest"]
    )


class _LiveServer:
    def __init__(self, tmp_path: Path) -> None:
        self.control_plane, self.store = build_file_control_plane(tmp_path)
        application = create_app(control_plane=self.control_plane, clock=lambda: NOW)
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
    server = _LiveServer(tmp_path_factory.mktemp("report-remote"))
    server.start()
    yield server
    server.stop()


def _remote(server: _LiveServer, *arguments: str) -> Any:
    return runner.invoke(cli_app, ["--server", server.url, *arguments])


def test_the_remote_cli_records_and_downloads_verified_files(
    live_server: _LiveServer, tmp_path: Path
) -> None:
    rationale = tmp_path / "rationale.txt"
    rationale.write_text("balanced", encoding="utf-8")
    steps = [
        ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")],
        [
            "confirm",
            CASE_ID,
            "--answers",
            str(ROOT / "examples/briefs/public-manual-qa-answers.yaml"),
        ],
        ["candidates", CASE_ID],
        ["evaluate", "candidate-03", "--case", CASE_ID],
        ["select", "candidate-03", "--case", CASE_ID, "--rationale-file", str(rationale)],
    ]
    for step in steps:
        result = _remote(live_server, *step)
        assert result.exit_code == 0, (step, _output(result))

    without_case = _remote(live_server, "report", "--record")
    assert without_case.exit_code == 2
    assert "OAK-REMOTE-CASE-REQUIRED" in _output(without_case)

    pdf_path = tmp_path / "remote.pdf"
    recorded = _remote(
        live_server,
        "report",
        "--case",
        CASE_ID,
        "--record",
        "--format",
        "pdf",
        "--output",
        str(pdf_path),
    )
    assert recorded.exit_code == 0, _output(recorded)
    assert "digest matches" in recorded.output
    case = live_server.control_plane.get_design_case(CASE_ID, tenant_id="local").case
    entry = case["extensions"]["oak.community/report"]
    assert entry["recorded_case_version"] == case["version"]
    assert content_digest(pdf_path.read_bytes()) == entry["pdf_ref"]["digest"]

    document = _remote(live_server, "report", "--case", CASE_ID)
    assert document.exit_code == 0, _output(document)
    assert json.loads(document.output)["case_ref"]["version"] == entry["made_from_case_version"]
