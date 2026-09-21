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


def _service(
    tmp_path: Path,
    *,
    discoverer: Any = None,
    route_chooser: Any = None,
    verifier: Any = None,
    clock: Any = None,
    verification_stale_seconds: int = 86_400,
) -> ModelConfigurationService:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    return ModelConfigurationService(
        ModelConfigurationFileStore(tmp_path / "models", registry),
        {
            "keychain": _UnavailableKeychain(),
            "file": FileCredentialStore(tmp_path / "credentials"),
            "env": EnvironmentCredentialReference(),
        },
        clock=clock or (lambda: NOW),
        discoverer=discoverer,
        verifier=verifier,
        route_chooser=route_chooser,
        token_reader=lambda: None,
        credentials_location=str(tmp_path / "credentials"),
        verification_stale_seconds=verification_stale_seconds,
    )


ACCEPTED = {
    "verdict": "accepted",
    "method": "hub_whoami_v2",
    "token_role": "read",
    "inference_permission": True,
    "can_pay": False,
    "is_pro": False,
    "reason": None,
    "name": "sentinel-account-name-MUST-NOT-BE-STORED",
    "email": "sentinel.address.MUST-NOT-BE-STORED@example.invalid",
}


SNAPSHOT = {
    "fetched_at": NOW,
    "source": "live",
    "recommended": "Qwen/Qwen3.8-27B",
    "filtered_out_count": 0,
    "models": [
        {
            "id": "Qwen/Qwen3.8-27B",
            "display_name": "Qwen/Qwen3.8-27B",
            "created": None,
            "licence": "apache-2.0",
            "data_use": "unknown",
            "providers": [
                {
                    "provider": "cerebras",
                    "supports_structured_output": True,
                    "output_price_per_million": 1.49,
                },
                {
                    "provider": "nscale",
                    "supports_structured_output": False,
                    "output_price_per_million": 0.2,
                },
            ],
        },
        {
            "id": "Qwen/Qwen3-8B",
            "display_name": "Qwen/Qwen3-8B",
            "created": None,
            "licence": "apache-2.0",
            "data_use": "unknown",
            "providers": [
                {
                    "provider": "novita",
                    "supports_structured_output": False,
                    "output_price_per_million": 0.1,
                }
            ],
        },
    ],
}


def _first_capable(listed: dict[str, Any] | None, policy: str) -> str | None:
    if listed is None:
        return None
    for route in listed.get("providers", []):
        if route.get("supports_structured_output"):
            return str(route["provider"])
    return None


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
    assert status["modes"]["online"]["available"] is False
    assert status["modes"]["local"]["available"] is False
    assert status["modes"]["deterministic"]["available"] is True
    assert status["selections"] == {"huggingface": None, "local": None}
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

    local = service.select("local", "llama3.2")
    assert local.family == "local" and local.provider_route is None
    assert service.status()["modes"]["local"]["available"] is True
    assert service.status()["modes"]["local"]["model_id"] == "llama3.2"

    service.set_key("huggingface", SecretValue(KEY), source="file")
    chosen = service.select("huggingface", "openai/gpt-oss-120b")
    assert chosen.model_id == "openai/gpt-oss-120b"
    status = service.status()
    assert status["selections"]["huggingface"]["model_id"] == "openai/gpt-oss-120b"
    assert status["selections"]["local"]["model_id"] == "llama3.2", "one pin per family"
    assert status["modes"]["online"]["pair"]["source"] == "pinned"
    assert service.clear_selection("huggingface") is True
    assert service.clear_selection("huggingface") is False
    assert service.status()["selections"]["huggingface"] is None
    assert service.status()["selections"]["local"]["model_id"] == "llama3.2"

    with pytest.raises(OAKError) as unknown:
        service.select("nope", "x")
    assert unknown.value.code == "OAK-MODEL-FAMILY-UNKNOWN"
    with pytest.raises(OAKError) as route:
        service.select("local", "llama3.2", provider_route="cerebras")
    assert route.value.code == "OAK-MODEL-ROUTE"


def test_online_ai_uses_the_pinned_pair_else_the_preferred_model(tmp_path: Path) -> None:
    service = _service(
        tmp_path, discoverer=lambda family, previous: SNAPSHOT, route_chooser=_first_capable
    )
    assert service.online_pair() is None, "nothing to call before a catalogue or a pin"

    service.set_key("huggingface", SecretValue(KEY), source="file")
    service.discover("huggingface")
    preferred = service.online_pair()
    assert preferred == {
        "model_id": "Qwen/Qwen3.8-27B",
        "provider_route": "cerebras",
        "source": "preferred",
        "resolved_at": NOW,
        "licence": "apache-2.0",
        "output_price_per_million": 1.49,
    }
    assert service.status()["modes"]["online"]["available"] is True

    # A pinned pair wins, and a route the catalogue lists as structured-output-capable is
    # kept; the price shown is that route's.
    service.select("huggingface", "Qwen/Qwen3.8-27B", provider_route="cerebras")
    pinned = service.online_pair()
    assert pinned is not None and pinned["source"] == "pinned"
    assert pinned["provider_route"] == "cerebras" and pinned["resolved_at"] == NOW

    # A model the catalogue does not know can still be pinned: the router decides.
    unknown = service.select("huggingface", "openai/gpt-oss-20b")
    assert unknown.provider_route is None
    assert service.online_pair() == {
        "model_id": "openai/gpt-oss-20b",
        "provider_route": None,
        "source": "pinned",
        "resolved_at": NOW,
        "licence": None,
        "output_price_per_million": None,
    }


def test_a_pinned_pair_must_be_able_to_answer_with_structured_output(tmp_path: Path) -> None:
    service = _service(tmp_path, discoverer=lambda family, previous: SNAPSHOT)
    service.set_key("huggingface", SecretValue(KEY), source="file")
    service.discover("huggingface")

    with pytest.raises(OAKError) as no_route:
        service.select("huggingface", "Qwen/Qwen3-8B")
    assert no_route.value.code == "OAK-MODEL-ROUTE"
    assert "structured output" in no_route.value.message

    with pytest.raises(OAKError) as wrong_route:
        service.select("huggingface", "Qwen/Qwen3.8-27B", provider_route="nscale")
    assert wrong_route.value.code == "OAK-MODEL-ROUTE"
    assert "cerebras" in wrong_route.value.message
    assert service.selection("huggingface") is None, "a refused pin changes nothing"


def test_a_sprint_9_configuration_file_is_read_and_upgraded(tmp_path: Path) -> None:
    """The unreleased Sprint 9 build stored one selection naming its family."""

    import json

    directory = tmp_path / "models"
    directory.mkdir(mode=0o700)
    legacy = {
        "schema_version": "0.1.0",
        "id": "model-configuration.local",
        "selection": {
            "family": "huggingface",
            "model_id": "openai/gpt-oss-120b",
            "provider_route": "deepinfra",
            "default_interpreter": "model",
            "data_use_acknowledged": False,
            "selected_at": NOW,
        },
        "credential_sources": {"huggingface": "file"},
        "provider_policy": "cheapest",
        "discovery": {},
        "extensions": {},
    }
    (directory / "model-configuration.json").write_text(json.dumps(legacy), encoding="utf-8")
    os.chmod(directory / "model-configuration.json", 0o600)

    service = _service(tmp_path)
    selection = service.selection("huggingface")
    assert selection is not None
    assert selection.model_id == "openai/gpt-oss-120b" and selection.provider_route == "deepinfra"
    assert service.selection("local") is None

    removed = dict(legacy, selection=dict(legacy["selection"], family="openai"))
    (directory / "model-configuration.json").write_text(json.dumps(removed), encoding="utf-8")
    assert _service(tmp_path).selections() == {"huggingface": None, "local": None}


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


# ----- OAK-S10-004: the verdict ------------------------------------------------------------


def test_verify_records_the_verdict_with_its_time_and_a_new_key_forgets_it(tmp_path: Path) -> None:
    asked: list[str] = []

    def verifier(family: str) -> dict[str, Any]:
        asked.append(family)
        return dict(ACCEPTED)

    service = _service(tmp_path, verifier=verifier)
    with pytest.raises(OAKError) as missing:
        service.verify("huggingface")
    assert missing.value.code == "OAK-MODEL-KEY-MISSING" and asked == []

    service.set_key("huggingface", SecretValue(KEY), source="file")
    assert service.verification_status("huggingface") is None
    assert service.is_verification_stale("huggingface") is True

    verdict = service.verify("huggingface")
    assert asked == ["huggingface"]
    assert verdict == {
        "verdict": "accepted",
        "checked_at": NOW,
        "method": "hub_whoami_v2",
        "token_role": "read",
        "inference_permission": True,
        "can_pay": False,
        "is_pro": False,
        "reason": None,
        "stale": False,
    }
    stored = (tmp_path / "models" / "model-configuration.json").read_text(encoding="utf-8")
    assert "MUST-NOT-BE-STORED" not in stored, "only the verdict's typed fields are kept"
    assert KEY not in stored
    status = service.status()
    assert status["credentials"]["huggingface"]["verification"]["verdict"] == "accepted"
    assert status["modes"]["online"]["verification"]["checked_at"] == NOW

    service.set_key("huggingface", SecretValue(KEY + "2"), source="file")
    assert service.verification_status("huggingface") is None, "a new key is unverified"
    service.verify("huggingface")
    assert service.remove_key("huggingface") is True
    assert service.verification_status("huggingface") is None

    bare = _service(tmp_path / "bare")
    bare.set_key("huggingface", SecretValue(KEY), source="file")
    with pytest.raises(OAKError) as unavailable:
        bare.verify("huggingface")
    assert unavailable.value.code == "OAK-MODEL-VERIFICATION-UNAVAILABLE"


def test_a_rejected_verdict_takes_online_ai_offline_until_a_new_key_is_stored(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        discoverer=lambda family, previous: SNAPSHOT,
        route_chooser=_first_capable,
        verifier=lambda family: {
            "verdict": "rejected",
            "method": "hub_whoami_v2",
            "reason": "Hugging Face did not accept this token (401)",
        },
    )
    service.set_key("huggingface", SecretValue(KEY), source="file")
    service.discover("huggingface")
    assert service.status()["modes"]["online"]["available"] is True

    service.verify("huggingface")
    online = service.status()["modes"]["online"]
    assert online["available"] is False
    assert "rejected the stored token at " + NOW in online["reason"]
    assert online["pair"] is not None, "what would be called is still shown"

    service.set_key("huggingface", SecretValue(KEY + "3"), source="file")
    assert service.status()["modes"]["online"]["available"] is True

    with pytest.raises(OAKError) as bad:
        service.record_verdict("huggingface", "shiny", method="hub_whoami_v2")
    assert bad.value.code == "OAK-MODEL-VERIFICATION-UNAVAILABLE"


def test_a_verdict_goes_stale_after_the_window_and_the_surfaces_say_so(tmp_path: Path) -> None:
    now = [NOW]
    service = _service(
        tmp_path,
        verifier=lambda family: dict(ACCEPTED),
        clock=lambda: now[0],
        verification_stale_seconds=60,
    )
    service.set_key("huggingface", SecretValue(KEY), source="file")
    service.verify("huggingface")
    assert service.is_verification_stale("huggingface") is False

    now[0] = "2026-09-17T10:02:00Z"
    status = service.verification_status("huggingface")
    assert status is not None and status["stale"] is True
    assert status["checked_at"] == NOW, "the time it was given, not the time it was read"
    assert service.is_verification_stale("huggingface") is True

    now[0] = "2026-09-17T09:00:00Z"
    status = service.verification_status("huggingface")
    assert status is not None and status["stale"] is True, "a future verdict is not current"
