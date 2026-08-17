# SPDX-License-Identifier: Apache-2.0
"""Typed values produced by bounded brief intake."""

from dataclasses import dataclass
from typing import Any


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
