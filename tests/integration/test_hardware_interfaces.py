# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-039: a scan result reaches a case through the CLI, REST and MCP, as a proposal."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
import yaml
from typer.testing import CliRunner

import oak.bootstrap
from oak.application import CommandContext
from oak.application.design_case import HARDWARE_PROPOSAL_EXTENSION
from oak.bootstrap import create_design_case_service
from oak.contracts import load_yaml_document
from oak.interfaces.api.app import create_app
from oak.interfaces.cli.main import app as cli_app
from tests.mcp_support import NOW, ROOT, MCPClient, build_server

pytestmark = pytest.mark.integration

BRIEF_PATH = ROOT / "examples/briefs/public-manual-qa.yaml"
ANSWERS_PATH = ROOT / "examples/briefs/public-manual-qa-answers.yaml"
CASE_ID = "design-case.public-manual-qa"
SCAN: dict[str, Any] = {
    "platform": {"operating_system": "linux", "architecture": "x86_64"},
    "cpu": {"model": "AMD EPYC 7763 64-Core Processor", "physical_cores": 8, "logical_cores": 16},
    "memory": {"ram_gib": 32.0, "unified": False},
    "storage_gib": 500.0,
    "accelerators": [
        {
            "vendor": "nvidia",
            "model": "NVIDIA GeForce RTX 4090",
            "memory_gib": 24.0,
            "unified_memory": False,
            "runtime": "cuda",
            "driver_version": "550.54.15",
        }
    ],
    "prerequisites": [{"name": "docker", "state": "present"}, {"name": "uv", "state": "absent"}],
    "unknown": [{"field": "accelerators.amd", "reason": "rocm-smi is not installed"}],
    "tools": [
        {"name": "lscpu", "status": "ran"},
        {"name": "nvidia-smi", "status": "ran"},
        {"name": "rocm-smi", "status": "absent"},
    ],
}
runner = CliRunner()


@pytest.fixture
def scanned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oak.bootstrap, "scan_hardware", lambda: json.loads(json.dumps(SCAN)))


def _ready_workspace(root: Path) -> None:
    def context(key: str, version: str | None) -> CommandContext:
        return CommandContext(
            actor="local-user",
            tenant_id="local",
            idempotency_key=f"hardware-cli-{key}-0001",
            expected_version=version,
            correlation_id=f"correlation-{key}",
            interface_origin="cli",
            occurred_at=NOW,
        )

    design = create_design_case_service(root)
    design.initialize(workspace_id="workspace.hardware-cli", tenant_id="local", created_at=NOW)
    design.design(BRIEF_PATH, context("design", None))
    answers = load_yaml_document(ANSWERS_PATH.read_text(encoding="utf-8"))
    design.confirm(answers, context("confirm", "0.1.1"))


def test_the_local_cli_proposes_then_confirms_a_scan(
    scanned: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    proposed = runner.invoke(cli_app, ["scan", "--propose", "--output", "json"])
    assert proposed.exit_code == 0, proposed.output
    document = json.loads(proposed.output)
    assert document["confirmed"] is False
    assert (
        document["case"]["extensions"][HARDWARE_PROPOSAL_EXTENSION]["id"]
        == (document["proposal_id"])
    )
    assert "vram_gib" not in document["intent"]["spec"]["hardware"]

    confirmed = runner.invoke(cli_app, ["scan", "--confirm"])
    assert confirmed.exit_code == 0, confirmed.output
    assert "now ready_for_candidates" in confirmed.output
    case = create_design_case_service(tmp_path).current()
    assert case.intent["spec"]["hardware"]["accelerators"] == ["nvidia-cuda"]
    assert case.intent["spec"]["hardware"]["vram_gib"] == 24.0


@pytest.mark.anyio
async def test_mcp_proposes_and_rest_confirms_on_one_control_plane(tmp_path: Path) -> None:
    server, control_plane, _store = build_server(tmp_path)
    client = MCPClient(server)
    created = client.call_ok(
        "oak_design_case_create",
        {
            "original_name": "public-manual-qa.yaml",
            "content": BRIEF_PATH.read_text(encoding="utf-8"),
            "idempotency_key": "hardware-mcp-create-0001",
        },
    )
    interpreted = client.call_ok(
        "oak_design_case_interpret",
        {
            "case_id": CASE_ID,
            "expected_version": str(created["case"]["version"]),
            "idempotency_key": "hardware-mcp-interpret-0001",
        },
    )
    confirmed = client.call_ok(
        "oak_claims_confirm",
        {
            "case_id": CASE_ID,
            "answers": yaml.safe_load(ANSWERS_PATH.read_text(encoding="utf-8")),
            "actor": "local-user",
            "expected_version": str(interpreted["case"]["version"]),
            "idempotency_key": "hardware-mcp-confirm-0001",
        },
    )

    proposed = client.call_ok(
        "oak_hardware_propose",
        {
            "case_id": CASE_ID,
            "scan": SCAN,
            "expected_version": str(confirmed["case"]["version"]),
            "idempotency_key": "hardware-mcp-propose-0001",
        },
    )
    reference = proposed["case"]["extensions"][HARDWARE_PROPOSAL_EXTENSION]
    assert proposed["intent"] == confirmed["intent"], "a proposal changes no intent value"

    transport = httpx.ASGITransport(app=create_app(control_plane=control_plane, clock=lambda: NOW))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as rest:
        answer = await rest.post(
            f"/v1/design-cases/{CASE_ID}:confirm-hardware",
            json={"proposal_id": reference["id"]},
            headers={
                "Idempotency-Key": "hardware-rest-confirm-0001",
                "If-Match": f'"{proposed["case"]["version"]}"',
            },
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["intent"]["spec"]["hardware"]["accelerators"] == ["nvidia-cuda"]

        late = await rest.post(
            f"/v1/design-cases/{CASE_ID}:propose-hardware",
            json={"scan": {**SCAN, "hostname": "laptop.local"}},
            headers={
                "Idempotency-Key": "hardware-rest-propose-0001",
                "If-Match": f'"{answer.json()["case"]["version"]}"',
            },
        )
        assert late.status_code == 422, late.text
        assert late.json()["code"] == "OAK-HARDWARE-PROPOSAL"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _LiveServer:
    def __init__(self, tmp_path: Path) -> None:
        _server, self.control_plane, _store = build_server(tmp_path)
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

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> _LiveServer:
        self.thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.url}/healthz", timeout=0.5):
                    return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the loopback API did not become healthy in time")

    def __exit__(self, *_: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[_LiveServer]:
    with _LiveServer(tmp_path) as server:
        yield server


def test_the_remote_cli_scans_here_and_confirms_on_the_server(
    scanned: None, live_server: _LiveServer
) -> None:
    def invoke(*arguments: str) -> Any:
        result = runner.invoke(cli_app, ["--server", live_server.url, *arguments])
        assert result.exit_code == 0, result.output
        return result

    invoke("design", str(BRIEF_PATH))
    invoke("confirm", CASE_ID, "--answers", str(ANSWERS_PATH))

    refused = runner.invoke(cli_app, ["--server", live_server.url, "scan", "--propose"])
    assert refused.exit_code == 2
    assert "OAK-REMOTE-CASE-REQUIRED" in refused.output + str(refused.stderr)

    result = invoke("scan", CASE_ID, "--confirm", "--output", "json")
    document = json.loads(result.output)
    assert document["confirmed"] is True
    assert document["case"]["status"] == "ready_for_candidates"
    assert document["intent"]["spec"]["hardware"]["vram_gib"] == 24.0
