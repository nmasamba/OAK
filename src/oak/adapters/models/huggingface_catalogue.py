# SPDX-License-Identifier: Apache-2.0
"""Find the current top open chat model on Hugging Face, without trusting what comes back.

Both catalogue calls are anonymous reads of public metadata (the router's chat catalogue and
the Hub's model list in trending order); no brief and no credential is sent. Model-card
metadata is written by model authors, so every field is treated as untrusted: values are
checked against closed enumerations and bounded before they reach the configuration file.
When the Hub cannot be reached the pinned chain below is returned with ``source: "pinned"``
so the user can still select a model; the snapshot then says so rather than pretending it
was looked up.

What survives the filter: a model the router serves, listed by the Hub as conversational
and served by at least one provider, not gated, from a namespace on the trusted list, with
at least one live route that supports structured output. The licence is recorded from the
model card and shown, not used to exclude: Online AI prefers the current top model, and the
user picks any pair with the licence in front of them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from oak.adapters.models.providers import (
    ModelDescriptor,
    ProviderRoute,
    descriptor_from,
    parse_json,
    profile_for,
)
from oak.adapters.models.transport import TransportRequest, TransportResponse
from oak.domain import OAKError

Fetch = Callable[..., TransportResponse]

ROUTER_MODELS_URL = "https://router.huggingface.co/v1/models"
HUB_MODELS_URL = (
    "https://huggingface.co/api/models?inference_provider=all&filter=conversational"
    "&sort=trendingScore&direction=-1&limit=100"
    "&expand[]=cardData&expand[]=gated&expand[]=inferenceProviderMapping"
)
PERMISSIVE_LICENCES = frozenset({"apache-2.0", "mit", "bsd-3-clause"})
# Organisations that publish open weights under their own name. Read against the Hub's
# trending list on the date below; a namespace outside this set is never offered, however
# high it trends, because a card is author-controlled and a fine-tune can carry any name.
TRUSTED_NAMESPACES_AS_OF = "2026-09-21"
TRUSTED_NAMESPACES = frozenset(
    {
        "openai",
        "Qwen",
        "mistralai",
        "google",
        "deepseek-ai",
        "zai-org",
        "moonshotai",
        "meta-llama",
        "MiniMaxAI",
        "inclusionAI",
        "tencent",
        "thinkingmachines",
        "ibm-granite",
        "microsoft",
        "nvidia",
        "allenai",
        "HuggingFaceTB",
    }
)
PINNED_AS_OF = "2026-09-21"
# The fallback chain: the top trending, ungated, permissively licensed models with live
# structured-output routes on the date above, with those routes' published output prices
# (USD per million tokens) and measured throughput (tokens per second). Hints, not a quote.
PINNED_MODELS: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        id="Qwen/Qwen3.8-27B",
        display_name="Qwen/Qwen3.8-27B",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("cerebras", True, 1.49, throughput=846.0),
            ProviderRoute("deepinfra", True, 2.5, throughput=40.0),
            ProviderRoute("ovhcloud", True, 3.19, throughput=71.0),
        ),
    ),
    ModelDescriptor(
        id="zai-org/GLM-5.3-Flash",
        display_name="zai-org/GLM-5.3-Flash",
        created=None,
        licence="mit",
        data_use="unknown",
        providers=(
            ProviderRoute("baseten", True, 0.5, throughput=72.0),
            ProviderRoute("deepinfra", True, 0.5, throughput=15.0),
            ProviderRoute("fireworks-ai", True, None, throughput=93.0),
        ),
    ),
    ModelDescriptor(
        id="openai/gpt-oss-120b",
        display_name="openai/gpt-oss-120b",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("deepinfra", True, 0.17, throughput=48.0),
            ProviderRoute("novita", True, 0.25, throughput=82.0),
            ProviderRoute("nscale", True, 0.4, throughput=113.0),
            ProviderRoute("ovhcloud", True, 0.47, throughput=111.0),
            ProviderRoute("baseten", True, 0.5, throughput=182.0),
            ProviderRoute("together", True, 0.6, throughput=104.0),
            ProviderRoute("fireworks-ai", True, 0.6, throughput=159.0),
            ProviderRoute("scaleway", True, 0.684, throughput=160.0),
            ProviderRoute("groq", True, 0.75, throughput=427.0),
            ProviderRoute("cerebras", True, 0.75, throughput=1124.0),
        ),
    ),
)
PINNED_BY_ID = {descriptor.id: descriptor for descriptor in PINNED_MODELS}
UNREACHABLE_CODES = frozenset(
    {
        "OAK-INTERPRETER-UNAVAILABLE",
        "OAK-INTERPRETER-OUTPUT-LIMIT",
        "OAK-MODEL-DISCOVERY-UNAVAILABLE",
        "OAK-MODEL-RATE-LIMITED",
    }
)


def pinned_snapshot(fetched_at: str) -> dict[str, Any]:
    return {
        "fetched_at": fetched_at,
        "source": "pinned",
        "recommended": PINNED_MODELS[0].id,
        "filtered_out_count": 0,
        "models": [descriptor.to_document() for descriptor in PINNED_MODELS],
    }


def discover_huggingface(
    fetch: Fetch, *, fetched_at: str, deadline_seconds: float | None = None
) -> dict[str, Any]:
    """A live snapshot when the catalogues answer; the pinned chain when they do not.

    Both reads share one budget: two full per-request deadlines would be twice the total the
    configuration promises for a single discovery. ``recommended`` is the preferred model:
    the first survivor in the Hub's trending order.
    """

    profile = profile_for("huggingface")
    started = time.monotonic()

    def read(url: str) -> TransportResponse:
        request = TransportRequest(method="GET", url=url)
        if deadline_seconds is None:
            return fetch(request)
        remaining = float(deadline_seconds) - (time.monotonic() - started)
        if remaining <= 0.05:
            raise OAKError(
                "OAK-MODEL-DISCOVERY-UNAVAILABLE",
                "the Hugging Face catalogue did not answer within its deadline",
                retriable=True,
            )
        return fetch(request, deadline_seconds=remaining)

    try:
        router = read(ROUTER_MODELS_URL)
        hub = read(HUB_MODELS_URL)
    except OAKError as error:
        if error.code in UNREACHABLE_CODES:
            return pinned_snapshot(fetched_at)
        raise
    served = _router_catalogue(profile, router)
    hub_entries = _hub_entries(hub)
    if not served or not hub_entries:
        # Without both catalogues there is no filter, and a snapshot built from the pins
        # alone is a pinned answer. Labelling it `live` would tell the user their gating
        # and namespace checks ran when they did not.
        return pinned_snapshot(fetched_at)

    candidates: dict[str, ModelDescriptor] = {}
    for entry in hub_entries:
        identifier = entry["id"]
        descriptor = served.get(identifier)
        if descriptor is None or identifier in candidates:
            continue
        if entry["gated"]:
            continue
        if identifier.split("/", 1)[0] not in TRUSTED_NAMESPACES:
            continue
        if not any(route.supports_structured_output for route in descriptor.providers):
            continue
        candidates[identifier] = ModelDescriptor(
            id=descriptor.id,
            display_name=descriptor.display_name,
            created=descriptor.created,
            licence=entry["licence"],
            data_use=descriptor.data_use,
            providers=descriptor.providers,
        )
    # The pinned chain was ungated and trusted when it was recorded, and the trending page
    # does not always list it, so a pinned model the router still serves is kept even when
    # the Hub listing did not mention it. What is *not* done is overriding the Hub: if the
    # listing says a pinned model is now gated, the pin does not rescue it — a stale constant
    # must never re-admit a model today's catalogue rejects.
    rejected = {entry["id"] for entry in hub_entries if entry["id"] not in candidates}
    for pinned in PINNED_MODELS:
        descriptor = served.get(pinned.id)
        if descriptor is None or pinned.id in candidates or pinned.id in rejected:
            continue
        if any(route.supports_structured_output for route in descriptor.providers):
            candidates[pinned.id] = ModelDescriptor(
                id=descriptor.id,
                display_name=descriptor.display_name,
                created=descriptor.created,
                licence=pinned.licence,
                data_use=descriptor.data_use,
                providers=descriptor.providers,
            )
    if not candidates:
        return pinned_snapshot(fetched_at)
    ordered = _rank(list(candidates.values()), [entry["id"] for entry in hub_entries])
    return {
        "fetched_at": fetched_at,
        "source": "live",
        "recommended": ordered[0].id,
        "filtered_out_count": max(0, len(served) - len(ordered)),
        "models": [descriptor.to_document() for descriptor in ordered[:200]],
    }


def _router_catalogue(profile: Any, response: TransportResponse) -> dict[str, ModelDescriptor]:
    if response.status != 200:
        return {}
    document = parse_json(response)
    entries = document.get("data") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return {}
    served: dict[str, ModelDescriptor] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        descriptor = descriptor_from(profile, raw)
        if descriptor is not None:
            served.setdefault(descriptor.id, descriptor)
    return served


def _hub_entries(response: TransportResponse) -> list[dict[str, Any]]:
    if response.status != 200:
        return []
    document = parse_json(response)
    if not isinstance(document, list):
        return []
    entries: list[dict[str, Any]] = []
    for raw in document:
        if not isinstance(raw, dict):
            continue
        identifier = raw.get("id") or raw.get("modelId")
        if not isinstance(identifier, str) or "/" not in identifier or len(identifier) > 256:
            continue
        gated = raw.get("gated")
        card = raw.get("cardData")
        licence_value = card.get("license") if isinstance(card, dict) else None
        if isinstance(licence_value, list):
            # A model card may declare several licences, and they are cumulative: one
            # restrictive entry restricts the model however permissive the first entry is,
            # so a mixed list is recorded as `other`, never as its most generous member.
            values = [str(item).strip().lower() for item in licence_value if isinstance(item, str)]
            licence_value = (
                values[0]
                if values and all(value in PERMISSIVE_LICENCES for value in values)
                else ("other" if values else None)
            )
        licence = str(licence_value).strip().lower() if isinstance(licence_value, str) else ""
        entries.append(
            {
                "id": identifier,
                "gated": gated not in (False, None, "false"),
                "licence": licence
                if licence in PERMISSIVE_LICENCES
                else ("other" if licence else "unknown"),
            }
        )
    return entries


def _rank(descriptors: list[ModelDescriptor], hub_order: list[str]) -> list[ModelDescriptor]:
    """The Hub's trending order first; a pinned model the Hub did not list comes after."""

    hub_rank = {identifier: index for index, identifier in enumerate(hub_order)}
    pinned_rank = {descriptor.id: index for index, descriptor in enumerate(PINNED_MODELS)}

    def key(descriptor: ModelDescriptor) -> tuple[int, int, int, str]:
        structured = sum(1 for route in descriptor.providers if route.supports_structured_output)
        return (
            hub_rank.get(descriptor.id, len(hub_rank)),
            pinned_rank.get(descriptor.id, len(pinned_rank)),
            -structured,
            descriptor.id,
        )

    return sorted(descriptors, key=key)
