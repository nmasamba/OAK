# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005: what the local CLI says about the paths a person gives it.

A mistyped input file keeps its stable code but says it does not exist, rather than
reading like a security refusal (walkthrough V-4); and a destination is printed
normalised (walkthrough W-3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def _output(result: object) -> str:
    return str(getattr(result, "output", "")) + str(getattr(result, "stderr", "") or "")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.chdir(tmp_path)
    initialised = runner.invoke(cli_app, ["init", "ws"])
    assert initialised.exit_code == 0, _output(initialised)
    root = tmp_path / "ws"
    monkeypatch.chdir(root)
    return root


def test_a_missing_brief_or_answers_file_says_it_does_not_exist(workspace: Path) -> None:
    brief = runner.invoke(cli_app, ["design", "no-such-brief.yaml"])
    assert brief.exit_code == 2
    assert "OAK-INTAKE-UNSAFE-PATH: brief file does not exist: no-such-brief.yaml" in _output(brief)

    designed = runner.invoke(
        cli_app, ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")]
    )
    assert designed.exit_code == 0, _output(designed)
    answers = runner.invoke(cli_app, ["confirm", "--answers", "no-such-answers.yaml"])
    assert answers.exit_code == 2
    assert "OAK-CONFIRM-UNSAFE-PATH: input file does not exist: no-such-answers.yaml" in _output(
        answers
    )


def test_an_import_prints_its_destination_normalised(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    designed = runner.invoke(
        cli_app, ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")]
    )
    assert designed.exit_code == 0, _output(designed)
    exported = runner.invoke(cli_app, ["export", "--output", str(tmp_path / "export")])
    assert exported.exit_code == 0, _output(exported)

    imported = runner.invoke(
        cli_app, ["import", str(tmp_path / "export"), "--directory", "../restored"]
    )

    assert imported.exit_code == 0, _output(imported)
    assert f"into {tmp_path / 'restored'}" in imported.output
    assert "/../" not in imported.output
