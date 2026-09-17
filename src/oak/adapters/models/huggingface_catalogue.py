# SPDX-License-Identifier: Apache-2.0
"""Find a free, permissively licensed, structured-output-capable chat model on Hugging Face.

Both catalogue calls are anonymous reads of public metadata (the router's chat catalogue and
the Hub's model list); no brief and no credential is sent. Model-card metadata is written by
model authors, so every field is treated as untrusted: values are checked against closed
enumerations and bounded before they reach the configuration file. When the Hub cannot be
reached the pinned chain below is returned with ``source: "pinned"`` so the user can still
select a model; the snapshot then says so rather than pretending it was looked up.
"""

from __future__ import annotations

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

Fetch = Callable[[TransportRequest], TransportResponse]

ROUTER_MODELS_URL = "https://router.huggingface.co/v1/models"
HUB_MODELS_URL = (
    "https://huggingface.co/api/models?inference_provider=all&filter=conversational"
    "&sort=trendingScore&direction=-1&limit=100"
    "&expand[]=cardData&expand[]=gated&expand[]=inferenceProviderMapping"
)
PERMISSIVE_LICENCES = frozenset({"apache-2.0", "mit", "bsd-3-clause"})
TRUSTED_NAMESPACES = frozenset(
    {
        "openai",
        "Qwen",
        "mistralai",
        "google",
        "deepseek-ai",
        "zai-org",
        "ibm-granite",
        "microsoft",
        "nvidia",
        "allenai",
        "HuggingFaceTB",
    }
)
PINNED_AS_OF = "2026-09-16"
# The fallback chain, with the providers that supported structured output for each model
# on the date above. Prices are the providers' published output prices then; they are hints,
# not a quote.
PINNED_MODELS: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        id="openai/gpt-oss-120b",
        display_name="openai/gpt-oss-120b",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("deepinfra", True, 0.17),
            ProviderRoute("ovhcloud", True, 0.47),
            ProviderRoute("baseten", True, 0.50),
            ProviderRoute("together", True, 0.60),
            ProviderRoute("fireworks-ai", True, 0.60),
            ProviderRoute("scaleway", True, 0.684),
            ProviderRoute("groq", True, 0.75),
            ProviderRoute("cerebras", True, 0.75),
        ),
    ),
    ModelDescriptor(
        id="openai/gpt-oss-20b",
        display_name="openai/gpt-oss-20b",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("deepinfra", True, 0.14),
            ProviderRoute("novita", True, 0.15),
            ProviderRoute("ovhcloud", True, 0.18),
            ProviderRoute("nscale", True, 0.20),
            ProviderRoute("groq", True, 0.50),
        ),
    ),
    ModelDescriptor(
        id="Qwen/Qwen3-235B-A22B-Instruct-2507",
        display_name="Qwen/Qwen3-235B-A22B-Instruct-2507",
        created=None,
        licence="apache-2.0",
        data_use="unknown",
        providers=(
            ProviderRoute("deepinfra", True, 0.55),
            ProviderRoute("novita", True, 0.58),
            ProviderRoute("nscale", True, 0.60),
            ProviderRoute("scaleway", True, 2.565),
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


def discover_huggingface(fetch: Fetch, *, fetched_at: str) -> dict[str, Any]:
    """A live snapshot when the catalogues answer; the pinned chain when they do not."""

    profile = profile_for("huggingface")
    try:
        router = fetch(TransportRequest(method="GET", url=ROUTER_MODELS_URL))
        hub = fetch(TransportRequest(method="GET", url=HUB_MODELS_URL))
    except OAKError as error:
        if error.code in UNREACHABLE_CODES:
            return pinned_snapshot(fetched_at)
        raise
    served = _router_catalogue(profile, router)
    hub_entries = _hub_entries(hub)
    if not served or not hub_entries:
        # Without both catalogues there is no filter, and a snapshot built from the pins
        # alone is a pinned answer. Labelling it `live` would tell the user their licence
        # and gating checks ran when they did not.
        return pinned_snapshot(fetched_at)

    candidates: dict[str, ModelDescriptor] = {}
    for entry in hub_entries:
        identifier = entry["id"]
        descriptor = served.get(identifier)
        if descriptor is None or identifier in candidates:
            continue
        if entry["gated"] or entry["licence"] not in PERMISSIVE_LICENCES:
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
    # The pinned chain was permissively licensed and ungated when it was recorded, and the
    # trending page does not always list it, so a pinned model the router still serves is
    # kept even when the Hub listing did not mention it. What is *not* done is overriding
    # the Hub: if the listing says a pinned model is now gated or has been relicensed, the
    # pin does not rescue it — a stale constant must never re-admit a model today's
    # catalogue rejects.
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
            # restrictive entry restricts the model however permissive the first entry is.
            values = [str(item).strip().lower() for item in licence_value if isinstance(item, str)]
            licence_value = (
                values[0]
                if values and all(value in PERMISSIVE_LICENCES for value in values)
                else None
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
    pinned_rank = {descriptor.id: index for index, descriptor in enumerate(PINNED_MODELS)}
    hub_rank = {identifier: index for index, identifier in enumerate(hub_order)}

    def key(descriptor: ModelDescriptor) -> tuple[int, int, int, str]:
        structured = sum(1 for route in descriptor.providers if route.supports_structured_output)
        return (
            pinned_rank.get(descriptor.id, len(pinned_rank)),
            -structured,
            hub_rank.get(descriptor.id, len(hub_rank)),
            descriptor.id,
        )

    return sorted(descriptors, key=key)
