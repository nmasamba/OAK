# SPDX-License-Identifier: Apache-2.0
"""What a research run may send, derived from the confirmed intent (Sprint 14, ADR-0018).

``derive_research_terms`` is pure. It reads the intent's hardware section and the closed
vocabularies, and nothing else: no brief text, no identifier, no credential. Every string in
the ``sent`` block is a value from the capability map or the licence list; the ``local``
block is used on this machine only. The consent card shows this document verbatim and the
audit event records its digest, so what the user agreed to and what was sent are one object.
"""

import hashlib
import json
from typing import Any

from oak.domain import OAKError, ResearchVocabulary

TERMS_VERSION = "community-research-terms-1.0.0"
DEFAULT_FRESHNESS_WINDOW_DAYS = 180
HUB_SORT = "createdAt"
HUB_INFERENCE_PROVIDER = "all"
# Literal query values that are not vocabulary entries but are fixed here, so a guard can
# hold every sent string to the vocabulary plus exactly this set.
FIXED_QUERY_VALUES = frozenset({HUB_SORT, HUB_INFERENCE_PROVIDER})


def derive_research_terms(
    intent: dict[str, Any],
    vocabulary: ResearchVocabulary,
    patterns: tuple[dict[str, Any], ...],
    *,
    freshness_window_days: int = DEFAULT_FRESHNESS_WINDOW_DAYS,
) -> dict[str, Any]:
    """Return the terms document for ``intent``; raise ``OAK-RESEARCH-VOCABULARY`` on a gap."""

    if not isinstance(freshness_window_days, int) or not 1 <= freshness_window_days <= 365:
        raise OAKError("OAK-RESEARCH-VOCABULARY", "freshness window must be 1 to 365 days")
    capabilities = _model_capabilities(vocabulary, patterns)
    capability_map = vocabulary.capabilities["capabilities"]
    pipeline_tags: set[str] = set()
    filters: set[str] = set()
    for name in capabilities:
        pipeline_tags.update(capability_map[name]["hub_pipeline_tags"])
        filters.update(capability_map[name]["hub_filters"])
    kinds = vocabulary.capabilities["harness_kinds"]
    topics = {
        kind: sorted(kinds[kind]["github_topics"])
        for kind in sorted(kinds)
        if kinds[kind]["github_topics"]
    }
    licences = sorted(
        (str(entry["spdx_id"]), str(entry["github_keyword"]), str(entry["hub_tag"]))
        for entry in vocabulary.licences["licences"]
    )
    terms = {
        "version": TERMS_VERSION,
        "sent": {
            "hub": {
                "pipeline_tags": sorted(pipeline_tags),
                "filters": sorted(filters),
                "sort": HUB_SORT,
                "inference_provider": HUB_INFERENCE_PROVIDER,
            },
            "github": {
                "topics": topics,
                "licences": [keyword for _spdx, keyword, _tag in licences],
                "archived": False,
                "pushed_within_days": freshness_window_days,
            },
        },
        "local": {
            "capabilities": capabilities,
            "hardware_class": classify_hardware(intent, vocabulary),
            "licence_ids": [spdx for spdx, _keyword, _tag in licences],
            "hub_licence_tags": [tag for _spdx, _keyword, tag in licences],
            "freshness_window_days": freshness_window_days,
        },
        "vocabulary": {
            "capabilities": _identity(vocabulary.capabilities),
            "hardware_classes": _identity(vocabulary.hardware_classes),
            "licences": _identity(vocabulary.licences),
            "harness_repositories": _identity(vocabulary.harness_repositories),
            "bindings": [_identity(binding) for binding in vocabulary.bindings],
        },
    }
    return terms


def terms_digest(terms: dict[str, Any]) -> str:
    """The digest the consent carries: ``sha256:`` over the canonical JSON of the terms."""

    canonical = json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()


def classify_hardware(intent: dict[str, Any], vocabulary: ResearchVocabulary) -> str:
    """The first hardware class whose rule the intent's hardware section satisfies.

    Only three facts are read: whether the accelerator list is declared and holds anything,
    the accelerator memory and the system memory. An intent that declares no accelerator
    list at all is ``unknown``, not CPU-only. Free-text fields (the accelerator names,
    drivers, network, topology, expansion path) are never read, so nothing an author typed
    can reach a term.
    """

    spec = intent.get("spec") if isinstance(intent, dict) else None
    hardware = spec.get("hardware") if isinstance(spec, dict) else None
    hardware = hardware if isinstance(hardware, dict) else {}
    accelerators = hardware.get("accelerators")
    if isinstance(accelerators, list):
        has_accelerator = len(accelerators) > 0
        declared_none = len(accelerators) == 0
    else:
        has_accelerator = declared_none = False
    vram = _number(hardware.get("vram_gib"))
    ram = _number(hardware.get("ram_gib"))
    for entry in vocabulary.hardware_classes["classes"]:
        presence = entry.get("accelerators")
        if presence == "present" and not has_accelerator:
            continue
        if presence == "absent" and not declared_none:
            continue
        if "vram_gib_at_least" in entry and (vram is None or vram < entry["vram_gib_at_least"]):
            continue
        if "ram_gib_at_least" in entry and (ram is None or ram < entry["ram_gib_at_least"]):
            continue
        return str(entry["id"])
    raise OAKError("OAK-RESEARCH-VOCABULARY", "hardware classes have no fallback")


def _model_capabilities(
    vocabulary: ResearchVocabulary, patterns: tuple[dict[str, Any], ...]
) -> list[str]:
    by_id = {str(pattern["id"]): pattern for pattern in patterns}
    capability_map = vocabulary.capabilities["capabilities"]
    found: set[str] = set()
    for binding in vocabulary.bindings:
        pattern = by_id.get(str(binding["pattern_id"]))
        if pattern is None:
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research binding names an unknown pattern")
        roles = {str(role["id"]): role for role in pattern["roles"]}
        role = roles.get(str(binding["model_role_id"]))
        if role is None or role["component_category"] != "model":
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research binding names a non-model role")
        capability = str(role["required_capability"])
        entry = capability_map.get(capability)
        if entry is None or entry["component_category"] != "model":
            raise OAKError("OAK-RESEARCH-VOCABULARY", "pattern capability is outside the map")
        found.add(capability)
    if not found:
        raise OAKError("OAK-RESEARCH-VOCABULARY", "no research binding yields a capability")
    return sorted(found)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _identity(document: dict[str, Any]) -> str:
    return f"{document['id']}@{document['version']}"
