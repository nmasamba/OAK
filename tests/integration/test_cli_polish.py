# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005: the local and remote CLI's rough edges the 1.0 review found (F1-13, F1-17,
F1-19, F1-20)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from oak.domain import OAKError
from oak.interfaces.cli import remote as remote_mode
from oak.interfaces.cli.main import OutputFormat, _abort, _remote_design
from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("index", [5, None, "entries"])
def test_a_remote_import_with_a_malformed_index_is_refused_not_a_traceback(
    tmp_path: Path, index: Any
) -> None:
    """F1-13: a null or numeric index raised TypeError before any request."""

    (tmp_path / "manifest.json").write_text(json.dumps({"artifact_index": index}))
    with pytest.raises(OAKError) as refused:
        remote_mode.read_export_directory(tmp_path)
    assert refused.value.code == "OAK-IMPORT-INVALID"


def test_the_research_plan_refuses_another_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1-17: the plan of the current case was printed for any --case."""

    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(cli_app, ["init", "ws"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "ws")
    brief = str(ROOT / "examples/briefs/public-manual-qa.yaml")
    assert runner.invoke(cli_app, ["design", brief]).exit_code == 0
    refused = runner.invoke(cli_app, ["research", "--plan", "--case", "design-case.does-not-exist"])
    assert refused.exit_code == 2
    assert "OAK-CASE-NOT-FOUND" in refused.output + str(refused.stderr or "")


def test_a_closed_pipe_stops_quietly(capsys: pytest.CaptureFixture[str]) -> None:
    """F1-19: `oak report | head` printed OAK-INPUT-INVALID."""

    with pytest.raises(typer.Exit) as stopped:
        _abort(BrokenPipeError())
    assert stopped.value.exit_code == 141
    assert "OAK-" not in capsys.readouterr().err


class _NoRemote:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError("nothing may be sent for an unreadable brief")


def test_a_remote_brief_that_is_not_utf8_is_the_intake_refusal(tmp_path: Path) -> None:
    """F1-20: remote mode said OAK-INPUT-INVALID where local mode said why."""

    brief = tmp_path / "latin1.md"
    brief.write_bytes("Café brief\n".encode("latin-1"))
    with pytest.raises(OAKError) as refused:
        _remote_design(_NoRemote(), brief, None, OutputFormat.HUMAN, "deterministic")  # type: ignore[arg-type]
    assert refused.value.code == "OAK-INTAKE-ENCODING"


def test_a_failed_remote_operation_carries_the_servers_own_message() -> None:
    """F1-20: every remote failure read 'the remote operation failed'."""

    client = remote_mode.RemoteClient.__new__(remote_mode.RemoteClient)
    client.get_operation = lambda operation_id: {  # type: ignore[method-assign]
        "state": "failed",
        "problem": {
            "code": "OAK-CANDIDATES-STATE",
            "message": "candidates require a case that is ready for candidates",
            "retriable": False,
        },
    }
    with pytest.raises(OAKError) as failed:
        client.wait_for_operation("operation.x")
    assert failed.value.code == "OAK-CANDIDATES-STATE"
    assert failed.value.message == "candidates require a case that is ready for candidates"
