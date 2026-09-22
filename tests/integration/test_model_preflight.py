# SPDX-License-Identifier: Apache-2.0
"""OAK-S10-004: before an online interpretation, the token is corroborated and the catalogue
refreshed when either is stale, and a rejected token is refused before anything can spend.

No socket is opened here: the verifier and the catalogue refresh are stubbed at the wiring
seam in ``oak.bootstrap``, and what is pinned is *when* they are asked and what happens to
their answers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from oak import bootstrap
from oak.application import validate_key_input
from oak.bootstrap import create_model_configuration_service, create_model_interpreter
from oak.domain import OAKError
from oak.ports.interpreter import ProposalLimits

pytestmark = pytest.mark.integration

KEY = "oak-test-key-preflight-0123456789abcdef"
# The snapshot must read as fresh whenever this suite runs: a fixed timestamp made the
# "nothing is asked twice" assertion pass for six hours after it was written and fail for
# ever afterwards. The stamp follows the clock the service uses.
NOW = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
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

    configuration.record_discovery("huggingface", dict(SNAPSHOT))
    configuration.select("huggingface", "Qwen/Qwen3.8-27B", provider_route="cerebras")
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


def test_a_rejection_stands_when_the_hub_cannot_be_reached_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later attempt that hears nothing never turns a rejected token back on."""

    answers = ["rejected", "unreachable", "unreachable"]
    asked: list[str] = []

    def verify(family: str, *, deadline_seconds: float | None = None) -> dict[str, Any]:
        asked.append(family)
        return {"verdict": answers.pop(0), "method": "hub_whoami_v2", "reason": "x"}

    monkeypatch.setattr(bootstrap, "model_verifier", verify)
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover([]))
    monkeypatch.setenv("OAK_MODEL_VERIFICATION_STALE_SECONDS", "0")
    configuration = create_model_configuration_service()
    configuration.set_key("huggingface", validate_key_input(KEY), source="file")
    configuration.verify("huggingface")
    assert asked == ["huggingface"]

    for _ in range(2):
        with pytest.raises(OAKError) as refused:
            create_model_interpreter("online")
        assert refused.value.code == "OAK-MODEL-KEY-REJECTED"
    # The stale rejection is refused before any re-check; nothing was asked again.
    assert asked == ["huggingface"]
    status = configuration.verification_status("huggingface")
    assert status is not None and status["verdict"] == "rejected"


def test_a_pinned_pair_the_catalogue_no_longer_supports_is_refused_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier([]))
    moved = {
        **SNAPSHOT,
        "models": [
            {
                **SNAPSHOT["models"][0],
                "providers": [
                    {
                        "provider": "cerebras",
                        "supports_structured_output": False,
                        "output_price_per_million": 1.49,
                        "is_free": False,
                        "throughput": 846.0,
                    },
                    {
                        "provider": "deepinfra",
                        "supports_structured_output": True,
                        "output_price_per_million": 2.5,
                        "is_free": False,
                        "throughput": 40.0,
                    },
                ],
            }
        ],
    }

    def refresh(configuration: Any) -> None:
        configuration.record_discovery("huggingface", moved)

    monkeypatch.setattr(bootstrap, "_preflight_discover", refresh)
    monkeypatch.setenv("OAK_MODEL_DISCOVERY_CACHE_SECONDS", "0")
    configuration = create_model_configuration_service()
    configuration.set_key("huggingface", validate_key_input(KEY), source="file")
    configuration.record_discovery("huggingface", dict(SNAPSHOT))
    configuration.select("huggingface", "Qwen/Qwen3.8-27B", provider_route="cerebras")

    with pytest.raises(OAKError) as refused:
        create_model_interpreter("online")
    assert refused.value.code == "OAK-MODEL-ROUTE"
    assert "cerebras" in refused.value.message and "structured output" in refused.value.message


def test_only_a_credential_refusal_is_remembered_as_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "model_verifier", _verifier([]))
    monkeypatch.setattr(bootstrap, "_preflight_discover", _discover([]))
    configuration = create_model_configuration_service()
    configuration.set_key("huggingface", validate_key_input(KEY), source="file")
    configuration.record_verdict("huggingface", "accepted", method="hub_whoami_v2")

    class _Refusing:
        def __init__(self, message: str) -> None:
            self.message = message

        def propose(self, source_record: Any, source_content: bytes, limits: Any) -> Any:
            raise OAKError("OAK-MODEL-KEY-REJECTED", self.message)

    # A 403 on one request keeps the same code but is not about the credential.
    per_request = bootstrap._VerdictRecordingInterpreter(
        _Refusing("the huggingface provider refused the stored key for this request"),
        configuration,
        "huggingface",
    )
    with pytest.raises(OAKError):
        per_request.propose({}, b"brief", ProposalLimits())
    status = configuration.verification_status("huggingface")
    assert status is not None and status["verdict"] == "accepted"

    # The local family has no credential to record a verdict about.
    local = bootstrap._VerdictRecordingInterpreter(
        _Refusing("the local provider rejected the stored key; store a current key"),
        configuration,
        "local",
    )
    with pytest.raises(OAKError):
        local.propose({}, b"brief", ProposalLimits())
    assert configuration.verification_status("local") is None
