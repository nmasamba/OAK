# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-002: the report says what the workspace says, in the same words.

The variant labels, the provenance words and the install steps exist once in the web and
once in Python. These tests read the TypeScript sources and fail when the two drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from oak.application.report.composer import INSTALL_STEPS
from oak.application.report.labels import (
    KIND_WORDS,
    PROVENANCE_WORDS,
    RESEARCHED_SUFFIX,
    SOURCE_WORDS,
    TIER_WORDS,
    VARIANT_LABELS,
    VERDICT_WORDS,
    candidate_label,
    is_baseline,
    number_words,
    variant_label,
)
from oak.compiler.research_designs import LABEL_SUFFIX
from oak.domain import EVIDENCE_WORDS

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "src"
ENTRY = re.compile(r'^\s*(\w+):\s*"([^"]+)",?\s*$', re.MULTILINE)


def _object_literal(source: str, name: str) -> dict[str, str]:
    start = source.index(name)
    body = source[source.index("{", start) + 1 : source.index("}", start)]
    return dict(ENTRY.findall(body))


def test_the_variant_labels_match_the_workspace() -> None:
    source = (WEB / "ui" / "variantLabel.ts").read_text(encoding="utf-8")
    assert _object_literal(source, "VARIANT_LABELS") == VARIANT_LABELS
    # The fallback the TypeScript documents: "some_new_kind" → "Some new kind".
    assert variant_label("some_new_kind") == "Some new kind"
    assert variant_label(None) == "Unknown"


def test_the_provenance_words_match_the_workspace() -> None:
    source = (WEB / "claims.tsx").read_text(encoding="utf-8")
    classes = _object_literal(source, "SOURCE_CLASSES")
    labels = _object_literal(source, "CLASS_LABELS")
    for provenance_source, claim_class in classes.items():
        assert PROVENANCE_WORDS[provenance_source] == labels[claim_class]
    assert PROVENANCE_WORDS["unknown"] == labels["unknown"]


def test_the_install_steps_match_the_copy_plate() -> None:
    source = (WEB / "pages" / "BundlePage.tsx").read_text(encoding="utf-8")
    start = source.index("const INSTALL_STEPS = [")
    body = source[start : source.index("].join", start)]
    assert tuple(re.findall(r'"([^"]+)"', body)) == INSTALL_STEPS


def test_the_evidence_words_match_the_workspace() -> None:
    """ADR-0018: one closed map of evidence words, in Python and in the web."""

    source = (WEB / "research.ts").read_text(encoding="utf-8")
    assert _object_literal(source, "export const EVIDENCE_WORDS") == EVIDENCE_WORDS


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SOURCE_WORDS", SOURCE_WORDS),
        ("KIND_WORDS", KIND_WORDS),
        ("TIER_WORDS", TIER_WORDS),
        ("VERDICT_WORDS", VERDICT_WORDS),
    ],
)
def test_the_research_words_match_the_workspace(name: str, expected: dict[str, str]) -> None:
    source = (WEB / "research.ts").read_text(encoding="utf-8")
    assert _object_literal(source, f"export const {name}") == expected


def test_budget_figures_have_words() -> None:
    assert [number_words(n) for n in (0, 1, 12, 13, 19, 20, 30, 42, 60, 99, 100, 180, 1000)] == [
        "no",
        "one",
        "twelve",
        "thirteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty-two",
        "sixty",
        "ninety-nine",
        "one hundred",
        "one hundred and eighty",
        "many",
    ]


def test_the_researched_suffix_matches_the_workspace_and_the_compiler() -> None:
    """ "Balanced, new": the pattern label plus the one closed suffix, never a model name."""

    source = (WEB / "ui" / "variantLabel.ts").read_text(encoding="utf-8")
    match = re.search(r'export const RESEARCHED_SUFFIX = "([^"]+)";', source)
    assert match is not None
    assert match.group(1) == RESEARCHED_SUFFIX == LABEL_SUFFIX
    researched = {
        "extensions": {
            "oak.community/pattern_variant": "balanced_enterprise",
            "oak.community/research": {
                "label_suffix": LABEL_SUFFIX,
                "model_source_id": "HuggingFaceTB/Fixturelm-4B",
            },
        }
    }
    assert candidate_label(researched) == "Balanced, new"
    assert "Fixturelm" not in candidate_label(researched)
    assert " (" not in candidate_label(researched)
    assert candidate_label(
        {"extensions": {"oak.community/pattern_variant": "balanced_enterprise"}}
    ) == ("Balanced")


def test_a_researched_design_is_never_the_baseline() -> None:
    researched = {
        "extensions": {
            "oak.community/pattern_variant": "simpler_baseline",
            "oak.community/research": {"label_suffix": LABEL_SUFFIX},
        }
    }
    assert not is_baseline(researched)
    assert is_baseline({"extensions": {"oak.community/pattern_variant": "simpler_baseline"}})
