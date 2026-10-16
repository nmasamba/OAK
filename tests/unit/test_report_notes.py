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
                "lines": ["Latency | 1,200 (900 to 1,500)"],
            }
        ]
    }
    kept, _ = check_notes([{"section": "6", "text": "Latency is near 1200 milliseconds."}], facts)
    assert kept == {"6": "Latency is near 1200 milliseconds."}


def test_anything_but_a_list_is_no_notes() -> None:
    assert check_notes({"section": "8"}, FACTS) == ({}, 0)
    assert check_notes(None, FACTS) == ({}, 0)
