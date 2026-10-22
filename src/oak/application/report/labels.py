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
