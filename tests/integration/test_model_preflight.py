# SPDX-License-Identifier: Apache-2.0
"""OAK-S10-004: before an online interpretation, the token is corroborated and the catalogue
refreshed when either is stale, and a rejected token is refused before anything can spend.

No socket is opened here: the verifier and the catalogue refresh are stubbed at the wiring
seam in ``oak.bootstrap``, and what is pinned is *when* they are asked and what happens to
their answers.
"""

from __future__ import annotations

from typing import Any

import pytest

from oak import bootstrap
from oak.application import validate_key_input
from oak.bootstrap import create_model_configuration_service, create_model_interpreter
from oak.domain import OAKError
from oak.ports.interpreter import ProposalLimits

pytestmark = pytest.mark.integration

KEY = "oak-test-key-preflight-0123456789abcdef"
NOW = "2026-09-21T10:00:00Z"
SNAPSHOT: dict[str, Any] = {
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
                    "is_free": False,
                    "throughput": 846.0,
                }
            ],
        }
    ],
}


def _verifier(asked: list[str], verdict: str = "accepted") -> Any:
    def verify(family: str, *, deadline_seconds: float | None = None) -> dict[str, Any]:
        asked.append(family)
        return {"verdict": verdict, "method": "hub_whoami_v2", "reason": None}

    return verify


def _discover(refreshed: list[str]) -> Any:
    def refresh(configuration: Any) -> None:
        refreshed.append("huggingface")
        configuration.record_discovery("huggingface", dict(SNAPSHOT))

    return refresh


def test_a_stale_verdict_and_catalogue_are_refreshed_once_before_the_first_online_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    refreshed: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier(asked))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover(refreshed))
    create_model_configuration_service().set_key(
        "huggingface", validate_key_input(KEY), source="file"
    )

    adapter = create_model_interpreter("online")

    assert adapter is not None
    assert asked == ["huggingface"] and refreshed == ["huggingface"]
    status = create_model_configuration_service().status()
    assert status["modes"]["online"]["pair"]["model_id"] == "Qwen/Qwen3.8-27B"
    assert status["credentials"]["huggingface"]["verification"]["verdict"] == "accepted"

    # Fresh verdict and fresh snapshot: the second call asks nothing.
    assert create_model_interpreter("online") is not None
    assert asked == ["huggingface"] and refreshed == ["huggingface"]


def test_a_rejected_token_is_refused_before_anything_could_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier(asked, "rejected"))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover([]))
    create_model_configuration_service().set_key(
        "huggingface", validate_key_input(KEY), source="file"
    )

    with pytest.raises(OAKError) as refused:
        create_model_interpreter("online")

    assert refused.value.code == "OAK-MODEL-KEY-REJECTED"
    assert "oak models set-key" in refused.value.message
    assert asked == ["huggingface"]
    # The verdict is fresh, so a retry refuses again without asking the Hub again.
    with pytest.raises(OAKError):
        create_model_interpreter("online")
    assert asked == ["huggingface"]


def test_without_headroom_under_the_proxy_limit_the_pre_flight_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    refreshed: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier(asked))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover(refreshed))
    monkeypatch.setenv("OAK_MODEL_TIMEOUT_SECONDS", "50")
    configuration = create_model_configuration_service()
    configuration.set_key("huggingface", validate_key_input(KEY), source="file")
    assert bootstrap.preflight_allowed() is False

    assert create_model_interpreter("online") is None, "no catalogue, nothing pinned"
    assert asked == [] and refreshed == []

    configuration.select("huggingface", "openai/gpt-oss-20b")
    assert create_model_interpreter("online") is not None
    assert asked == [] and refreshed == [], "the stored state is used as it is"


def test_no_token_means_nothing_to_call_and_nothing_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier(asked))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover([]))

    assert create_model_interpreter("online") is None
    assert create_model_interpreter("local") is None
    assert create_model_interpreter("deterministic") is None
    assert asked == []


def test_a_token_the_provider_refuses_mid_interpretation_is_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier([]))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover([]))
    configuration = create_model_configuration_service()
    configuration.set_key("huggingface", validate_key_input(KEY), source="file")
    configuration.record_verdict("huggingface", "accepted", method="hub_whoami_v2")
    configuration.record_discovery("huggingface", dict(SNAPSHOT))

    class _Refusing:
        def propose(self, source_record: Any, source_content: bytes, limits: Any) -> Any:
            raise OAKError("OAK-MODEL-KEY-REJECTED", "the provider rejected the stored key")

    wrapped = bootstrap._VerdictRecordingInterpreter(_Refusing(), configuration, "huggingface")
    with pytest.raises(OAKError):
        wrapped.propose({}, b"brief", ProposalLimits())

    verification = configuration.verification_status("huggingface")
    assert verification is not None
    assert verification["verdict"] == "rejected" and verification["method"] == "interpretation"
    assert configuration.status()["modes"]["online"]["available"] is False
