# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-004: the checks a model's note passes before a report quotes it."""

from __future__ import annotations

import pytest

from oak.application.report.notes import check_notes

FACTS = {
    "slides": [
        {
            "section": "8",
            "title": "Balanced is estimated to cost more than the baseline per month",
            "subtitle": "Point estimate and range.",
            "lines": ["Balanced (candidate-03) | 36 USD/month (32.4 to 39.6)"],
        },
        {"section": "7", "title": "The owner chose Balanced", "subtitle": "s", "lines": []},
    ]
}
GOOD = "Balanced is estimated at 36 USD a month, against the baseline."


def test_a_plain_sourced_note_is_kept_with_its_whitespace_tidied() -> None:
    kept, dropped = check_notes([{"section": "8", "text": f"  {GOOD}\n"}], FACTS)
    assert kept == {"8": GOOD}
    assert dropped == 0


@pytest.mark.parametrize(
    "note",
    (
        {"section": "A", "text": "An appendix note."},
        {"section": "99", "text": "No such slide."},
        {"section": "8", "text": ""},
        {"section": "8", "text": "x" * 281},
        {"section": "8", "text": "One. Two. Three."},
        {"section": "8", "text": "The design is certified."},
        {"section": "8", "text": "An enterprise design."},
        {"section": "8", "text": "Pick balanced_enterprise."},
        {"section": "8", "text": "See https://example.com for more."},
        {"section": "8", "text": "Use **bold** words."},
        {"section": "8", "text": "This design is approved."},
        {"section": "8", "text": "It is ready for production."},
        {"section": "8", "text": "It is safe to deploy."},
        {"section": "8", "text": "It costs 99 USD a month."},
        {"section": "8", "text": "It costs\x0736 USD."},
        # Invisible format characters survive NFKC; none may reach a note.
        {"section": "8", "text": f"Balanced\u200b {GOOD}"},
        {"section": "8", "text": f"Bal\u00adanced {GOOD}"},
        {"section": "8", "text": f"{GOOD}\u2060"},
        {"section": "8", "text": f"\u202e{GOOD}"},
        # Authority in other words than the narrator's rule 3 lists.
        {"section": "8", "text": "Balanced has been cleared for deployment."},
        {"section": "8", "text": "Balanced is secure and safe for production."},
        {"section": "8", "text": "OAK has verified and validated this design."},
        {"section": "8", "text": "Balanced is endorsed by the security team."},
        # Addresses and hosts the slide does not hold.
        {"section": "8", "text": "Ask ops@example.org about Balanced."},
        {"section": "8", "text": "Fetch ftp://mirror/balanced first."},
        {"section": "8", "text": "Write to mailto:owner about it."},
        {"section": "8", "text": "Read balanced.example.org before choosing."},
        # Numbers in words, moved units and benefits the slide does not state.
        {"section": "8", "text": "Balanced costs thirty USD a month."},
        {"section": "8", "text": "Balanced costs twice the baseline."},
        {"section": "8", "text": "Balanced serves 36 users a month."},
        {"section": "8", "text": "Balanced saves money against the baseline."},
        {"section": "8", "text": "Balanced pays for itself within a year."},
        {"section": "8", "text": "Balanced has a quick payback."},
        # Superlatives: OAK says what each record states, never that something is the best.
        {"section": "8", "text": "Balanced, new is the best option and works well."},
        {"section": "8", "text": "Balanced is the optimal choice."},
        {"section": "8", "text": "Balanced works fine for this corpus."},
        {"section": "8", "text": 36},
        "not an object",
    ),
)
def test_a_note_that_breaks_a_rule_is_dropped(note: object) -> None:
    kept, dropped = check_notes([note], FACTS)
    assert kept == {}
    assert dropped == 1


def test_one_note_per_slide_and_the_rest_counted() -> None:
    kept, dropped = check_notes(
        [
            {"section": "8", "text": GOOD},
            {"section": "8", "text": "Again."},
            {"section": "7", "text": "The owner chose Balanced."},
        ],
        FACTS,
    )
    assert kept == {"8": GOOD, "7": "The owner chose Balanced."}
    assert dropped == 1


def test_a_number_from_the_slide_may_be_repeated_with_or_without_grouping() -> None:
    facts = {
        "slides": [
            {
                "section": "6",
                "title": "t",
                "subtitle": "s",
                "lines": ["Latency | 1,200 milliseconds (900 to 1,500)"],
            }
        ]
    }
    kept, _ = check_notes([{"section": "6", "text": "Latency is near 1200 milliseconds."}], facts)
    assert kept == {"6": "Latency is near 1200 milliseconds."}


def test_a_host_or_number_word_the_slide_holds_may_be_repeated() -> None:
    facts = {
        "slides": [
            {
                "section": "9",
                "title": "Two services run on gpu.node",
                "subtitle": "s",
                "lines": ["Nodes | gpu.node"],
            }
        ]
    }
    note = "Both services run on gpu.node, two of them."
    assert check_notes([{"section": "9", "text": note}], facts) == ({"9": note}, 0)


def test_anything_but_a_list_is_no_notes() -> None:
    assert check_notes({"section": "8"}, FACTS) == ({}, 0)
    assert check_notes(None, FACTS) == ({}, 0)
