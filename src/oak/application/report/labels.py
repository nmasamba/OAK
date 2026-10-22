# SPDX-License-Identifier: Apache-2.0
"""The words a reader sees for ids and classes, mirrored from the web workspace.

`VARIANT_LABELS` mirrors `web/src/ui/variantLabel.ts` and a contract test keeps the two
equal: a candidate is "Balanced" in the report for the reason it is "Balanced" on the
screen, and a raw variant id is never rendered. `PROVENANCE_WORDS` mirrors the classes
`web/src/claims.tsx` names, plus the two the intent schema adds. `RESEARCHED_SUFFIX`
mirrors the one closed suffix a researched design's label carries ("Balanced, new",
ADR-0018); a label is never built from a model or repository name, and a researched
design is never the baseline.
"""

from __future__ import annotations

import re
from typing import Any

VARIANT_LABELS: dict[str, str] = {
    "simpler_baseline": "Baseline",
    "minimum_sufficient": "Minimal",
    "balanced_enterprise": "Balanced",
    "high_assurance_sovereign": "High assurance",
}
BASELINE_VARIANT = "simpler_baseline"
RESEARCHED_SUFFIX = "new"
RESEARCH_EXTENSION = "oak.community/research"

PROVENANCE_WORDS: dict[str, str] = {
    "explicit": "Fact from brief",
    "user_correction": "Corrected by reviewer",
    "inferred_from_brief": "Inference",
    "domain_default": "Domain default",
    "model_proposed": "Proposed by model",
    "policy": "Policy",
    "measured": "Measured",
    "unknown": "Unknown",
}

# `evidenceRef.source_type` as a reader sees it (appendix E). A fixture component's evidence
# is a synthetic declaration whatever its recorded type, so a reader never takes a
# fixture's figure for a measurement; a researched claim maps onto the three untrusted
# types and reads as such (ADR-0018).
SOURCE_TYPE_WORDS: dict[str, str] = {
    "authoritative": "Authoritative",
    "official_guidance": "Official guidance",
    "measured": "Measured",
    "stakeholder": "Stakeholder",
    "vendor_claim": "Vendor claim",
    "community_claim": "Community claim",
    "inference": "Inference",
}
SYNTHETIC_DECLARATION = "Synthetic declaration"
# The research words (ADR-0018), mirrored from `web/src/research.ts` and held equal by the
# agreement tests: where an item came from, what it is, which tier it sits in and what the
# gates said. Every one is closed; a reader never sees a raw enum value.
SOURCE_WORDS: dict[str, str] = {
    "huggingface_hub": "Hugging Face Hub",
    "huggingface_router": "Hugging Face router",
    "github": "GitHub",
    "fixture": "Fixture (synthetic)",
}
KIND_WORDS: dict[str, str] = {
    "model": "Model",
    "serving_runtime": "Serving runtime",
    "agent_framework": "Agent framework",
    "retrieval_engine": "Retrieval engine",
}
TIER_WORDS: dict[str, str] = {
    "trusted": "Trusted source",
    "unvetted": "Unvetted",
}
VERDICT_WORDS: dict[str, str] = {
    "passed": "Passed the gates",
    "needs_review": "Needs your review",
    "failed": "Did not pass",
}
# The word for an objective that names no estimator, so appendix D never prints "None".
NO_ESTIMATOR = "none recorded"

_SEPARATORS = re.compile(r"[_-]+")


def variant_label(variant_id: str | None) -> str:
    """ "Baseline" for `simpler_baseline`; any other id humanised, as the web does."""

    if not variant_id:
        return "Unknown"
    known = VARIANT_LABELS.get(variant_id)
    if known is not None:
        return known
    words = _SEPARATORS.sub(" ", variant_id).strip()
    return words[:1].upper() + words[1:]


def candidate_variant_id(candidate: dict[str, Any]) -> str | None:
    """The pattern variant the compiler records, else the coarser canonical `variant`."""

    extensions = candidate.get("extensions")
    if isinstance(extensions, dict):
        pattern = extensions.get("oak.community/pattern_variant")
        if isinstance(pattern, str):
            return pattern
    variant = candidate.get("variant")
    return variant if isinstance(variant, str) else None


def is_researched(candidate: dict[str, Any]) -> bool:
    """True for a design the compiler built from a research snapshot."""

    extensions = candidate.get("extensions")
    return isinstance(extensions, dict) and isinstance(extensions.get(RESEARCH_EXTENSION), dict)


def candidate_label(candidate: dict[str, Any]) -> str:
    label = variant_label(candidate_variant_id(candidate))
    return f"{label}, {RESEARCHED_SUFFIX}" if is_researched(candidate) else label


def is_baseline(candidate: dict[str, Any]) -> bool:
    """Only the curated baseline is a baseline; a researched design never is."""

    return not is_researched(candidate) and candidate_variant_id(candidate) == BASELINE_VARIANT


def humanise(identifier: str) -> str:
    """`constraint.data-locality` → "Data locality"; `latency_p95` → "Latency p95"."""

    tail = identifier.rsplit(".", 1)[-1]
    words = _SEPARATORS.sub(" ", tail).strip()
    return words[:1].upper() + words[1:] if words else identifier


NUMBER_WORDS = (
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)


def count_words(count: int) -> str:
    """A small count as a word, for a title or sentence that must hold no bare number."""

    return NUMBER_WORDS[count] if 0 <= count < len(NUMBER_WORDS) else "many"


_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_TEENS = ("thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")


def number_words(count: int) -> str:
    """A whole number under one thousand in words ("thirty", "one hundred and eighty");
    "many" beyond that.

    For a figure a sentence must carry without a bare digit (R2), such as a budget's
    request count, deadline or window; a measured or published figure is a quantity.
    """

    if count < 0 or count >= 1000:
        return "many"
    if count < len(NUMBER_WORDS):
        return NUMBER_WORDS[count]
    if count < 20:
        return _TEENS[count - 13]
    if count < 100:
        tens, units = divmod(count, 10)
        return _TENS[tens] if units == 0 else f"{_TENS[tens]}-{NUMBER_WORDS[units]}"
    hundreds, rest = divmod(count, 100)
    prefix = f"{NUMBER_WORDS[hundreds]} hundred"
    return prefix if rest == 0 else f"{prefix} and {number_words(rest)}"


def source_type_word(source_type: object, *, synthetic: bool = False) -> str:
    """The closed word for an evidence record's source type; synthetic for a fixture's."""

    if synthetic:
        return SYNTHETIC_DECLARATION
    return SOURCE_TYPE_WORDS.get(str(source_type), "Unknown")


def estimator_word(estimator_ref: object) -> str:
    return str(estimator_ref) if isinstance(estimator_ref, str) and estimator_ref else NO_ESTIMATOR
