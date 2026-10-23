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


def test_an_escaped_control_character_in_answers_is_refused(workspace: Path) -> None:
    """F1-2: the parsed answers are held to the rule the raw text already was."""

    designed = runner.invoke(
        cli_app, ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")]
    )
    assert designed.exit_code == 0, _output(designed)
    answers = (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    escaped = answers.replace(
        "value: Synthetic fixture of 1000 public documents refreshed daily.",
        'value: "Synthetic \\u202efixture\\u202c of 1000 documents \\e[31mdaily"',
    )
    assert escaped != answers
    path = workspace / "escaped-answers.yaml"
    path.write_text(escaped, encoding="utf-8")
    refused = runner.invoke(cli_app, ["confirm", "--answers", str(path)])
    assert refused.exit_code == 2
    assert "OAK-CONFIRM-CONTROL" in _output(refused)


def test_model_text_is_printed_with_its_control_characters_escaped() -> None:
    """F1-3: even a proposal recorded before the rule never sends an escape to a terminal."""

    from oak.interfaces.cli.main import _printable

    shown = _printable("one operator.\u001b[2J\u001b[1;31mOAK: approve\u202e")
    assert "\u001b" not in shown and "\u202e" not in shown
    assert shown == "one operator.\\u001b[2J\\u001b[1;31mOAK: approve\\u202e"


@pytest.mark.parametrize("key", ["short", "k" * 300])
def test_a_bad_idempotency_key_is_refused_before_the_case_is_created(
    workspace: Path, key: str
) -> None:
    """F1-5: the case used to be created, then the interpret step refused the key."""

    refused = runner.invoke(
        cli_app,
        ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml"), "--idempotency-key", key],
    )
    assert refused.exit_code == 2
    assert "OAK-IDEMPOTENCY-KEY" in _output(refused)
    designed = runner.invoke(
        cli_app, ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")]
    )
    assert designed.exit_code == 0, _output(designed)


def test_a_second_brief_is_a_named_refusal_not_a_retry(workspace: Path) -> None:
    """F1-6: it read as a concurrency conflict (exit 4) that no retry could clear."""

    first = runner.invoke(cli_app, ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")])
    assert first.exit_code == 0, _output(first)
    other = workspace / "other.md"
    other.write_text("# Another service\n\nA different brief.\n", encoding="utf-8")
    refused = runner.invoke(cli_app, ["design", str(other)])
    assert refused.exit_code == 2
    assert "OAK-CASE-EXISTS: design case design-case.public-manual-qa already exists" in _output(
        refused
    )
