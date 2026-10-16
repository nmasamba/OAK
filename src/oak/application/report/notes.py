# SPDX-License-Identifier: Apache-2.0
"""The checks a model's note must pass before a report quotes it.

A note is untrusted proposal data. It is kept only if it names a main slide once, reads
as at most two plain sentences of at most 280 characters, uses no assurance vocabulary,
no edition word and no raw variant id, carries no link or markup, claims no approval or
authority, and holds no number that the slide's own text does not hold. Anything else is
dropped and counted; nothing in a dropped note reaches a record.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from oak.domain.vocabulary import forbidden_words

MAXIMUM_NOTE_CHARACTERS = 280
MAXIMUM_SENTENCES = 2
AUTHORITY = re.compile(
    r"\b(?:approv\w*|authori[sz]\w*|guarantee\w*|certif\w*|complian\w*|sign(?:ed|-off|off)|"
    r"safe to (?:deploy|install|use)|ready (?:for|to) (?:production|deploy\w*|install\w*))\b",
    re.IGNORECASE,
)
MARKUP = re.compile(r"https?://|www\.|\]\(|[<>`*_#|\[\]{}]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def _numbers(text: str) -> set[str]:
    return {match.replace(",", "") for match in NUMBER.findall(text)}


def _slide_text(slide: dict[str, Any]) -> str:
    return " ".join(
        [
            str(slide.get("title", "")),
            str(slide.get("subtitle", "")),
            *[str(line) for line in slide.get("lines", [])],
        ]
    )


def check_notes(proposed: Any, facts: dict[str, Any]) -> tuple[dict[str, str], int]:
    """The notes worth keeping, by section number, and how many were dropped."""

    slides = {str(slide["section"]): slide for slide in facts.get("slides", [])}
    kept: dict[str, str] = {}
    dropped = 0
    for note in proposed if isinstance(proposed, list) else []:
        section = str(note.get("section")) if isinstance(note, dict) else ""
        text = note.get("text") if isinstance(note, dict) else None
        if section not in slides or section in kept or not isinstance(text, str):
            dropped += 1
            continue
        text = " ".join(unicodedata.normalize("NFKC", text).split())
        if (
            not text
            or len(text) > MAXIMUM_NOTE_CHARACTERS
            or len(SENTENCE_END.findall(text)) > MAXIMUM_SENTENCES
            or any(unicodedata.category(character) == "Cc" for character in text)
            or forbidden_words(text)
            or AUTHORITY.search(text)
            or MARKUP.search(text)
            or not _numbers(text) <= _numbers(_slide_text(slides[section]))
        ):
            dropped += 1
            continue
        kept[section] = text
    return kept, dropped
