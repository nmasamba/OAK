# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-039: `oak scan` shows the proposal and the recommendations, and records nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import oak.bootstrap
from oak.interfaces.cli.main import app

PROPOSAL: dict[str, Any] = {
    "platform": {"operating_system": "macos", "architecture": "arm64"},
    "cpu": {"model": "Apple M1 Max", "physical_cores": 10, "logical_cores": 10},
    "memory": {"ram_gib": 64.0, "unified": True},
    "storage_gib": 926.4,
    "accelerators": [
        {
            "vendor": "apple",
            "model": "Apple M1 Max",
            "memory_gib": None,
            "unified_memory": True,
            "runtime": "metal",
            "driver_version": None,
        }
    ],
    "prerequisites": [{"name": "docker", "state": "absent"}, {"name": "uv", "state": "present"}],
    "unknown": [{"field": "accelerators.amd", "reason": "rocm-smi is not installed"}],
    "tools": [{"name": "sysctl", "status": "ran"}, {"name": "system_profiler", "status": "ran"}],
}


@pytest.fixture
def scanned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(oak.bootstrap, "scan_hardware", lambda: PROPOSAL)
    monkeypatch.chdir(tmp_path)


def test_scan_prints_the_proposal_and_what_is_missing(scanned: None, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["scan"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("Proposed hardware for this machine (nothing is recorded")
    assert "  CPU: Apple M1 Max, 10 cores (10 threads)" in lines
    assert "  Memory: 64 GiB, shared with the GPU" in lines
    assert "  GPU: Apple M1 Max (apple, metal), unified memory" in lines
    assert "  Unknown accelerators.amd: rocm-smi is not installed" in lines
    assert "Prerequisites: docker absent, uv present" in lines
    assert any("https://docs.docker.com/get-started/get-docker/" in line for line in lines)
    assert list(tmp_path.iterdir()) == [], "a scan writes nothing"


def test_scan_emits_the_proposal_as_json(scanned: None) -> None:
    result = CliRunner().invoke(app, ["scan", "--output", "json"])

    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["proposal"] == PROPOSAL
    assert len(document["recommendations"]) == 1
