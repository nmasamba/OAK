# SPDX-License-Identifier: Apache-2.0
"""The closed vocabularies research may draw its terms from (Sprint 14, ADR-0018).

A leaf type: the compiler's pure terms function reads it, the catalogue adapter loads it,
and neither imports the other. Each field is one validated document from
``catalogue/research/``: the capability map, the hardware classes, the licence list, the
owner-reviewed harness list and the research bindings.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResearchVocabulary:
    capabilities: dict[str, Any]
    hardware_classes: dict[str, Any]
    licences: dict[str, Any]
    harness_repositories: dict[str, Any]
    bindings: tuple[dict[str, Any], ...]


# The closed evidence classes, shown beside every researched claim (ADR-0018). The schema
# `research-snapshot.schema.json` pins the same enum, and a contract test holds them equal;
# the web's words mirror `EVIDENCE_WORDS` and an agreement test holds those equal too.
EVIDENCE_CLASSES: tuple[str, ...] = (
    "served_by_live_route",
    "published_release",
    "published_by_source",
    "measured_by_source",
    "claimed_by_model_card",
    "claimed_by_release_notes",
    "unverified",
)
EVIDENCE_WORDS: dict[str, str] = {
    "served_by_live_route": "Live route",
    "published_release": "Published release",
    "published_by_source": "Published by source",
    "measured_by_source": "Measured by source",
    "claimed_by_model_card": "Claimed by model card",
    "claimed_by_release_notes": "Claimed by release notes",
    "unverified": "Unverified",
}
# Each class onto `evidenceRef.source_type` with a fixed confidence. None reads as if OAK
# checked it: a source's own listing, a live route and a dated release are the source's
# claims; a card's or a release note's words are the author's; a gap is an inference.
EVIDENCE_SOURCE_TYPES: dict[str, tuple[str, float]] = {
    "served_by_live_route": ("vendor_claim", 0.6),
    "published_release": ("vendor_claim", 0.7),
    "published_by_source": ("vendor_claim", 0.6),
    "measured_by_source": ("vendor_claim", 0.5),
    "claimed_by_model_card": ("community_claim", 0.3),
    "claimed_by_release_notes": ("community_claim", 0.3),
    "unverified": ("inference", 0.0),
}
ITEM_KINDS: tuple[str, ...] = ("model", "serving_runtime", "agent_framework", "retrieval_engine")
RESEARCH_SOURCES: tuple[str, ...] = ("huggingface_hub", "huggingface_router", "github", "fixture")
TIERS: tuple[str, ...] = ("trusted", "unvetted")
VERDICTS: tuple[str, ...] = ("passed", "needs_review", "failed")

CURATED_RULES_VERSION = "community-open-components-1.0.0"
RESEARCH_GATES_VERSION = "community-research-gates-1.0.0"
COMPARISON_RULE_VERSION = "community-compare-only-1.0.0"

# Namespaced extension keys. A researched manifest and a researched candidate carry
# `RESEARCH_EXTENSION`; a candidate the compare-only rule classified carries
# `COMPARISON_EXTENSION`; a case that holds research carries the two reference keys, which
# the export-lineage check covers.
RESEARCH_EXTENSION = "oak.community/research"
COMPARISON_EXTENSION = "oak.community/comparison"
RESEARCH_SNAPSHOT_REF = "oak.community/research_snapshot_ref"
RESEARCH_REVIEW_REFS = "oak.community/research_review_refs"
RESEARCH_SNAPSHOT_MEDIA_TYPE = "application/vnd.oak.research-snapshot+json"
# The three hosts research may read, and nothing else (ADR-0018, guard S1).
RESEARCH_HOSTS: frozenset[str] = frozenset(
    {"huggingface.co", "router.huggingface.co", "api.github.com"}
)
# Organisations that publish open weights under their own name. Read against the Hub's
# trending list on the date below; a namespace outside this set is never offered by Online
# AI and is unvetted for research, however high it trends, because a card is
# author-controlled and a fine-tune can carry any name. Never widened silently.
TRUSTED_NAMESPACES_AS_OF = "2026-09-21"
TRUSTED_NAMESPACES: frozenset[str] = frozenset(
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
RESEARCH_REVIEW_MEDIA_TYPE = "application/vnd.oak.research-review+json"
