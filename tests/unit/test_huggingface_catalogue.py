# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-005 / OAK-S10-003: looking up the current top open model, without trusting the answer.

The lookup reads two public catalogues anonymously. Model-card metadata is author-controlled,
so the rules under test are that the filter is real (gated models and untrusted namespaces
never survive), that a model with no structured-output route is never recommended, that the
licence is recorded rather than trusted, that the preferred model is the first survivor in
the Hub's trending order, that nothing from the brief or the credential store is sent, and
that an unreachable catalogue produces the pinned chain labelled `pinned` rather than a
pretend live answer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from oak.adapters.models.huggingface_catalogue import (
    HUB_MODELS_URL,
    PINNED_AS_OF,
    PINNED_MODELS,
    ROUTER_MODELS_URL,
    TRUSTED_NAMESPACES,
    TRUSTED_NAMESPACES_AS_OF,
    discover_huggingface,
    pinned_snapshot,
)
from oak.adapters.models.transport import TransportRequest, TransportResponse
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from tests.unit.test_provider_profiles import ROOT

FETCHED_AT = "2026-09-17T09:00:00Z"
KEY = "oak-test-key-huggingface-0123456789ab"
BRIEF = "A support desk wants drafted answers from public manuals."


def _router(*models: dict[str, Any]) -> TransportResponse:
    return TransportResponse(200, {}, json.dumps({"data": list(models)}).encode("utf-8"))


def _hub(*entries: dict[str, Any]) -> TransportResponse:
    return TransportResponse(200, {}, json.dumps(list(entries)).encode("utf-8"))


def _served(
    identifier: str, *, structured: bool = True, price: float | None = 0.2
) -> dict[str, Any]:
    return {
        "id": identifier,
        "object": "model",
        "created": 1_754_000_000,
        "providers": [
            {
                "provider": "deepinfra",
                "status": "live",
                "pricing": {"input": 0.04, "output": price},
                "supports_structured_output": structured,
            }
        ],
    }


def _listed(identifier: str, *, licence: str = "apache-2.0", gated: Any = False) -> dict[str, Any]:
    return {"id": identifier, "gated": gated, "cardData": {"license": licence}}


class _Fetcher:
    def __init__(self, router: TransportResponse, hub: TransportResponse) -> None:
        self._responses = {ROUTER_MODELS_URL: router, HUB_MODELS_URL: hub}
        self.requests: list[TransportRequest] = []

    def __call__(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        return self._responses[request.url]


def _snapshot(fetcher: _Fetcher) -> dict[str, Any]:
    snapshot = discover_huggingface(fetcher, fetched_at=FETCHED_AT)
    # Everything this returns is written to the model-configuration file, so it must be
    # valid against that schema before it is trusted anywhere else.
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    registry.validate(
        "model-configuration.schema.json",
        {
            "schema_version": "0.1.0",
            "id": "model-configuration.local",
            "selection": {},
            "credential_sources": {},
            "provider_policy": "cheapest",
            "discovery": {"huggingface": snapshot},
            "extensions": {},
        },
    )
    return snapshot


def test_both_catalogue_reads_are_anonymous_public_gets() -> None:
    fetcher = _Fetcher(
        _router(_served("openai/gpt-oss-120b")), _hub(_listed("openai/gpt-oss-120b"))
    )

    _snapshot(fetcher)

    assert [request.method for request in fetcher.requests] == ["GET", "GET"]
    for request in fetcher.requests:
        assert request.body is None
        assert request.headers == {}, "no credential and no custom header is sent"
        assert KEY not in request.url and BRIEF not in request.url
        assert request.url.startswith("https://")
        assert request.url.split("/")[2] in {"router.huggingface.co", "huggingface.co"}
    assert "inference_provider=all" in HUB_MODELS_URL
    assert "filter=conversational" in HUB_MODELS_URL
    assert "direction=-1" in HUB_MODELS_URL


def test_the_preferred_model_is_the_first_trending_survivor_not_a_pin() -> None:
    fetcher = _Fetcher(
        _router(
            _served("Qwen/Qwen3-235B-A22B-Instruct-2507"),
            _served("openai/gpt-oss-120b"),
            _served("openai/gpt-oss-20b"),
        ),
        _hub(
            _listed("Qwen/Qwen3-235B-A22B-Instruct-2507"),
            _listed("openai/gpt-oss-20b"),
            _listed("openai/gpt-oss-120b"),
        ),
    )

    snapshot = _snapshot(fetcher)

    assert snapshot["source"] == "live"
    assert snapshot["fetched_at"] == FETCHED_AT
    assert snapshot["recommended"] == "Qwen/Qwen3-235B-A22B-Instruct-2507"
    assert [model["id"] for model in snapshot["models"]] == [
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ], "the Hub's trending order, not the pinned order"


def test_a_pinned_model_the_hub_did_not_list_is_offered_after_the_trending_ones() -> None:
    fetcher = _Fetcher(
        _router(_served("zai-org/GLM-5.2"), _served(PINNED_MODELS[0].id)),
        _hub(_listed("zai-org/GLM-5.2", licence="mit")),
    )

    snapshot = _snapshot(fetcher)

    identifiers = [model["id"] for model in snapshot["models"]]
    assert identifiers == ["zai-org/GLM-5.2", PINNED_MODELS[0].id]
    assert snapshot["models"][0]["licence"] == "mit"
    assert snapshot["recommended"] == "zai-org/GLM-5.2"


@pytest.mark.parametrize(
    "entry,licence",
    [
        (_listed("moonshotai/Kimi-K2-Instruct", licence="other"), "other"),
        (_listed("zai-org/GLM-5.3", licence="other"), "other"),
        (_listed("Qwen/Qwen3-8B", licence=None), "unknown"),
        (_listed("Qwen/Qwen3-8B", licence="apache-2.0"), "apache-2.0"),
    ],
)
def test_the_licence_is_recorded_and_shown_rather_than_used_to_exclude(
    entry: dict[str, Any], licence: str
) -> None:
    identifier = str(entry["id"])
    fetcher = _Fetcher(_router(_served(identifier)), _hub(entry))

    snapshot = _snapshot(fetcher)

    assert snapshot["source"] == "live"
    assert [model["id"] for model in snapshot["models"]] == [identifier]
    assert snapshot["models"][0]["licence"] == licence


@pytest.mark.parametrize(
    "entry,reason",
    [
        (_listed("meta-llama/Llama-3.3-70B-Instruct", licence="llama3.3", gated="manual"), "gated"),
        (_listed("google/gemma-3-27b-it", licence="gemma", gated="manual"), "gated"),
        (_listed("OBLITERATUS/Qwen3.8-27B-OBLITERATED"), "untrusted namespace"),
        (_listed("somebody/finetune-of-something"), "untrusted namespace"),
        (_listed("Qwen/Qwen3-8B", gated=True), "gated by boolean"),
    ],
)
def test_the_filter_drops_gated_and_untrusted_candidates(
    entry: dict[str, Any], reason: str
) -> None:
    identifier = str(entry["id"])
    fetcher = _Fetcher(_router(_served(identifier)), _hub(entry))

    snapshot = _snapshot(fetcher)

    assert snapshot["source"] == "pinned", reason
    assert identifier not in [model["id"] for model in snapshot["models"]], reason


def test_a_model_with_no_structured_output_route_is_never_offered() -> None:
    fetcher = _Fetcher(
        _router(_served("Qwen/Qwen3-8B", structured=False)),
        _hub(_listed("Qwen/Qwen3-8B")),
    )

    snapshot = _snapshot(fetcher)

    assert snapshot["source"] == "pinned"
    assert all(
        any(route["supports_structured_output"] for route in model["providers"])
        for model in snapshot["models"]
    )


def test_a_model_the_router_does_not_serve_is_never_offered() -> None:
    fetcher = _Fetcher(_router(_served("openai/gpt-oss-120b")), _hub(_listed("Qwen/Qwen3-8B")))

    snapshot = _snapshot(fetcher)

    assert [model["id"] for model in snapshot["models"]] == ["openai/gpt-oss-120b"]


def test_dead_provider_routes_are_dropped_from_the_snapshot() -> None:
    served = {
        "id": "openai/gpt-oss-120b",
        "providers": [
            {"provider": "together", "status": "error", "supports_structured_output": True},
            {
                "provider": "groq",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 0.75},
            },
            {
                "provider": "deepinfra",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 0.17},
            },
        ],
    }
    fetcher = _Fetcher(_router(served), _hub(_listed("openai/gpt-oss-120b")))

    snapshot = _snapshot(fetcher)

    routes = snapshot["models"][0]["providers"]
    assert [route["provider"] for route in routes] == ["groq", "deepinfra"]
    assert all(route["output_price_per_million"] is not None for route in routes)


def test_hostile_card_metadata_cannot_widen_the_filter_or_the_snapshot() -> None:
    hostile = [
        # Licences are cumulative: a second, restrictive entry restricts the model, so the
        # permissive first element must not decide it.
        {
            "id": "openai/gpt-oss-120b",
            "gated": False,
            "cardData": {"license": ["apache-2.0", "cc-by-nc-4.0"]},
        },
        {"id": "openai/gpt-oss-20b", "gated": False, "cardData": {"license": ["mit"]}},
        {"id": "evil/model", "gated": "false", "cardData": {"license": "apache-2.0"}},
        {"id": "x" * 400, "gated": False, "cardData": {"license": "mit"}},
        {"id": 7, "gated": False, "cardData": {"license": "mit"}},
        {"id": "no-namespace", "gated": False, "cardData": {"license": "mit"}},
        {"id": "Qwen/Qwen3-8B", "gated": False, "cardData": "not-an-object"},
        {"id": "Qwen/Qwen3-8B", "gated": False},
        "a string, not an entry",
    ]
    fetcher = _Fetcher(
        _router(
            _served("openai/gpt-oss-120b"),
            _served("openai/gpt-oss-20b"),
            _served("evil/model"),
            _served("Qwen/Qwen3-8B"),
        ),
        TransportResponse(200, {}, json.dumps(hostile).encode("utf-8")),
    )

    snapshot = _snapshot(fetcher)

    # The dual-licensed model is offered as `other`, never as its most generous member; the
    # malformed entries and the untrusted namespace never appear; the entry with unreadable
    # card data is offered with its licence honestly unknown.
    assert [model["id"] for model in snapshot["models"]] == [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "Qwen/Qwen3-8B",
    ]
    assert [model["licence"] for model in snapshot["models"]] == ["other", "mit", "unknown"]
    assert snapshot["source"] == "live"


@pytest.mark.parametrize(
    "code",
    ["OAK-INTERPRETER-UNAVAILABLE", "OAK-MODEL-RATE-LIMITED", "OAK-MODEL-DISCOVERY-UNAVAILABLE"],
)
def test_an_unreachable_catalogue_falls_back_to_the_pinned_chain(code: str) -> None:
    def failing(request: TransportRequest) -> TransportResponse:
        raise OAKError(code, "the catalogue could not be reached", retriable=True)

    snapshot = discover_huggingface(failing, fetched_at=FETCHED_AT)

    assert snapshot["source"] == "pinned"
    assert snapshot["recommended"] == PINNED_MODELS[0].id == "Qwen/Qwen3.8-27B"
    assert [model["id"] for model in snapshot["models"]] == [
        descriptor.id for descriptor in PINNED_MODELS
    ]
    assert snapshot == pinned_snapshot(FETCHED_AT)


def test_an_unexpected_error_is_not_swallowed_by_the_fallback() -> None:
    def failing(request: TransportRequest) -> TransportResponse:
        raise OAKError("OAK-MODEL-EGRESS-DENIED", "the host is not allowlisted")

    with pytest.raises(OAKError) as refused:
        discover_huggingface(failing, fetched_at=FETCHED_AT)
    assert refused.value.code == "OAK-MODEL-EGRESS-DENIED"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_a_refusing_catalogue_falls_back_rather_than_offering_nothing(status: int) -> None:
    empty = TransportResponse(status, {}, b"{}")
    snapshot = discover_huggingface(_Fetcher(empty, empty), fetched_at=FETCHED_AT)
    assert snapshot["source"] == "pinned"


def test_the_pinned_chain_is_permissive_trusted_and_structured_output_capable() -> None:
    assert [descriptor.id for descriptor in PINNED_MODELS] == [
        "Qwen/Qwen3.8-27B",
        "zai-org/GLM-5.3-Flash",
        "openai/gpt-oss-120b",
    ]
    assert PINNED_AS_OF == TRUSTED_NAMESPACES_AS_OF == "2026-09-21"
    for descriptor in PINNED_MODELS:
        assert descriptor.licence in {"apache-2.0", "mit", "bsd-3-clause"}
        assert descriptor.providers
        assert all(route.supports_structured_output for route in descriptor.providers)
        assert descriptor.id.split("/", 1)[0] in TRUSTED_NAMESPACES
        assert all(route.throughput is not None for route in descriptor.providers)


def test_free_promotions_and_throughput_are_read_into_the_snapshot() -> None:
    served = {
        "id": "openai/gpt-oss-120b",
        "providers": [
            {
                "provider": "groq",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 0.75},
                "is_free": True,
                "throughput": 427.2,
            },
            {
                "provider": "deepinfra",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 0.17},
                "is_free": "yes",
                "throughput": -3,
            },
            {
                "provider": "cerebras",
                "status": "live",
                "supports_structured_output": True,
                "throughput": float("inf"),
            },
        ],
    }
    fetcher = _Fetcher(_router(served), _hub(_listed("openai/gpt-oss-120b")))

    routes = _snapshot(fetcher)["models"][0]["providers"]

    assert [(r["provider"], r["is_free"], r["throughput"]) for r in routes] == [
        ("groq", True, 427.2),
        ("deepinfra", False, None),
        ("cerebras", False, None),
    ]


def test_the_two_catalogues_are_joined_without_regard_to_case() -> None:
    """A Hub spelling that differs in case must neither demote a model nor bypass gating."""

    fetcher = _Fetcher(
        _router(_served("Qwen/Qwen3.8-27B"), _served("openai/gpt-oss-120b")),
        _hub(
            _listed("qwen/qwen3.8-27b", gated="manual"),
            _listed("OpenAI/GPT-OSS-120B"),
        ),
    )

    snapshot = _snapshot(fetcher)

    identifiers = [model["id"] for model in snapshot["models"]]
    assert "Qwen/Qwen3.8-27B" not in identifiers, "gated on the Hub, however it is spelled"
    assert identifiers == ["openai/gpt-oss-120b"], "the router's spelling is the one stored"
    assert snapshot["recommended"] == "openai/gpt-oss-120b"
