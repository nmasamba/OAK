# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-003: provider keys are stored owner-only, never rendered, never guessed."""

from __future__ import annotations

import json
import os
import pickle
import stat
import sys
import types
from pathlib import Path

import pytest

from oak.adapters.credentials import (
    EnvironmentCredentialReference,
    FileCredentialStore,
    KeychainCredentialStore,
)
from oak.domain import REDACTED, OAKError, SecretValue

KEY = "oak-test-key-openai-0123456789ab"


def test_secret_value_never_renders_its_content() -> None:
    secret = SecretValue(KEY)
    assert repr(secret) == f"SecretValue({REDACTED})"
    assert str(secret) == REDACTED
    assert f"{secret}" == REDACTED
    assert format(secret, ">40") == REDACTED
    assert KEY not in f"{secret!r}{secret!s}{secret}"
    with pytest.raises(TypeError):
        json.dumps(secret)
    with pytest.raises(TypeError):
        pickle.dumps(secret)
    with pytest.raises(TypeError):
        hash(secret)
    assert secret == SecretValue(KEY)
    assert secret != SecretValue(KEY + "x")
    assert secret.reveal() == KEY
    assert len(secret) == len(KEY)
    assert not hasattr(secret, "__dict__")


def test_file_store_writes_owner_only_and_fingerprints_with_a_salt(tmp_path: Path) -> None:
    store = FileCredentialStore(tmp_path / "credentials")
    store.set("openai", SecretValue(KEY))

    key_path = tmp_path / "credentials" / "openai.key"
    assert stat.S_IMODE(os.lstat(tmp_path / "credentials").st_mode) == 0o700
    assert stat.S_IMODE(os.lstat(key_path).st_mode) == 0o600
    assert store.get("openai") == SecretValue(KEY)
    first = store.fingerprint(SecretValue(KEY))
    assert len(first) == 8 and first == store.fingerprint(SecretValue(KEY))
    assert first != store.fingerprint(SecretValue(KEY + "1"))
    other = FileCredentialStore(tmp_path / "other")
    assert other.fingerprint(SecretValue(KEY)) != first, "the fingerprint is salted per install"
    assert stat.S_IMODE(os.lstat(tmp_path / "credentials" / "fingerprint.salt").st_mode) == 0o600
    assert store.delete("openai") is True
    assert store.get("openai") is None
    assert store.delete("openai") is False


def test_file_store_refuses_loose_permissions_and_links(tmp_path: Path) -> None:
    store = FileCredentialStore(tmp_path / "credentials")
    store.set("openai", SecretValue(KEY))
    os.chmod(tmp_path / "credentials" / "openai.key", 0o644)
    with pytest.raises(OAKError) as loose:
        store.get("openai")
    assert loose.value.code == "OAK-MODEL-KEY-PERMISSIONS"
    assert KEY not in loose.value.message

    (tmp_path / "credentials" / "anthropic.key").symlink_to(tmp_path / "credentials" / "openai.key")
    with pytest.raises(OAKError) as linked:
        store.get("anthropic")
    assert linked.value.code == "OAK-MODEL-KEY-PERMISSIONS"


def test_environment_reference_stores_nothing_and_accepts_only_documented_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reference = EnvironmentCredentialReference()
    assert reference.get("openai") is None
    with pytest.raises(OAKError) as missing:
        reference.set("openai", SecretValue(""))
    assert missing.value.code == "OAK-MODEL-KEY-MISSING"

    monkeypatch.setenv("OAK_MODEL_KEY_OPENAI", KEY + "\n")
    reference.set("openai", SecretValue(""))
    assert reference.get("openai") == SecretValue(KEY)
    assert reference.delete("openai") is False
    assert not list(tmp_path.iterdir())

    with pytest.raises(OAKError) as undocumented:
        reference.variable_for("local")
    assert undocumented.value.code == "OAK-MODEL-CREDENTIAL-SOURCE"
    with pytest.raises(OAKError):
        reference.variable_for("OAK_DATABASE_URL")


def _fake_keyring(module_name: str, backend_module: str, storage: dict[str, str]) -> None:
    module = types.ModuleType(module_name)
    backend_type = type("Backend", (), {})
    backend_type.__module__ = backend_module

    def get_keyring() -> object:
        return backend_type()

    def set_password(service: str, username: str, password: str) -> None:
        storage[f"{service}/{username}"] = password

    def get_password(service: str, username: str) -> str | None:
        return storage.get(f"{service}/{username}")

    def delete_password(service: str, username: str) -> None:
        storage.pop(f"{service}/{username}")

    module.get_keyring = get_keyring  # type: ignore[attr-defined]
    module.set_password = set_password  # type: ignore[attr-defined]
    module.get_password = get_password  # type: ignore[attr-defined]
    module.delete_password = delete_password  # type: ignore[attr-defined]
    sys.modules[module_name] = module


def test_keychain_store_uses_the_service_and_account_convention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage: dict[str, str] = {}
    _fake_keyring("oak_test_keyring_ok", "keyring.backends.macOS", storage)
    monkeypatch.delitem(sys.modules, "oak_test_keyring_ok", raising=False)
    _fake_keyring("oak_test_keyring_ok", "keyring.backends.macOS", storage)
    store = KeychainCredentialStore("oak_test_keyring_ok")

    store.set("openai", SecretValue(KEY))
    assert storage == {"oak-community/openai": KEY}
    assert store.get("openai") == SecretValue(KEY)
    assert store.delete("openai") is True
    assert store.get("openai") is None
    assert store.delete("openai") is False


def test_keychain_store_refuses_plaintext_backends_and_reports_a_missing_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_keyring("oak_test_keyring_alt", "keyrings.alt.file", {})
    with pytest.raises(OAKError) as unsafe:
        KeychainCredentialStore("oak_test_keyring_alt").set("openai", SecretValue(KEY))
    assert unsafe.value.code == "OAK-MODEL-KEYCHAIN-UNSAFE"

    _fake_keyring("oak_test_keyring_fail", "keyring.backends.fail", {})
    with pytest.raises(OAKError) as failing:
        KeychainCredentialStore("oak_test_keyring_fail").get("openai")
    assert failing.value.code == "OAK-MODEL-KEYCHAIN-UNAVAILABLE"

    with pytest.raises(OAKError) as absent:
        KeychainCredentialStore("oak_test_keyring_not_installed").get("openai")
    assert absent.value.code == "OAK-MODEL-KEYCHAIN-UNAVAILABLE"
    assert "--store file" in absent.value.message
