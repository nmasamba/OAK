# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-003: `oak models` never accepts a key as an argument and never prints one."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

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
        app, ["models", "set-key", "huggingface", "--store", "file", "--stdin"], input=KEY + "\n"
    )

    assert result.exit_code == 0, _all_output(result)
    assert KEY not in _all_output(result)
    assert "fingerprint" in result.output
    key_path = tmp_path / "credentials" / "huggingface.key"
    assert stat.S_IMODE(os.lstat(key_path).st_mode) == 0o600

    status = runner.invoke(app, ["models", "status", "--output", "json"])
    assert status.exit_code == 0
    document = json.loads(status.output)
    assert document["credentials"]["huggingface"]["configured"] is True
    assert KEY not in status.output
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.name != "huggingface.key":
            assert KEY not in path.read_text(encoding="utf-8", errors="ignore"), path

    removed = runner.invoke(app, ["models", "remove-key", "huggingface"])
    assert removed.exit_code == 0 and not key_path.exists()


def test_set_key_without_a_terminal_and_without_stdin_refuses() -> None:
    result = runner.invoke(app, ["models", "set-key", "huggingface", "--store", "file"])
    assert result.exit_code == 2
    assert "OAK-MODEL-KEY-INPUT" in _all_output(result)


def test_no_models_option_accepts_a_key_value() -> None:
    from typer.main import get_command

    command = get_command(app).commands["models"]  # type: ignore[attr-defined]
    for parameter in command.params:
        name = str(parameter.name).lower()
        assert not any(term in name for term in ("key", "secret", "token", "password")), name


def test_status_without_configuration_says_only_deterministic_is_ready() -> None:
    result = runner.invoke(app, ["models", "status"])
    assert result.exit_code == 0
    assert "deterministic: ready" in result.output
    assert "online: not ready" in result.output and "oak models set-key" in result.output
    assert "local: not ready" in result.output and "oak models select local" in result.output


def test_a_local_model_can_be_pinned_and_cleared_and_status_follows() -> None:
    pinned = runner.invoke(app, ["models", "select", "local", "qwen3:8b", "--output", "json"])
    assert pinned.exit_code == 0, _all_output(pinned)
    assert json.loads(pinned.output) == {
        "family": "local",
        "model_id": "qwen3:8b",
        "provider_route": None,
        "selected_at": json.loads(pinned.output)["selected_at"],
    }
    status = runner.invoke(app, ["models", "status"])
    assert "local: ready — qwen3:8b on http://127.0.0.1:11434/v1" in status.output

    route = runner.invoke(app, ["models", "select", "local", "qwen3:8b", "--provider", "x"])
    assert route.exit_code == 2 and "OAK-MODEL-ROUTE" in _all_output(route)

    cleared = runner.invoke(app, ["models", "clear", "local"])
    assert cleared.exit_code == 0 and "Cleared the pinned local model" in cleared.output
    again = runner.invoke(app, ["models", "clear", "local"])
    assert again.exit_code == 0 and "No local model was pinned" in again.output
    assert "local: not ready" in runner.invoke(app, ["models", "status"]).output


def test_families_lists_hugging_face_and_local_and_marks_the_default() -> None:
    result = runner.invoke(app, ["models", "families", "--output", "json"])
    assert result.exit_code == 0
    families = json.loads(result.output)["families"]
    assert [row["family"] for row in families] == ["huggingface", "local"]
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


# ----- OAK-S10-004: set-key verifies by default, and says so -------------------------------


def _accepting_verifier(asked: list[str]) -> Any:
    def verifier(family: str, *, deadline_seconds: float | None = None) -> dict[str, Any]:
        asked.append(family)
        return {
            "verdict": "accepted",
            "method": "hub_whoami_v2",
            "token_role": "read",
            "inference_permission": True,
            "can_pay": False,
            "is_pro": False,
            "reason": None,
        }

    return verifier


def test_set_key_verifies_by_default_prints_what_it_does_and_no_verify_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from oak import bootstrap

    asked: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _accepting_verifier(asked))

    stored = runner.invoke(
        app, ["models", "set-key", "--store", "file", "--stdin"], input=KEY + "\n"
    )
    assert stored.exit_code == 0, _all_output(stored)
    assert "Stored the huggingface key" in stored.output
    assert "Verifying with Hugging Face" in stored.output
    assert "nothing is generated" in stored.output
    assert "Hugging Face accepted the credential at" in stored.output
    assert "read token" in stored.output and "account can pay: no" in stored.output
    assert KEY not in _all_output(stored)
    assert asked == ["huggingface"]

    quiet = runner.invoke(
        app, ["models", "set-key", "--store", "file", "--stdin", "--no-verify"], input=KEY + "\n"
    )
    assert quiet.exit_code == 0, _all_output(quiet)
    assert "Verifying" not in quiet.output
    assert asked == ["huggingface"], "--no-verify sends nothing"
    status = runner.invoke(app, ["models", "status"])
    assert "accepted" not in status.output, "a re-stored key is unverified again"

    again = runner.invoke(app, ["models", "verify"])
    assert again.exit_code == 0, _all_output(again)
    assert asked == ["huggingface", "huggingface"]
    assert "accepted the credential at" in again.output
    status = runner.invoke(app, ["models", "status"])
    assert "Hugging Face accepted the credential at" in status.output


def test_verify_without_a_key_refuses_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from oak import bootstrap

    asked: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _accepting_verifier(asked))
    result = runner.invoke(app, ["models", "verify"])
    assert result.exit_code == 2 and "OAK-MODEL-KEY-MISSING" in _all_output(result)
    assert asked == []
