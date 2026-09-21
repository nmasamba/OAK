# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-003: the model configuration service never holds, prints or guesses a key."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.credentials import (
    EnvironmentCredentialReference,
    FileCredentialStore,
    ModelConfigurationFileStore,
)
from oak.application import ModelConfigurationService, validate_key_input
from oak.contracts import SchemaRegistry
from oak.domain import OAKError, SecretValue
from tools.check_repository import SECRET_PATTERNS

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-09-17T10:00:00Z"
KEY = "oak-test-key-huggingface-deadbeefcafe"


class _UnavailableKeychain:
    source = "keychain"

    def location(self) -> str:
        return "none"

    def set(self, family: str, secret: SecretValue) -> None:
        raise OAKError("OAK-MODEL-KEYCHAIN-UNAVAILABLE", "no keychain in tests")

    def get(self, family: str) -> SecretValue | None:
        raise OAKError("OAK-MODEL-KEYCHAIN-UNAVAILABLE", "no keychain in tests")

    def delete(self, family: str) -> bool:
        return False


def _service(tmp_path: Path, *, discoverer: Any = None) -> ModelConfigurationService:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    return ModelConfigurationService(
        ModelConfigurationFileStore(tmp_path / "models", registry),
        {
            "keychain": _UnavailableKeychain(),
            "file": FileCredentialStore(tmp_path / "credentials"),
            "env": EnvironmentCredentialReference(),
        },
        clock=lambda: NOW,
        discoverer=discoverer,
        token_reader=lambda: None,
        credentials_location=str(tmp_path / "credentials"),
    )


def test_key_input_is_bounded_and_trimmed_once() -> None:
    assert validate_key_input(KEY + "\n").reveal() == KEY
    assert validate_key_input(KEY + "\r\n").reveal() == KEY
    for bad in ("short", "a" * 513, "has space" + "x" * 20, "tab\t" + "x" * 20, "é" * 20):
        with pytest.raises(OAKError) as refusal:
            validate_key_input(bad)
        assert refusal.value.code == "OAK-MODEL-KEY-INPUT"


def test_status_before_anything_is_configured_is_deterministic(tmp_path: Path) -> None:
    service = _service(tmp_path)
    status = service.status()
    assert status["configured"] is False and status["selection"] is None
    assert all(not row["configured"] for row in status["credentials"].values())
    assert {row["family"] for row in service.families()} == {"huggingface", "local"}
    assert next(row for row in service.families() if row["default"])["family"] == "huggingface"


def test_set_key_writes_a_schema_valid_configuration_with_no_key_shape(tmp_path: Path) -> None:
    service = _service(tmp_path)
    status = service.set_key("huggingface", SecretValue(KEY), source="file")

    assert status.configured and status.source == "file" and status.length == len(KEY)
    assert status.fingerprint is not None and len(status.fingerprint) == 8
    configuration = tmp_path / "models" / "model-configuration.json"
    assert stat.S_IMODE(os.lstat(configuration).st_mode) == 0o600
    text = configuration.read_text(encoding="utf-8")
    assert KEY not in text and status.fingerprint not in text
    assert not any(pattern.search(text) for pattern in SECRET_PATTERNS)
    document = json.loads(text)
    assert document["credential_sources"] == {"huggingface": "file"}
    assert service.credential_for("huggingface") == SecretValue(KEY)
    assert KEY not in json.dumps(service.status())


def test_a_key_lives_in_exactly_one_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    service.set_key("huggingface", SecretValue(KEY), source="file")
    monkeypatch.setenv("OAK_MODEL_KEY_HUGGINGFACE", KEY + "2")
    service.set_key("huggingface", SecretValue(""), source="env")

    assert not (tmp_path / "credentials" / "huggingface.key").exists(), "the file copy was removed"
    assert service.credential_status("huggingface").source == "env"
    assert service.credential_for("huggingface") == SecretValue(KEY + "2")
    monkeypatch.delenv("OAK_MODEL_KEY_HUGGINGFACE")
    assert service.credential_status("huggingface").configured is False
    assert service.remove_key("huggingface") is True
    assert service.credential_status("huggingface").source is None


def test_select_requires_a_key_for_hosted_families_but_not_for_local(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(OAKError) as missing:
        service.select("huggingface", "openai/gpt-oss-120b")
    assert missing.value.code == "OAK-MODEL-KEY-MISSING"

    local = service.select("local", "llama3.2", default_interpreter="model")
    assert local.family == "local" and service.status()["configured"] is True

    service.set_key("huggingface", SecretValue(KEY), source="file")
    chosen = service.select("huggingface", "openai/gpt-oss-120b")
    assert chosen.model_id == "openai/gpt-oss-120b"
    assert service.status()["selection"]["family"] == "huggingface"
    service.clear_selection()
    assert service.status()["selection"] is None

    with pytest.raises(OAKError) as unknown:
        service.select("nope", "x")
    assert unknown.value.code == "OAK-MODEL-FAMILY-UNKNOWN"
    with pytest.raises(OAKError) as interpreter:
        service.select("local", "llama3.2", default_interpreter="chatty")
    assert interpreter.value.code == "OAK-MODEL-INTERPRETER"


def test_discovery_is_explicit_and_unavailable_without_a_discoverer(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(OAKError) as refusal:
        service.discover("huggingface")
    assert refusal.value.code == "OAK-MODEL-DISCOVERY-UNAVAILABLE"
    assert service.discovery_snapshot("huggingface") is None


def test_the_schema_has_no_property_that_could_hold_a_credential() -> None:
    schema = json.loads((ROOT / "schemas" / "model-configuration.schema.json").read_text())
    forbidden = {"api_key", "key", "secret", "token", "password", "credential"}

    def names(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    found |= set(value)
                found |= names(value)
        elif isinstance(node, list):
            for item in node:
                found |= names(item)
        return found

    assert not names(schema) & forbidden
