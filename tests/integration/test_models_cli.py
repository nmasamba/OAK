# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-003: `oak models` never accepts a key as an argument and never prints one."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oak.interfaces.cli.main import app

pytestmark = pytest.mark.integration
KEY = "oak-test-key-openai-0123456789ab"
runner = CliRunner()


def _all_output(result: object) -> str:
    return str(getattr(result, "output", "")) + str(getattr(result, "stderr", "") or "")


def test_set_key_reads_stdin_stores_owner_only_and_echoes_only_a_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))

    result = runner.invoke(
        app, ["models", "set-key", "openai", "--store", "file", "--stdin"], input=KEY + "\n"
    )

    assert result.exit_code == 0, _all_output(result)
    assert KEY not in _all_output(result)
    assert "fingerprint" in result.output
    key_path = tmp_path / "credentials" / "openai.key"
    assert stat.S_IMODE(os.lstat(key_path).st_mode) == 0o600

    status = runner.invoke(app, ["models", "status", "--output", "json"])
    assert status.exit_code == 0
    document = json.loads(status.output)
    assert document["credentials"]["openai"]["configured"] is True
    assert KEY not in status.output
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.name != "openai.key":
            assert KEY not in path.read_text(encoding="utf-8", errors="ignore"), path

    removed = runner.invoke(app, ["models", "remove-key", "openai"])
    assert removed.exit_code == 0 and not key_path.exists()


def test_set_key_without_a_terminal_and_without_stdin_refuses() -> None:
    result = runner.invoke(app, ["models", "set-key", "openai", "--store", "file"])
    assert result.exit_code == 2
    assert "OAK-MODEL-KEY-INPUT" in _all_output(result)


def test_no_models_option_accepts_a_key_value() -> None:
    from typer.main import get_command

    command = get_command(app).commands["models"]  # type: ignore[attr-defined]
    for parameter in command.params:
        name = str(parameter.name).lower()
        assert not any(term in name for term in ("key", "secret", "token", "password")), name


def test_status_without_configuration_says_deterministic() -> None:
    result = runner.invoke(app, ["models", "status"])
    assert result.exit_code == 0
    assert "Deterministic interpretation" in result.output


def test_families_lists_the_seven_and_marks_the_default() -> None:
    result = runner.invoke(app, ["models", "families", "--output", "json"])
    assert result.exit_code == 0
    families = json.loads(result.output)["families"]
    assert [row["family"] for row in families] == [
        "huggingface",
        "openai",
        "anthropic",
        "gemini",
        "meta",
        "xai",
        "local",
    ]
    assert [row["family"] for row in families if row["default"]] == ["huggingface"]


def test_unknown_action_and_family_are_stable_refusals() -> None:
    action = runner.invoke(app, ["models", "frobnicate"])
    assert action.exit_code == 2 and "OAK-MODEL-ACTION" in _all_output(action)
    family = runner.invoke(app, ["models", "remove-key", "nope"])
    assert family.exit_code == 2 and "OAK-MODEL-FAMILY-UNKNOWN" in _all_output(family)
    missing = runner.invoke(app, ["models", "select"])
    assert missing.exit_code == 2 and "OAK-MODEL-FAMILY-REQUIRED" in _all_output(missing)
    token = runner.invoke(app, ["models", "token"])
    assert token.exit_code == 2 and "OAK-MODEL-TOKEN-MISSING" in _all_output(token)


def test_models_is_local_only() -> None:
    result = runner.invoke(app, ["--server", "http://127.0.0.1:9", "models", "status"])
    assert result.exit_code == 2
    assert "OAK-REMOTE-UNSUPPORTED" in _all_output(result)
