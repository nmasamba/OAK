# SPDX-License-Identifier: Apache-2.0
"""The checks a model's note must pass before a report quotes it.

A note is untrusted proposal data, so the rules hold it inside the slide it describes
rather than only naming what it may not say. It is kept only if:
- it names a main slide once;
- it is at most two plain sentences and 280 characters;
- it carries no control or format character (no zero-width or bidirectional tricks);
- it uses no assurance vocabulary, no edition word and no raw variant id;
- it claims no approval, clearance, safety, security or authority;
- it holds no link, address or host name the slide does not hold;
- it holds no benefit, saving or return;
- every number in it, in digits or in words, appears on that slide, and where a number
  carries a unit word, that unit appears on the slide line that holds the number.
Anything else is dropped and counted; nothing in a dropped note reaches a record.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from oak.domain.vocabulary import forbidden_words

MAXIMUM_NOTE_CHARACTERS = 280
MAXIMUM_SENTENCES = 2
AUTHORITY = re.compile(
    r"\b(?:approv\w*|authori[sz]\w*|guarantee\w*|certif\w*|complian\w*|"
    r"sign(?:ed|-off|off)|secur\w*|safe(?:ly|ty)?|cleared|clearance|endors\w*|vetted|"
    r"accredit\w*|sanction\w*|verified|validated|permitted to (?:deploy|install|run)|"
    r"ready (?:for|to) (?:production|deploy\w*|install\w*))\b",
    re.IGNORECASE,
)
BENEFIT = re.compile(
    r"\b(?:sav(?:e|es|ed|ing|ings)|pays? (?:for )?itself|payback|roi|return on|"
    r"benefit\w*|cheaper|profit\w*|revenue)\b",
    re.IGNORECASE,
)
MARKUP = re.compile(r"[a-z][a-z0-9+.-]*://|\bmailto:|www\.|@|\]\(|[<>`*_#|\[\]{}]", re.IGNORECASE)
HOST = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
NUMBER_WORDS = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundred|thousand|million|billion|dozen|half|twice|double|triple|"
    r"percent)\b",
    re.IGNORECASE,
)
# A word after a number that names its unit; it must sit on the same slide line as the
# number, so a figure cannot be moved from one row's unit to another's.
UNIT_WORDS = {
    "usd": "usd",
    "dollar": "usd",
    "dollars": "usd",
    "$": "usd",
    "ms": "millisecond",
    "millisecond": "millisecond",
    "milliseconds": "millisecond",
    "s": "second",
    "second": "second",
    "seconds": "second",
    "wh": "wh",
    "gib": "gib",
    "gb": "gb",
    "mb": "mb",
    "%": "%",
    "percent": "%",
    "case": "case",
    "cases": "case",
    "user": "user",
    "users": "user",
    "month": "month",
    "months": "month",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "days": "day",
}
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
FOLLOWING = re.compile(r"(\d+(?:[.,]\d+)*)\s*([a-z]+|[%$])?", re.IGNORECASE)
WORD = re.compile(r"[a-z]+|[%$]")


def _numbers(text: str) -> set[str]:
    return {match.replace(",", "") for match in NUMBER.findall(text)}


def _slide_lines(slide: dict[str, Any]) -> list[str]:
    return [
        str(slide.get("title", "")),
        str(slide.get("subtitle", "")),
        *[str(line) for line in slide.get("lines", [])],
    ]


def _units(line: str) -> set[str]:
    return {UNIT_WORDS[word] for word in WORD.findall(line.lower()) if word in UNIT_WORDS}


def _units_hold(text: str, lines: list[str]) -> bool:
    """Every number that names a unit in the note sits beside that unit on the slide."""

    for number, word in FOLLOWING.findall(text):
        unit = UNIT_WORDS.get(word.lower())
        if unit is None:
            continue
        value = number.replace(",", "")
        if not any(value in _numbers(line) and unit in _units(line) for line in lines):
            return False
    return True


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
        if any(unicodedata.category(character).startswith("C") for character in text):
            dropped += 1
            continue
        lines = _slide_lines(slides[section])
        slide_text = " ".join(lines)
        slide_lower = slide_text.lower()
        if (
            not text
            or len(text) > MAXIMUM_NOTE_CHARACTERS
            or len(SENTENCE_END.findall(text)) > MAXIMUM_SENTENCES
            or forbidden_words(text)
            or AUTHORITY.search(text)
            or BENEFIT.search(text)
            or MARKUP.search(text)
            or any(host.lower() not in slide_lower for host in HOST.findall(text))
            or any(
                not re.search(rf"\b{re.escape(word.lower())}\b", slide_lower)
                for word in NUMBER_WORDS.findall(text)
            )
            or not _numbers(text) <= _numbers(slide_text)
            or not _units_hold(text, lines)
        ):
            dropped += 1
            continue
        kept[section] = text
    return kept, dropped
