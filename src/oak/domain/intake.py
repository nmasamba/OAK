# SPDX-License-Identifier: Apache-2.0
"""Typed values produced by bounded brief intake."""

import unicodedata
from dataclasses import dataclass
from typing import Any

# Tab and the line breaks are layout. Every other control (Cc), format (Cf, which holds the
# bidirectional overrides) or surrogate (Cs) character is refused wherever untrusted
# structured input is parsed, because a JSON or YAML escape produces one as easily as a raw
# byte does, and the raw-text checks never see it.
REFUSED_CHARACTER_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
# The only media types a stored brief source may carry: the four formats intake reads. An
# imported export is held to them too, so its index cannot relabel a brief as a web page.
BRIEF_MEDIA_TYPES = frozenset(
    {"application/yaml", "application/json", "text/markdown", "text/plain"}
)


def holds_control_character(value: Any) -> bool:
    """True if any string, or mapping key, anywhere in ``value`` holds a refused character."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(
                character not in "\t\n\r"
                and unicodedata.category(character) in REFUSED_CHARACTER_CATEGORIES
                for character in current
            ):
                return True
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
    return False


@dataclass(frozen=True, slots=True)
class IngestedBrief:
    id: str
    version: str
    title: str
    format: str
    media_type: str
    original_name: str
    content: bytes
    structured: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    kind: str
    path: str
    message: str
    materiality: str
    blocking_stage: str


@dataclass(frozen=True, slots=True)
class ClarificationQuestion:
    id: str
    path: str
    question: str
    reason: str
    materiality: str
    blocking_stage: str
    blocking_gate: str
    status: str = "open"
    # Presentation-only ordering hint. Deterministic questions carry 0; a question that
    # confirms model-proposed values carries the section's lowest confidence bucket so
    # the least certain proposal is asked first. Never serialized: the documents below
    # are unchanged, so the deterministic path's bytes cannot depend on it.
    rank_hint: int = 0

    def case_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "question": self.question,
            "reason": self.reason,
            "materiality": self.materiality,
            "blocking_stage": self.blocking_stage,
            "status": self.status,
        }

    def intent_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "question": self.question,
            "materiality": self.materiality,
            "blocking_gate": self.blocking_gate,
            "status": self.status,
        }
