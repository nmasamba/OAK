# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-005 / OAK-S10-002: two provider families, described as data, exercised on fixtures.

No network: every response here is a recorded fixture under `tests/fixtures/providers/`.
The rules under test are the ones that matter if a provider misbehaves or a hostile endpoint
answers: auth material only ever travels in a header, provider text never reaches an error
message, every documented status maps to one stable OAK code, and a non-chat entry never
becomes a selectable model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.models.providers import (
    HINTS_AS_OF,
    WHOAMI_URL,
    ModelDescriptor,
    ProviderProfile,
    ProviderRoute,
    Verdict,
    _huggingface_routes,
    chat_request,
    descriptor_from,
    discover_models,
    error_for_status,
    extract_text,
    key_verification_request,
    local_profile,
    models_request,
    parse_models,
    parse_verification,
    profile_for,
    recommended_route,
    retry_after_seconds,
)
from oak.adapters.models.transport import TransportRequest, TransportResponse
from oak.domain import OAKError, canonical_json_bytes
from oak.domain.model_families import FAMILY_BY_ID, FAMILY_IDS

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "providers"
HOSTED = tuple(family for family in FAMILY_IDS if family != "local")
KEY = "oak-test-key-provider-0123456789abcdef"
SENTINEL = "PROVIDER-TEXT-THAT-MUST-NOT-LEAK"
SCHEMA = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}


def _response(status: int, document: Any, **headers: str) -> TransportResponse:
    body = json.dumps(document).encode("utf-8")
    return TransportResponse(
        status=status,
        headers={name.lower().replace("_", "-"): value for name, value in headers.items()},
        body=body,
    )


def _fixture(family: str, name: str) -> Any:
    return json.loads((FIXTURES / family / f"{name}.json").read_text(encoding="utf-8"))


def _profile(family: str) -> ProviderProfile:
    return profile_for(family, local_endpoint=None)


# ----- the table itself ------------------------------------------------------------


@pytest.mark.parametrize("family", FAMILY_IDS)
def test_every_family_has_a_profile_whose_hosts_are_https_and_fixed(family: str) -> None:
    profile = profile_for(family, local_endpoint="http://127.0.0.1:11434/v1")
    assert profile.family == family
    assert profile.allowed_hosts
    assert profile.hints_as_of == HINTS_AS_OF
    descriptor = FAMILY_BY_ID[family]
    assert profile.credential_required == descriptor.credential_required
    if family == "local":
        assert profile.plain_http_loopback is True
        assert profile.base_url.startswith("http://127.0.0.1")
    else:
        assert profile.plain_http_loopback is False
        assert profile.base_url.startswith("https://")
        host = profile.base_url.split("/")[2]
        assert host in profile.allowed_hosts
        assert profile.preferred_order, family
        assert all(identifier for identifier in profile.preferred_order)


def test_an_unknown_family_is_refused_with_the_shared_code() -> None:
    with pytest.raises(OAKError) as refused:
        profile_for("deepmind")
    assert refused.value.code == "OAK-MODEL-FAMILY-UNKNOWN"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.example.test/v1",
        "http://10.0.0.5:11434/v1",
        "http://ollama.local:11434/v1",
        "http://user:pass@127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/v1?key=x",
        "ftp://127.0.0.1/v1",
        "127.0.0.1:11434",
    ],
)
def test_a_non_loopback_local_endpoint_is_refused(endpoint: str) -> None:
    with pytest.raises(OAKError) as refused:
        local_profile(endpoint)
    assert refused.value.code == "OAK-MODEL-ENDPOINT-INVALID"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:11434/v1",
        "http://localhost:8000/v1",
        "https://127.0.0.1:8443/v1",
        "  http://127.0.0.1:11434/v1  ",
        None,
        "",
    ],
)
def test_a_loopback_local_endpoint_is_accepted(endpoint: str | None) -> None:
    profile = local_profile(endpoint)
    assert profile.allowed_hosts <= {"127.0.0.1", "localhost"}
    assert profile.credential_required is False


# ----- requests --------------------------------------------------------------------


@pytest.mark.parametrize("family", HOSTED)
def test_the_key_travels_only_in_a_header_never_in_a_url_or_body(family: str) -> None:
    profile = _profile(family)
    requests = [
        models_request(profile, KEY),
        chat_request(
            profile,
            "model-x",
            key=KEY,
            system_prompt="system",
            user_content="brief",
            response_schema=SCHEMA,
            schema_name="s",
            max_tokens=512,
        ),
    ]
    verification = key_verification_request(profile, KEY)
    if verification is not None:
        requests.append(verification)
    for request in requests:
        assert KEY not in request.url, family
        assert KEY not in (request.body or b"").decode("utf-8"), family
        assert any(KEY in value for value in request.headers.values()), family
        assert request.url.split("/")[2] in profile.allowed_hosts, family
        assert request.url.startswith("https://"), family
        assert request.headers["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("family", FAMILY_IDS)
def test_the_chat_body_asks_for_the_schema_in_that_provider_s_own_spelling(family: str) -> None:
    profile = profile_for(family, local_endpoint="http://127.0.0.1:11434/v1")
    request = chat_request(
        profile,
        "model-x",
        key=KEY,
        system_prompt="SYSTEM",
        user_content="<brief>text</brief>",
        response_schema=SCHEMA,
        schema_name="oak_proposal",
        max_tokens=1024,
    )
    body = json.loads(request.body or b"{}")
    assert body["model"] == "model-x"
    assert profile.request_shape == "openai_chat"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert body["messages"][1]["content"] == "<brief>text</brief>"
    assert body["max_tokens"] == 1024
    assert request.headers["Content-Type"] == "application/json"


def test_a_hugging_face_request_pins_the_provider_route_when_one_is_chosen() -> None:
    profile = _profile("huggingface")
    request = chat_request(
        profile,
        "openai/gpt-oss-120b:groq",
        key=KEY,
        system_prompt="s",
        user_content="b",
        response_schema=SCHEMA,
        schema_name="s",
        max_tokens=256,
    )
    assert json.loads(request.body or b"{}")["model"] == "openai/gpt-oss-120b:groq"


def test_key_verification_asks_the_hub_who_the_token_is_and_the_local_server_whether_it_is_up() -> (
    None
):
    """The router's list is a public catalogue and proves nothing; the Hub's whoami does."""

    assert _profile("huggingface").key_verification == "hub_whoami_v2"
    verification = key_verification_request(_profile("huggingface"), KEY)
    assert verification is not None
    assert verification.method == "GET" and verification.url == WHOAMI_URL
    assert verification.body is None
    assert verification.headers == {"Authorization": f"Bearer {KEY}"}
    local = profile_for("local", local_endpoint="http://127.0.0.1:11434/v1")
    assert local.key_verification == "authenticated_models_list"
    listing = key_verification_request(local, None)
    assert listing is not None and listing.url.endswith("/models") and listing.headers == {}


SENTINEL_NAME = "sentinel-account-name-MUST-NOT-BE-STORED"
SENTINEL_EMAIL = "sentinel.address.MUST-NOT-BE-STORED@example.invalid"


@pytest.mark.parametrize(
    "status,fixture,expected",
    [
        (
            200,
            "whoami-v2",
            Verdict("accepted", "hub_whoami_v2", "read", True, False, False),
        ),
        (
            200,
            "whoami-v2-finegrained",
            Verdict("accepted", "hub_whoami_v2", "fineGrained", True, True, True),
        ),
        (200, "whoami-v2-hostile", Verdict("accepted", "hub_whoami_v2", None, None, None, None)),
        (401, "whoami-v2-401", Verdict("rejected", "hub_whoami_v2")),
        (403, "whoami-v2-401", Verdict("scope_limited", "hub_whoami_v2")),
        (429, "whoami-v2-401", Verdict("unreachable", "hub_whoami_v2")),
        (500, "whoami-v2-401", Verdict("unreachable", "hub_whoami_v2")),
        (503, "whoami-v2", Verdict("unreachable", "hub_whoami_v2")),
    ],
)
def test_the_hub_whoami_answer_becomes_a_verdict_and_nothing_else(
    status: int, fixture: str, expected: Verdict
) -> None:
    """Role, permission and billing come through; the account's name and email never do."""

    payload = _fixture("huggingface", fixture)
    verdict = parse_verification(_profile("huggingface"), _response(status, payload))

    assert verdict.verdict == expected.verdict
    assert verdict.method == expected.method
    assert verdict.token_role == expected.token_role
    assert verdict.inference_permission == expected.inference_permission
    assert verdict.can_pay == expected.can_pay
    assert verdict.is_pro == expected.is_pro
    if verdict.verdict != "accepted":
        assert verdict.reason, "a non-acceptance says why"
    rendered = json.dumps(verdict.to_document())
    assert SENTINEL_NAME not in rendered and SENTINEL_EMAIL not in rendered
    assert "ignore previous" not in rendered


def test_the_inference_permission_is_found_where_the_hub_actually_puts_it() -> None:
    """A live call on 2026-09-22 settled this: it arrives under `scoped`, not `global`.

    The first fixture put it in `global`, so the positive case passed without ever
    exercising the path the Hub uses.
    """

    payload = _fixture("huggingface", "whoami-v2-finegrained")
    fine_grained = payload["auth"]["accessToken"]["fineGrained"]
    assert "inference.serverless.write" not in fine_grained["global"]
    assert "inference.serverless.write" in fine_grained["scoped"][0]["permissions"]

    verdict = parse_verification(_profile("huggingface"), _response(200, payload))

    assert verdict.verdict == "accepted" and verdict.token_role == "fineGrained"
    assert verdict.inference_permission is True
    # The entity the permission is scoped to names the account; none of it is kept.
    assert SENTINEL_NAME not in json.dumps(verdict.to_document())


def test_a_fine_grained_token_without_the_inference_permission_is_reported_not_assumed() -> None:
    payload = _fixture("huggingface", "whoami-v2-finegrained")
    payload["auth"]["accessToken"]["fineGrained"] = {
        "global": ["repo.content.read"],
        "scoped": [{"entity": {"type": "user"}, "permissions": ["repo.write"]}],
    }
    verdict = parse_verification(_profile("huggingface"), _response(200, payload))
    assert verdict.verdict == "accepted" and verdict.inference_permission is False

    payload["auth"]["accessToken"].pop("fineGrained")
    verdict = parse_verification(_profile("huggingface"), _response(200, payload))
    assert verdict.inference_permission is None, "scopes not reported: unknown, never assumed"

    unreadable = TransportResponse(status=200, headers={}, body=b"<html>" + SENTINEL.encode())
    verdict = parse_verification(_profile("huggingface"), unreadable)
    assert verdict.verdict == "unreachable" and SENTINEL not in json.dumps(verdict.to_document())


@pytest.mark.parametrize(
    "status,expected",
    [(200, "accepted"), (401, "rejected"), (403, "rejected"), (503, "unreachable")],
)
def test_the_local_server_is_verified_by_whether_its_list_answers(
    status: int, expected: str
) -> None:
    local = profile_for("local", local_endpoint="http://127.0.0.1:11434/v1")
    verdict = parse_verification(local, _response(status, {"data": [], "note": SENTINEL}))
    assert verdict.verdict == expected and verdict.method == "models_list"
    assert SENTINEL not in json.dumps(verdict.to_document())


# ----- catalogue parsing -----------------------------------------------------------


@pytest.mark.parametrize("family", HOSTED)
def test_the_recorded_model_list_parses_into_chat_models_only(family: str) -> None:
    profile = _profile(family)
    payload = _fixture(family, "models")
    entries, token = parse_models(profile, _response(200, payload))
    descriptors = [descriptor_from(profile, entry) for entry in entries]
    kept = [descriptor for descriptor in descriptors if descriptor is not None]
    assert kept, family
    assert len(kept) < len(entries), f"{family} kept every entry; the filter is vacuous"
    for descriptor in kept:
        assert descriptor.licence in {"apache-2.0", "mit", "bsd-3-clause", "other", "unknown"}
        assert descriptor.data_use in {"trains_on_inputs", "not_used_for_training", "unknown"}
        assert 0 < len(descriptor.id) <= 256
        assert len(descriptor.display_name) <= 200
        assert len(descriptor.providers) <= 32
    assert token is None, "neither remaining family paginates its list"
    if family == "huggingface":
        assert all(descriptor.providers for descriptor in kept)
        assert any(
            route.supports_structured_output
            for descriptor in kept
            for route in descriptor.providers
        )


@pytest.mark.parametrize("family", HOSTED)
def test_a_hostile_catalogue_entry_cannot_inject_an_identifier_or_a_route(family: str) -> None:
    """Nothing malformed survives, and what does survive is bounded and route-free.

    Two entries in the fixture are well-formed identifiers borrowed from another family's
    catalogue. A family whose rule is "any chat-shaped id" is entitled to accept those —
    they are ordinary data, not an injection — so the invariant under test is that every
    surviving descriptor is one OAK could have produced itself: a bounded `name` or
    `namespace/name`, no URL, no path, no provider route the entry supplied.
    """

    profile = _profile(family)
    entries, _ = parse_models(profile, _response(200, _fixture("hostile", "models")))
    survivors = [descriptor_from(profile, entry) for entry in entries]
    for descriptor in survivors:
        if descriptor is None:
            continue
        assert descriptor.id in {"openai/gpt-oss-120b"}, (family, descriptor.id)
        assert descriptor.providers == (), family
        assert len(descriptor.display_name) <= 200
    if family == "huggingface":
        # Live-looking routes with an unusable provider name are dropped, which leaves the
        # entry with no route at all, which disqualifies it.
        assert all(descriptor is None for descriptor in survivors)


@pytest.mark.parametrize("family", HOSTED)
def test_an_unreadable_model_list_is_one_retriable_code(family: str) -> None:
    profile = _profile(family)
    for document in ({}, {"data": "nope"}, {"models": 3}, [], "text", None):
        with pytest.raises(OAKError) as refused:
            parse_models(profile, _response(200, document))
        assert refused.value.code == "OAK-MODEL-DISCOVERY-UNAVAILABLE"
        assert refused.value.retriable is True


def test_discovery_refuses_before_a_request_when_the_key_is_missing() -> None:
    def fetch(request: TransportRequest) -> TransportResponse:
        raise AssertionError("discovery called the provider without a key")

    with pytest.raises(OAKError) as refused:
        discover_models(_profile("huggingface"), fetch, key=None, fetched_at="2026-09-17T00:00:00Z")
    assert refused.value.code == "OAK-MODEL-KEY-MISSING"


def test_the_cheapest_structured_output_route_is_chosen_for_hugging_face() -> None:
    document = ModelDescriptor(
        id="openai/gpt-oss-120b",
        display_name="openai/gpt-oss-120b",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("nscale", False, 0.40),
            ProviderRoute("groq", True, 0.75),
            ProviderRoute("deepinfra", True, 0.17),
            ProviderRoute("featherless-ai", True, None),
        ),
    ).to_document()
    assert recommended_route(document, "cheapest") == "deepinfra"
    assert recommended_route(document, "fastest") == "groq", "no throughput: first capable"
    assert recommended_route(None, "cheapest") is None

    measured = ModelDescriptor(
        id="Qwen/Qwen3.8-27B",
        display_name="Qwen/Qwen3.8-27B",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("nscale", False, 0.10, throughput=999.0),
            ProviderRoute("cerebras", True, 1.49, throughput=846.0),
            ProviderRoute("deepinfra", True, 2.5, throughput=40.0),
            ProviderRoute("baseten", True, 3.0, is_free=True, throughput=72.0),
        ),
    ).to_document()
    assert recommended_route(measured, "fastest") == "cerebras", "fastest structured route"
    assert recommended_route(measured, "cheapest") == "baseten", "a free promotion beats price"
    assert recommended_route(None, "fastest") is None
    assert (
        recommended_route(
            {"providers": [{"provider": "x", "supports_structured_output": False}]}, "cheapest"
        )
        is None
    )


# ----- completions -----------------------------------------------------------------


@pytest.mark.parametrize("family", FAMILY_IDS)
def test_a_recorded_completion_yields_its_text_and_usage(family: str) -> None:
    profile = profile_for(family, local_endpoint="http://127.0.0.1:11434/v1")
    text, usage = extract_text(profile, _response(200, _fixture("huggingface", "completion")))
    assert json.loads(text)["proposed_claims"]
    assert usage["input_tokens"] == 1200
    assert usage["output_tokens"] == 340


def test_a_refusal_an_empty_answer_and_a_truncation_are_explicit() -> None:
    profile = _profile("huggingface")
    refusal = _fixture("huggingface", "refusal")
    with pytest.raises(OAKError) as refused:
        extract_text(profile, _response(200, refusal))
    assert refused.value.code == "OAK-INTERPRETER-MALFORMED"

    truncated = _fixture("huggingface", "truncated")
    with pytest.raises(OAKError) as cut:
        extract_text(profile, _response(200, truncated))
    assert cut.value.code == "OAK-INTERPRETER-OUTPUT-LIMIT"

    for document in (
        {},
        {"choices": []},
        {"content": []},
        {"choices": [{"message": {"content": "  "}}]},
    ):
        with pytest.raises(OAKError) as unusable:
            extract_text(profile, _response(200, document))
        assert unusable.value.code == "OAK-INTERPRETER-MALFORMED"


def test_a_non_json_completion_body_is_malformed_without_echoing_it() -> None:
    response = TransportResponse(status=200, headers={}, body=b"<html>" + SENTINEL.encode())
    with pytest.raises(OAKError) as unusable:
        extract_text(_profile("huggingface"), response)
    assert unusable.value.code == "OAK-INTERPRETER-MALFORMED"
    assert SENTINEL not in unusable.value.message


# ----- status mapping --------------------------------------------------------------


@pytest.mark.parametrize(
    "status,body,expected,retriable",
    [
        (
            401,
            {"error": {"type": "authentication_error", "message": SENTINEL}},
            "OAK-MODEL-KEY-REJECTED",
            False,
        ),
        (
            403,
            {"error": {"type": "permission_error", "message": SENTINEL}},
            "OAK-MODEL-KEY-REJECTED",
            False,
        ),
        (
            402,
            {"error": {"type": "billing_error", "message": SENTINEL}},
            "OAK-MODEL-QUOTA-EXHAUSTED",
            False,
        ),
        (
            429,
            {"error": {"code": "credit_balance_exhausted", "message": SENTINEL}},
            "OAK-MODEL-QUOTA-EXHAUSTED",
            False,
        ),
        (
            429,
            {"error": {"type": "rate_limit_error", "message": SENTINEL}},
            "OAK-MODEL-RATE-LIMITED",
            True,
        ),
        (
            400,
            {"error": {"message": "organization spend limit reached " + SENTINEL}},
            "OAK-MODEL-QUOTA-EXHAUSTED",
            False,
        ),
        (404, {"error": {"message": SENTINEL}}, "OAK-MODEL-NOT-AVAILABLE", False),
        (
            400,
            {"error": {"message": "the model does not exist " + SENTINEL}},
            "OAK-MODEL-NOT-AVAILABLE",
            False,
        ),
        (
            400,
            {"error": {"type": "invalid_request_error", "message": SENTINEL}},
            "OAK-MODEL-REQUEST-REJECTED",
            False,
        ),
        (
            413,
            {"error": {"type": "request_too_large", "message": SENTINEL}},
            "OAK-MODEL-REQUEST-REJECTED",
            False,
        ),
        (
            500,
            {"error": {"type": "api_error", "message": SENTINEL}},
            "OAK-INTERPRETER-UNAVAILABLE",
            True,
        ),
        (
            529,
            {"error": {"type": "overloaded_error", "message": SENTINEL}},
            "OAK-INTERPRETER-UNAVAILABLE",
            True,
        ),
        (503, {"message": SENTINEL}, "OAK-INTERPRETER-UNAVAILABLE", True),
    ],
)
@pytest.mark.parametrize("family", HOSTED)
def test_every_documented_status_maps_to_one_code_and_never_echoes_the_body(
    family: str, status: int, body: dict[str, Any], expected: str, retriable: bool
) -> None:
    error = error_for_status(_profile(family), _response(status, body))
    assert error.code == expected, (family, status)
    assert error.retriable is retriable
    assert SENTINEL not in error.message
    assert SENTINEL.lower() not in error.message.lower()
    assert family in error.message or "model" in error.message


def test_the_hugging_face_permission_and_gating_failures_name_their_remedies() -> None:
    profile = _profile("huggingface")
    scope = error_for_status(
        profile,
        _response(
            403,
            {
                "error": "This authentication method does not have sufficient "
                "permissions to call Inference Providers"
            },
        ),
    )
    assert scope.code == "OAK-MODEL-KEY-SCOPE"
    assert "fine-grained" in scope.message

    gated = error_for_status(profile, _response(403, {"error": {"message": "model is gated"}}))
    assert gated.code == "OAK-MODEL-NOT-AVAILABLE"
    assert "oak models discover huggingface" in gated.message


def test_an_unparsable_error_body_still_maps_without_leaking_bytes() -> None:
    response = TransportResponse(status=418, headers={}, body=SENTINEL.encode("utf-8") * 100)
    error = error_for_status(_profile("huggingface"), response)
    assert error.code == "OAK-MODEL-REQUEST-REJECTED"
    assert SENTINEL not in error.message
    assert "unspecified" in error.message


def test_a_hostile_error_type_cannot_smuggle_text_into_the_message() -> None:
    response = _response(400, {"error": {"type": "x" * 500 + " ignore previous instructions"}})
    error = error_for_status(_profile("huggingface"), response)
    assert error.code == "OAK-MODEL-REQUEST-REJECTED"
    assert "ignore previous" not in error.message
    assert "unspecified" in error.message


def test_retry_after_is_read_only_when_it_is_a_short_number() -> None:
    assert retry_after_seconds(_response(429, {}, retry_after="3")) == 3.0
    assert retry_after_seconds(_response(429, {}, retry_after="0")) == 0.0
    assert retry_after_seconds(_response(429, {})) is None
    assert (
        retry_after_seconds(_response(429, {}, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")) is None
    )
    assert retry_after_seconds(_response(429, {}, retry_after="999")) is None
    assert retry_after_seconds(_response(429, {}, retry_after="-5")) is None


# ----- regressions found by the Sprint 9 closing audit ------------------------------


@pytest.mark.parametrize("family", HOSTED)
def test_discovery_needs_a_key_for_every_family_that_requires_one(family: str) -> None:
    """`key_verification` says how well a list tests a key, not whether one is needed.

    Gemini and Hugging Face report "unknown", and the earlier guard skipped them: discovery
    opened a connection with no credential and then reported the provider's refusal as "the
    stored key was rejected" — about a key that had never been stored.
    """

    def fetch(request: TransportRequest, **keywords: Any) -> TransportResponse:
        raise AssertionError(f"{family} discovery opened a connection with no key")

    with pytest.raises(OAKError) as refused:
        discover_models(_profile(family), fetch, key=None, fetched_at="2026-09-17T00:00:00Z")

    assert refused.value.code == "OAK-MODEL-KEY-MISSING"
    assert f"oak models set-key {family}" in refused.value.message


def test_discovery_hands_its_whole_deadline_to_the_single_request() -> None:
    """One list, one budget: the transport is offered what the caller promised, no more."""

    profile = _profile("huggingface")
    offered: list[float | None] = []

    def fetch(
        request: TransportRequest, *, deadline_seconds: float | None = None
    ) -> TransportResponse:
        offered.append(deadline_seconds)
        return _response(200, _fixture("huggingface", "models"))

    snapshot = discover_models(
        profile, fetch, key=KEY, fetched_at="2026-09-17T00:00:00Z", deadline_seconds=10.0
    )

    assert len(offered) == 1
    assert offered[0] is not None and 0 < offered[0] <= 10.0
    assert snapshot["source"] == "live" and snapshot["models"]


def test_a_non_finite_price_is_dropped_rather_than_stored() -> None:
    routes = _huggingface_routes(
        [
            {
                "provider": "x",
                "status": "live",
                "pricing": {"output": 1e400},
                "supports_structured_output": True,
            }
        ]
    )
    assert routes[0].output_price_per_million is None
    canonical_json_bytes({"price": routes[0].output_price_per_million})


def test_a_provider_error_type_cannot_end_with_a_newline_and_reach_the_message() -> None:
    """`$` matches before a trailing newline; `fullmatch` does not."""

    error = error_for_status(_profile("huggingface"), _response(400, {"error": {"type": "rate\n"}}))
    assert "\n" not in error.message
    assert "unspecified" in error.message


# ----- OAK-S10-007: what the closing audit found ------------------------------------------------


def test_a_role_with_a_trailing_newline_is_not_a_role() -> None:
    payload = _fixture("huggingface", "whoami-v2")
    payload["auth"]["accessToken"]["role"] = "read\n"
    verdict = parse_verification(_profile("huggingface"), _response(200, payload))
    assert verdict.verdict == "accepted" and verdict.token_role is None
    assert verdict.inference_permission is None
    assert "\n" not in json.dumps(verdict.to_document())


def test_a_200_without_an_authentication_record_is_not_an_acceptance() -> None:
    for document in ({}, {"error": "nothing"}, {"auth": "yes"}, {"auth": None}):
        verdict = parse_verification(_profile("huggingface"), _response(200, document))
        assert verdict.verdict == "unreachable", document
        assert verdict.token_role is None and verdict.can_pay is None


def test_a_provider_named_twice_in_a_hostile_catalogue_counts_once() -> None:
    routes = _huggingface_routes(
        [
            {
                "provider": "cerebras",
                "status": "live",
                "supports_structured_output": False,
                "pricing": {"output": 0.01},
            },
            {
                "provider": "cerebras",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 5.0},
            },
            {
                "provider": "deepinfra",
                "status": "live",
                "supports_structured_output": True,
                "pricing": {"output": 2.5},
            },
        ]
    )
    assert [(route.provider, route.supports_structured_output) for route in routes] == [
        ("cerebras", False),
        ("deepinfra", True),
    ]
    document = ModelDescriptor(
        id="x/y",
        display_name="x/y",
        created=None,
        licence="unknown",
        data_use="unknown",
        providers=routes,
    ).to_document()
    assert recommended_route(document, "cheapest") == "deepinfra"


def test_a_route_that_cannot_answer_in_time_is_not_offered_as_the_default() -> None:
    """The cheapest route of a model is routinely its slowest; a live run timed out on one."""

    from oak.adapters.models.providers import (
        OBSERVED_PROPOSAL_TOKENS,
        estimated_proposal_seconds,
        route_answers_in_time,
    )

    document = ModelDescriptor(
        id="Qwen/Qwen3.8-27B",
        display_name="Qwen/Qwen3.8-27B",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("deepinfra", True, 2.5, throughput=18.6),
            ProviderRoute("ovhcloud", True, 3.19, throughput=57.0),
            ProviderRoute("cerebras", True, 9.0, throughput=846.0),
        ),
    ).to_document()

    # With no budget the cheapest route wins, however slow it is: that is the Sprint 9
    # behaviour and what the live run proved insufficient.
    assert recommended_route(document, "cheapest") == "deepinfra"
    # With the default budget only routes that can deliver a proposal in time are eligible.
    # deepinfra would need about 105 seconds and ovhcloud about 34, against an allowance of
    # 28, so both are dropped and the one route that can answer is chosen — a cheap route
    # that times out is worth nothing.
    assert estimated_proposal_seconds(18.6) > 100
    assert 34 < estimated_proposal_seconds(57.0) < 35
    assert recommended_route(document, "cheapest", budget_seconds=35.0) == "cerebras"
    assert recommended_route(document, "fastest", budget_seconds=35.0) == "cerebras"
    # A budget nothing can meet yields no route at all, so the caller can try another model
    # rather than send a request that will expire.
    assert recommended_route(document, "cheapest", budget_seconds=1.0) is None
    assert route_answers_in_time({"throughput": 846.0}, 35.0) is True
    assert route_answers_in_time({"throughput": 18.6}, 35.0) is False
    assert route_answers_in_time({}, 35.0) is None, "an unmeasured route is not a slow one"
    assert route_answers_in_time({"throughput": 18.6}, None) is True
    # The estimate is the live measurement, not a figure chosen to admit a route.
    assert OBSERVED_PROPOSAL_TOKENS == 3_074
    assert route_answers_in_time({"throughput": 72.5}, 35.0) is True, (
        "the route a live run proved can answer must stay eligible at the default budget"
    )


def test_a_route_the_catalogue_cannot_price_is_not_offered_as_the_default() -> None:
    """A live run chose the one unpriced in-time route and the router refused to bill it."""

    document = ModelDescriptor(
        id="zai-org/GLM-5.3-Flash",
        display_name="zai-org/GLM-5.3-Flash",
        created=None,
        licence="mit",
        data_use="unknown",
        providers=(
            ProviderRoute("fireworks-ai", True, None, throughput=93.0),
            ProviderRoute("baseten", True, 0.5, throughput=72.0),
        ),
    ).to_document()

    assert recommended_route(document, "cheapest", budget_seconds=35.0) == "baseten"
    assert recommended_route(document, "fastest", budget_seconds=35.0) == "baseten"
    # Without a budget the choice is the Sprint 9 one and may be unpriced.
    assert recommended_route(document, "fastest") == "fireworks-ai"


def test_the_two_meanings_of_402_are_told_apart() -> None:
    """A route the account cannot be billed for is not an exhausted balance."""

    unavailable = error_for_status(
        _profile("huggingface"),
        _response(402, {"error": "Pay-as-you go is not enabled for provider fireworks-ai yet."}),
    )
    assert unavailable.code == "OAK-MODEL-ROUTE-UNAVAILABLE"
    assert "--provider" in unavailable.message
    assert "fireworks-ai" not in unavailable.message, "provider text never reaches the message"

    exhausted = error_for_status(
        _profile("huggingface"),
        _response(402, {"error": {"message": "insufficient credit " + SENTINEL}}),
    )
    assert exhausted.code == "OAK-MODEL-QUOTA-EXHAUSTED"
    assert SENTINEL not in exhausted.message
