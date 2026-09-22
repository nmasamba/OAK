# SPDX-License-Identifier: Apache-2.0
"""The two model families as data: hosts, request shape, parsers and status mapping.

Nothing in this module opens a connection. It builds ``TransportRequest`` values, reads
``TransportResponse`` values, and turns provider status codes into fixed OAK codes. Provider
text is parsed only to choose a code and is then discarded: no message, header or body from
a provider ever reaches an ``OAKError``. The model hints carry an ``as_of`` date because
provider catalogues move; discovery, not this table, decides what a key can reach.

Since Sprint 10 the only hosted family is Hugging Face Inference Providers; the other row is
the local OpenAI-compatible server. Both speak the OpenAI chat-completions shape.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from oak.adapters.models.transport import TransportRequest, TransportResponse, is_loopback_host
from oak.domain import OAKError
from oak.domain.model_families import FAMILY_IDS

RequestShape = Literal["openai_chat"]
KeyVerification = Literal["hub_whoami_v2", "authenticated_models_list", "unknown"]
KeyHeader = Literal["bearer"]

HINTS_AS_OF = "2026-09-16"
WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
INFERENCE_PERMISSION = "inference.serverless.write"
VERDICTS = ("accepted", "rejected", "scope_limited", "unreachable", "unverifiable")
# What a stored verdict says it came from; the local profile's strategy name and the
# stored spelling differ, and the schema closes the list, so the mapping lives here.
VERIFICATION_METHODS = {
    "hub_whoami_v2": "hub_whoami_v2",
    "authenticated_models_list": "models_list",
    "unknown": "unknown",
}
# The one phrase that identifies a 401 (the credential itself refused) as opposed to a
# 403 on a single request; the interpretation wrapper records a verdict only for the first.
KEY_REJECTED_MARKER = "rejected the stored key"
# How long an interpretation takes on a route, estimated from the one measurement there is.
#
# The catalogue publishes each route's measured throughput, so "can this route answer in
# time?" is arithmetic rather than a guess — and the answer matters: the cheapest route of a
# model is routinely its slowest, and a live run against the recommended default timed out at
# 30 seconds on a route that needed 80.
#
# The arithmetic is calibrated against that same run, which produced a 15-claim proposal of
# 3,074 output tokens on a route Hugging Face publishes at 72.5 tokens per second and
# completed inside a 30-second budget. Both figures are used as observed. The correction
# exists because they disagree: 3,074 tokens at the published rate would need 42 seconds, and
# it did not take 42 seconds — the published figure is a floor from Hugging Face's own probe,
# and the route delivered about 1.57 times it.
#
# An earlier version of this table carried an estimate of 1,500 tokens instead, defended on
# the grounds that the observed 3,074 "would exclude every route the catalogue measures".
# That is reasoning from the wanted answer: if honest numbers leave nothing callable, the
# conclusion is that the budget is too small or the catalogue too slow, not that the estimate
# should be understated. What is below is what was measured; the share is the one judgement,
# reserving a fifth of the budget for the prompt, the connection and the provider's queueing.
# One run is one run: `tests/live/` is where this gets corrected, not a comment.
OBSERVED_PROPOSAL_TOKENS = 3_074
PUBLISHED_THROUGHPUT_CORRECTION = 1.57
GENERATION_SHARE_OF_BUDGET = 0.8


def estimated_proposal_seconds(published_throughput: float) -> float:
    """How long a proposal is expected to take on a route publishing this throughput."""

    return OBSERVED_PROPOSAL_TOKENS / (published_throughput * PUBLISHED_THROUGHPUT_CORRECTION)


def route_answers_in_time(route: dict[str, Any], budget_seconds: float | None) -> bool | None:
    """Whether a route can generate a proposal inside the budget. ``None`` when unmeasured."""

    if budget_seconds is None:
        return True
    throughput = _finite_non_negative(route.get("throughput"))
    if not throughput:
        return None
    return estimated_proposal_seconds(throughput) <= budget_seconds * GENERATION_SHARE_OF_BUDGET


TOKEN_ROLE = re.compile(r"^[A-Za-z]{1,40}$")
DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:11434/v1"
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ERROR_TYPE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
ISO_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
LICENCES = frozenset({"apache-2.0", "mit", "bsd-3-clause", "other", "unknown"})
DATA_USES = frozenset({"trains_on_inputs", "not_used_for_training", "unknown"})

# Identifiers that name something other than a chat model on OpenAI-shaped catalogues.
NON_CHAT_TERMS = re.compile(
    r"embed|tts|whisper|transcri|dall-e|image|audio|realtime|moderation|search|codex|"
    r"computer-use|sora|voice|video|vision-only|rerank|guard|speech",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: str
    supports_structured_output: bool
    output_price_per_million: float | None
    is_free: bool = False
    throughput: float | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "supports_structured_output": self.supports_structured_output,
            "output_price_per_million": self.output_price_per_million,
            "is_free": self.is_free,
            "throughput": self.throughput,
        }


@dataclass(frozen=True, slots=True)
class Verdict:
    """What a provider said about a stored credential, and nothing else it said.

    ``accepted`` means the provider authenticated the credential on that request; it does
    not prove credit remains or that any particular model may be called. ``unreachable``
    is not a verdict about the credential at all, and the surfaces say so.
    """

    verdict: str
    method: str
    token_role: str | None = None
    inference_permission: bool | None = None
    can_pay: bool | None = None
    is_pro: bool | None = None
    reason: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "method": self.method,
            "token_role": self.token_role,
            "inference_permission": self.inference_permission,
            "can_pay": self.can_pay,
            "is_pro": self.is_pro,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    id: str
    display_name: str
    created: str | None
    licence: str
    data_use: str
    providers: tuple[ProviderRoute, ...] = ()

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "created": self.created,
            "licence": self.licence,
            "data_use": self.data_use,
            "providers": [route.to_document() for route in self.providers[:32]],
        }


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    family: str
    base_url: str
    allowed_hosts: frozenset[str]
    request_shape: RequestShape
    models_path: str
    chat_path: str
    key_header: KeyHeader
    key_verification: KeyVerification
    preferred_order: tuple[str, ...]
    licence: str
    default_data_use: str
    data_use_overrides: tuple[tuple[str, str], ...] = ()
    credential_required: bool = True
    plain_http_loopback: bool = False
    hints_as_of: str = HINTS_AS_OF

    def data_use_for(self, model_id: str) -> str:
        for candidate, value in self.data_use_overrides:
            if candidate == model_id:
                return value
        return self.default_data_use


_HOSTED_PROFILES: dict[str, ProviderProfile] = {
    "huggingface": ProviderProfile(
        family="huggingface",
        base_url="https://router.huggingface.co/v1",
        allowed_hosts=frozenset({"router.huggingface.co", "huggingface.co"}),
        request_shape="openai_chat",
        models_path="/models",
        chat_path="/chat/completions",
        key_header="bearer",
        key_verification="hub_whoami_v2",
        preferred_order=(
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "Qwen/Qwen3-235B-A22B-Instruct-2507",
        ),
        licence="unknown",
        default_data_use="unknown",
    ),
}


def local_profile(endpoint: str | None) -> ProviderProfile:
    """The local OpenAI-compatible server. Loopback only; plain http allowed there."""

    raw = (endpoint or DEFAULT_LOCAL_ENDPOINT).strip()
    parts = urllib.parse.urlsplit(raw)
    try:
        hostname = (parts.hostname or "").lower()
        parts.port  # noqa: B018 - raises for a malformed port before anything uses it
    except ValueError as error:
        raise OAKError(
            "OAK-MODEL-ENDPOINT-INVALID",
            "OAK_MODEL_ENDPOINT_LOCAL is not a usable URL",
        ) from error
    if (
        parts.scheme not in {"http", "https"}
        or not hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not is_loopback_host(hostname)
    ):
        raise OAKError(
            "OAK-MODEL-ENDPOINT-INVALID",
            "OAK_MODEL_ENDPOINT_LOCAL must be an http(s) URL on a loopback address "
            "(for example http://127.0.0.1:11434/v1) with no credentials in it",
        )
    base = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
    return ProviderProfile(
        family="local",
        base_url=base,
        allowed_hosts=frozenset({hostname}),
        request_shape="openai_chat",
        models_path="/models",
        chat_path="/chat/completions",
        key_header="bearer",
        key_verification="authenticated_models_list",
        preferred_order=(),
        licence="unknown",
        default_data_use="not_used_for_training",
        credential_required=False,
        plain_http_loopback=True,
    )


def profile_for(family: str, *, local_endpoint: str | None = None) -> ProviderProfile:
    if family == "local":
        return local_profile(local_endpoint)
    try:
        return _HOSTED_PROFILES[family]
    except KeyError as error:
        raise OAKError(
            "OAK-MODEL-FAMILY-UNKNOWN",
            f"unknown model family; choose one of {', '.join(FAMILY_IDS)}",
        ) from error


# ----- requests -------------------------------------------------------------------


def auth_headers(profile: ProviderProfile, key: str | None) -> dict[str, str]:
    del profile  # both families carry the key as a bearer token
    if key is None:
        return {}
    return {"Authorization": f"Bearer {key}"}


def models_request(profile: ProviderProfile, key: str | None) -> TransportRequest:
    return TransportRequest(
        method="GET",
        url=f"{profile.base_url}{profile.models_path}",
        headers=auth_headers(profile, key),
    )


def key_verification_request(profile: ProviderProfile, key: str | None) -> TransportRequest | None:
    """A free request that fails on a bad credential, where the provider documents one.

    Hugging Face: the Hub's ``whoami-v2`` — it authenticates the token, names its role and
    the account's billing state, and generates nothing. The local server: its models list,
    which answers only when the endpoint is up and accepts whatever key it was given.
    """

    if profile.key_verification == "hub_whoami_v2":
        return TransportRequest(method="GET", url=WHOAMI_URL, headers=auth_headers(profile, key))
    if profile.key_verification == "authenticated_models_list":
        return models_request(profile, key)
    return None


def parse_verification(profile: ProviderProfile, response: TransportResponse) -> Verdict:
    """The verdict a verification response carries. Every other byte of it is discarded."""

    if profile.key_verification == "hub_whoami_v2":
        return _parse_whoami(response)
    return _parse_models_list_verification(profile, response)


def _parse_whoami(response: TransportResponse) -> Verdict:
    method = "hub_whoami_v2"
    if response.status == 401:
        return Verdict("rejected", method, reason="Hugging Face did not accept this token (401)")
    if response.status == 403:
        return Verdict(
            "scope_limited",
            method,
            reason=(
                "Hugging Face accepted the token but refused this request (403); it may "
                "lack permission to read its own account"
            ),
        )
    if response.status == 429:
        return Verdict(
            "unreachable", method, reason="the Hub is rate limiting this token; try again shortly"
        )
    if response.status != 200:
        return Verdict(
            "unreachable", method, reason=f"the Hub answered with status {response.status}"
        )
    document = parse_json(response)
    if not isinstance(document, dict) or not isinstance(document.get("auth"), dict):
        # A 200 that carries no authentication record is not evidence the token was
        # accepted, whatever else it says.
        return Verdict("unreachable", method, reason="the Hub's answer could not be read")
    auth = document["auth"]
    token = auth.get("accessToken") if isinstance(auth, dict) else None
    role_value = token.get("role") if isinstance(token, dict) else None
    role = role_value if isinstance(role_value, str) and TOKEN_ROLE.fullmatch(role_value) else None
    permission: bool | None
    if role in {"read", "write"}:
        permission = True
    elif role == "fineGrained":
        permission = _fine_grained_inference_permission(
            token.get("fineGrained") if isinstance(token, dict) else None
        )
    else:
        permission = None
    return Verdict(
        "accepted",
        method,
        token_role=role,
        inference_permission=permission,
        can_pay=_boolean(document.get("canPay")),
        is_pro=_boolean(document.get("isPro")),
    )


def _fine_grained_inference_permission(fine_grained: Any) -> bool | None:
    """Whether a fine-grained token may call Inference Providers, when the Hub says.

    The Hub does say, though it does not document that it does: observed live on 2026-09-22,
    the permission arrives under ``scoped[].permissions`` — the list of what the token may do
    to a named entity — and not under ``global``. Both are read, because neither placement is
    promised; a token whose scopes are reported without the permission is a definite ``False``
    and one whose scopes are not reported at all stays ``None``.
    """

    if not isinstance(fine_grained, dict):
        return None
    found = False
    listed = False
    for item in (
        fine_grained.get("global", []) if isinstance(fine_grained.get("global"), list) else []
    ):
        listed = True
        if item == INFERENCE_PERMISSION:
            found = True
    scoped = fine_grained.get("scoped")
    for entry in scoped if isinstance(scoped, list) else []:
        permissions = entry.get("permissions") if isinstance(entry, dict) else None
        for item in permissions if isinstance(permissions, list) else []:
            listed = True
            if item == INFERENCE_PERMISSION:
                found = True
    if found:
        return True
    return False if listed else None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _parse_models_list_verification(
    profile: ProviderProfile, response: TransportResponse
) -> Verdict:
    method = "models_list"
    if response.status == 200:
        return Verdict("accepted", method)
    if response.status in {401, 403}:
        return Verdict(
            "rejected", method, reason=f"the {profile.family} server refused the credential"
        )
    return Verdict(
        "unreachable",
        method,
        reason=f"the {profile.family} server answered with status {response.status}",
    )


def chat_request(
    profile: ProviderProfile,
    model_id: str,
    *,
    key: str | None,
    system_prompt: str,
    user_content: str,
    response_schema: dict[str, Any],
    schema_name: str,
    max_tokens: int,
) -> TransportRequest:
    headers = {"Content-Type": "application/json", **auth_headers(profile, key)}
    body: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": response_schema, "strict": True},
        },
        "max_tokens": max_tokens,
    }
    if profile.family == "huggingface":
        body["stream"] = False
    return TransportRequest(
        method="POST",
        url=f"{profile.base_url}{profile.chat_path}",
        headers=headers,
        body=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


# ----- responses ------------------------------------------------------------------


def parse_json(response: TransportResponse) -> Any:
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    except RecursionError:
        # Deeply nested provider JSON exhausts the stack. `RecursionError` is a
        # `RuntimeError`, so it would otherwise escape every `except ValueError` guard
        # between here and the interface.
        return None


def parse_models(
    profile: ProviderProfile, response: TransportResponse
) -> tuple[list[dict[str, Any]], str | None]:
    """Raw catalogue entries and the next page token, or a fixed OAK error.

    Neither remaining family paginates its list, so the token is always ``None``; the
    shape is kept so a paginated family can be added without changing every caller.
    """

    if response.status != 200:
        raise error_for_status(profile, response)
    document = parse_json(response)
    if not isinstance(document, dict):
        raise OAKError(
            "OAK-MODEL-DISCOVERY-UNAVAILABLE",
            "the provider's model list could not be read",
            retriable=True,
        )
    entries = document.get("data")
    if entries is None:
        entries = document.get("models")
    if not isinstance(entries, list):
        raise OAKError(
            "OAK-MODEL-DISCOVERY-UNAVAILABLE",
            "the provider's model list could not be read",
            retriable=True,
        )
    return [entry for entry in entries if isinstance(entry, dict)], None


def descriptor_from(profile: ProviderProfile, raw: dict[str, Any]) -> ModelDescriptor | None:
    """A snapshot entry for a chat-capable model, or ``None`` when the entry is not one."""

    identifier = raw.get("id")
    if not isinstance(identifier, str):
        return None
    if not _is_model_identifier(identifier):
        return None
    if not _is_chat_candidate(profile, identifier, raw):
        return None
    display = raw.get("display_name") or raw.get("displayName") or identifier
    display_name = str(display)[:200] or identifier[:200]
    created = _created(raw.get("created"))
    providers: tuple[ProviderRoute, ...] = ()
    if profile.family == "huggingface":
        providers = _huggingface_routes(raw.get("providers"))
        if not providers:
            return None
    return ModelDescriptor(
        id=identifier,
        display_name=display_name,
        created=created,
        licence=profile.licence,
        data_use=profile.data_use_for(identifier),
        providers=providers,
    )


def _is_model_identifier(identifier: str) -> bool:
    """A bare name or one `namespace/name`. Never a URL, a path, or a multi-segment id."""

    return (
        bool(MODEL_ID.match(identifier))
        and len(identifier) <= 256
        and identifier.count("/") <= 1
        and "//" not in identifier
        and "://" not in identifier
    )


def _is_chat_candidate(profile: ProviderProfile, identifier: str, raw: dict[str, Any]) -> bool:
    del raw  # neither remaining catalogue carries a capability field worth reading here
    if profile.family == "huggingface":
        # The router lists chat-completion models only; the route filter decides the rest.
        return True
    return not NON_CHAT_TERMS.search(identifier.lower())


def _huggingface_routes(value: Any) -> tuple[ProviderRoute, ...]:
    if not isinstance(value, list):
        return ()
    routes: list[ProviderRoute] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict) or entry.get("status") != "live":
            continue
        provider = entry.get("provider")
        if not isinstance(provider, str) or not PROVIDER_NAME.match(provider):
            continue
        if provider in seen:
            # One entry per provider: a hostile catalogue that names a provider twice with
            # different capabilities or prices must not let the shown price and the chosen
            # route come from different entries.
            continue
        seen.add(provider)
        pricing = entry.get("pricing")
        output_price = (
            _finite_non_negative(pricing.get("output")) if isinstance(pricing, dict) else None
        )
        routes.append(
            ProviderRoute(
                provider=provider,
                supports_structured_output=entry.get("supports_structured_output") is True,
                output_price_per_million=output_price,
                is_free=entry.get("is_free") is True,
                throughput=_finite_non_negative(entry.get("throughput")),
            )
        )
        if len(routes) == 32:
            break
    return tuple(routes)


def _finite_non_negative(value: Any) -> float | None:
    """A catalogue number OAK will store, or ``None``: never a bool, NaN, infinity or a negative."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _created(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 0 < value < 4_102_444_800:
        return datetime.fromtimestamp(int(value), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and ISO_DATE_TIME.match(value):
        return value
    return None


def extract_text(
    profile: ProviderProfile, response: TransportResponse
) -> tuple[str, dict[str, int | None]]:
    """The model's text output and token usage, or a fixed OAK error."""

    if response.status != 200:
        raise error_for_status(profile, response)
    document = parse_json(response)
    if not isinstance(document, dict):
        raise OAKError("OAK-INTERPRETER-MALFORMED", "the provider returned an unusable response")
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise OAKError("OAK-INTERPRETER-MALFORMED", "the provider returned no completion")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise OAKError("OAK-INTERPRETER-MALFORMED", "the provider returned no completion")
    if message.get("refusal"):
        raise OAKError("OAK-INTERPRETER-MALFORMED", "the model declined to answer")
    if choice.get("finish_reason") == "length":
        raise OAKError("OAK-INTERPRETER-OUTPUT-LIMIT", "the model's answer was truncated")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    usage = document.get("usage")
    return _non_empty(str(content or "")), {
        "input_tokens": _token_count(usage, "prompt_tokens"),
        "output_tokens": _token_count(usage, "completion_tokens"),
    }


def _non_empty(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise OAKError("OAK-INTERPRETER-MALFORMED", "the model returned an empty answer")
    return stripped


def _token_count(usage: Any, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


# ----- status mapping -------------------------------------------------------------


def retry_after_seconds(response: TransportResponse) -> float | None:
    value = response.header("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if 0 <= seconds <= 60 else None


def _error_fields(response: TransportResponse) -> tuple[str, str, str]:
    """(type, code, message) from a provider error body, lowercased; empty when absent."""

    document = parse_json(response)
    if not isinstance(document, dict):
        return "", "", ""
    error = document.get("error")
    if isinstance(error, list) and error and isinstance(error[0], dict):
        error = error[0].get("error", error[0])
    if isinstance(error, str):
        error = {"message": error}
    if not isinstance(error, dict):
        error = document
    kind = error.get("type") or error.get("status") or ""
    code = error.get("code") or ""
    message = error.get("message") or document.get("message") or document.get("detail") or ""
    return str(kind).lower(), str(code).lower(), str(message).lower()


def error_for_status(profile: ProviderProfile, response: TransportResponse) -> OAKError:
    """Map a non-2xx provider response to a fixed OAK error. Provider text never survives."""

    status = response.status
    kind, code, message = _error_fields(response)
    quota_words = ("credit", "quota", "billing", "insufficient", "spend limit", "payment")
    if status == 401:
        return OAKError(
            "OAK-MODEL-KEY-REJECTED",
            f"the {profile.family} provider {KEY_REJECTED_MARKER}; store a current key with "
            f"`oak models set-key {profile.family}`",
        )
    if status == 403:
        if profile.family == "huggingface" and (
            "permission" in message or "inference providers" in message
        ):
            return OAKError(
                "OAK-MODEL-KEY-SCOPE",
                "the Hugging Face token lacks the 'Make calls to Inference Providers' "
                "permission; create a fine-grained token with that permission and store it "
                "with `oak models set-key huggingface`",
            )
        if profile.family == "huggingface" and "gated" in message:
            return OAKError(
                "OAK-MODEL-NOT-AVAILABLE",
                "the selected model is gated for this account; accept its licence on the "
                "Hugging Face model page or run `oak models discover huggingface` and select "
                "an ungated model",
            )
        return OAKError(
            "OAK-MODEL-KEY-REJECTED",
            f"the {profile.family} provider refused the stored key for this request",
        )
    unavailable_route_words = ("not enabled", "not available", "not supported for", "no provider")
    if status == 402 and any(word in message for word in unavailable_route_words):
        # A 402 is not always "top up": the router answers one when the account cannot be
        # billed for *this provider* even though it has credit. Telling such a user their
        # credit has run out sends them to the wrong page; the remedy is another route.
        return OAKError(
            "OAK-MODEL-ROUTE-UNAVAILABLE",
            "this provider route is not available for pay-as-you-go on the Hugging Face "
            "account; pick another with `oak models select huggingface <model_id> "
            "--provider <route>`, or `oak models clear huggingface` for the preferred pair",
        )
    if status == 402 or (
        status in {400, 429}
        and (
            any(word in message for word in quota_words)
            or any(word in code for word in quota_words)
        )
    ):
        return OAKError(
            "OAK-MODEL-QUOTA-EXHAUSTED",
            f"the {profile.family} account has no remaining credit or exceeded its spend limit",
        )
    if status == 429:
        return OAKError(
            "OAK-MODEL-RATE-LIMITED",
            f"the {profile.family} provider is rate limiting this key; retry shortly",
            retriable=True,
        )
    if status == 404 or (
        status == 400
        and "model" in message
        and any(
            phrase in message
            for phrase in (
                "not found",
                "does not exist",
                "unknown",
                "unsupported",
                "not supported",
                "invalid model",
            )
        )
    ):
        return OAKError(
            "OAK-MODEL-NOT-AVAILABLE",
            "the selected model is not available to this key; run "
            f"`oak models discover {profile.family}` and select a listed model",
        )
    if status in {408, 409, 500, 502, 503, 504, 529} or status >= 500:
        return OAKError(
            "OAK-INTERPRETER-UNAVAILABLE",
            f"the {profile.family} provider is unavailable or overloaded",
            retriable=True,
        )
    label = kind if ERROR_TYPE.fullmatch(kind) else "unspecified"
    return OAKError(
        "OAK-MODEL-REQUEST-REJECTED",
        f"the {profile.family} provider rejected the request (status {status}, type {label})",
    )


# ----- generic discovery ------------------------------------------------------------


def discover_models(
    profile: ProviderProfile,
    fetch: Any,
    *,
    key: str | None,
    fetched_at: str,
    deadline_seconds: float | None = None,
) -> dict[str, Any]:
    """A discovery snapshot from the provider's own catalogue.

    ``fetch`` is ``ModelTransport.send``. One request: neither remaining family paginates.
    """

    if profile.credential_required and key is None:
        # `key_verification` says how well a models list tests a key, not whether the family
        # needs one. Without this, a family whose verification is "unknown" opened a
        # connection with no credential and reported the provider's 401 as "the stored key
        # was refused" — about a key that was never stored.
        raise OAKError(
            "OAK-MODEL-KEY-MISSING",
            f"listing {profile.family} models needs a stored key; run "
            f"`oak models set-key {profile.family}` first",
        )
    started = time.monotonic()
    if deadline_seconds is not None:
        remaining = float(deadline_seconds) - (time.monotonic() - started)
        if remaining <= 0.05:
            raise OAKError(
                "OAK-MODEL-DISCOVERY-UNAVAILABLE",
                f"listing {profile.family} models did not finish within its deadline",
                retriable=True,
            )
        response = fetch(models_request(profile, key), deadline_seconds=remaining)
    else:
        response = fetch(models_request(profile, key))
    entries, _ = parse_models(profile, response)
    descriptors: list[ModelDescriptor] = []
    filtered_out = 0
    for entry in entries:
        descriptor = descriptor_from(profile, entry)
        if descriptor is None:
            filtered_out += 1
        else:
            descriptors.append(descriptor)
    unique: dict[str, ModelDescriptor] = {}
    for descriptor in descriptors:
        unique.setdefault(descriptor.id, descriptor)
    ordered = _rank(profile, list(unique.values()))
    return {
        "fetched_at": fetched_at,
        "source": "live",
        "recommended": ordered[0].id if ordered else None,
        "filtered_out_count": filtered_out,
        "models": [descriptor.to_document() for descriptor in ordered[:200]],
    }


def _rank(profile: ProviderProfile, descriptors: list[ModelDescriptor]) -> list[ModelDescriptor]:
    """Preferred ids first in their documented order, then the newest, then by id."""

    preferred = {identifier: index for index, identifier in enumerate(profile.preferred_order)}

    def key(descriptor: ModelDescriptor) -> tuple[int, int, str, str]:
        rank = preferred.get(descriptor.id, len(preferred))
        created = descriptor.created or ""
        # Newest first: sort ascending by rank, then descending by created via a tuple of
        # the complemented characters.
        inverted = "".join(chr(0x10FFFF - ord(character)) for character in created)
        return (rank, 0 if created else 1, inverted, descriptor.id)

    return sorted(descriptors, key=key)


def recommended_route(
    descriptor_document: dict[str, Any] | None,
    policy: str,
    *,
    budget_seconds: float | None = None,
) -> str | None:
    """The Hugging Face provider to call for structured output, or ``None``.

    A route is considered only when it supports structured output **and** can plausibly
    generate a proposal inside ``budget_seconds``; a route the catalogue has not measured is
    considered, because an unmeasured route is not a slow one. Among those, ``cheapest``
    takes a route flagged free while a promotion lasts, else the lowest published output
    price; ``fastest`` takes the highest measured throughput.

    ``None`` means this model cannot be called in time, which is a usable answer: the caller
    moves to the next model rather than sending a request that will expire.
    """

    if not descriptor_document:
        return None
    capable = [
        route
        for route in descriptor_document.get("providers", [])
        if isinstance(route, dict) and route.get("supports_structured_output") is True
    ]
    capable = [
        route for route in capable if route_answers_in_time(route, budget_seconds) is not False
    ]
    if budget_seconds is not None:
        # A route the catalogue does not price is a route Hugging Face may not be able to
        # bill: a live run chose the one unpriced route that could answer in time and the
        # router refused it with 402 "pay-as-you go is not enabled for provider …". An
        # unpriced route can still be pinned deliberately; it is not offered as the default,
        # which also means the user always sees a price beside the pair they will be charged
        # for.
        capable = [
            route
            for route in capable
            if _finite_non_negative(route.get("output_price_per_million")) is not None
        ]
    if not capable:
        return None
    if policy == "fastest":
        measured = [route for route in capable if _finite_non_negative(route.get("throughput"))]
        if measured:
            return str(
                max(
                    measured,
                    key=lambda route: (float(route["throughput"]), str(route["provider"])),
                )["provider"]
            )
        return str(capable[0]["provider"])
    free = [route for route in capable if route.get("is_free") is True]
    pool = free or capable
    priced = [route for route in pool if route.get("output_price_per_million") is not None]
    if priced:
        return str(
            min(
                priced,
                key=lambda route: (
                    float(route["output_price_per_million"]),
                    str(route["provider"]),
                ),
            )["provider"]
        )
    return str(pool[0]["provider"])
