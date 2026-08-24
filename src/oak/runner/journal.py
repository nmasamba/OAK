# SPDX-License-Identifier: Apache-2.0
"""Append-only, hash-chained runner journal with crash-resume state."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oak.domain import OAKError, canonical_json_bytes, content_digest

ENTRY_TYPES = frozenset(
    {
        "lease_accepted",
        "operation_before",
        "operation_after",
        "operation_failed",
        "cancellation_observed",
        "rollback_before",
        "rollback_after",
        "manual_recovery_required",
        "completion_recorded",
    }
)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    sequence: int
    previous_digest: str | None
    entry_type: str
    occurred_at: str
    details: dict[str, Any]

    def to_document(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_digest": self.previous_digest,
            "entry_type": self.entry_type,
            "occurred_at": self.occurred_at,
            "details": self.details,
        }

    @property
    def digest(self) -> str:
        return content_digest(canonical_json_bytes(self.to_document()))


class RunnerJournal:
    """One journal file per lease; every external side effect is bracketed."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entry_type: str, occurred_at: str, details: dict[str, Any]) -> JournalEntry:
        if entry_type not in ENTRY_TYPES:
            raise OAKError("OAK-JOURNAL-ENTRY", "journal entry type is not recognized")
        entries = self.entries()
        previous = entries[-1].digest if entries else None
        entry = JournalEntry(
            sequence=len(entries) + 1,
            previous_digest=previous,
            entry_type=entry_type,
            occurred_at=occurred_at,
            details=details,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        descriptor = os.open(self._path, flags, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(canonical_json_bytes(entry.to_document()) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return entry

    def entries(self) -> tuple[JournalEntry, ...]:
        if not self._path.is_file():
            return ()
        entries: list[JournalEntry] = []
        for number, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            # A journal on disk is exactly the thing that is damaged when this matters,
            # so a malformed line is a domain refusal, not a raw parser exception.
            # `json.loads` raised JSONDecodeError and a wrong-shaped line raised
            # TypeError or KeyError, and `verify_chain` is called unguarded from both
            # `oak-runner status` and `run_once` — so a corrupt journal crashed the very
            # command that exists to report it, and wedged the runner besides.
            try:
                document = json.loads(line)
                entries.append(
                    JournalEntry(
                        sequence=int(document["sequence"]),
                        previous_digest=document["previous_digest"],
                        entry_type=str(document["entry_type"]),
                        occurred_at=str(document["occurred_at"]),
                        details=dict(document["details"]),
                    )
                )
            except (ValueError, TypeError, KeyError) as error:
                raise OAKError(
                    "OAK-JOURNAL-TAMPERED", f"journal entry {number} is not readable"
                ) from error
        return tuple(entries)

    def verify_chain(self) -> None:
        previous: str | None = None
        for index, entry in enumerate(self.entries(), start=1):
            if entry.sequence != index or entry.previous_digest != previous:
                raise OAKError("OAK-JOURNAL-TAMPERED", "journal hash chain does not verify")
            previous = entry.digest

    def digest(self) -> str:
        entries = self.entries()
        return entries[-1].digest if entries else content_digest(b"")

    def incomplete_operation(self) -> dict[str, Any] | None:
        """Return the operation whose before-entry has no after/failed entry."""

        open_operation: dict[str, Any] | None = None
        for entry in self.entries():
            if entry.entry_type in {"operation_before", "rollback_before"}:
                open_operation = entry.details
            elif entry.entry_type in {
                "operation_after",
                "operation_failed",
                "rollback_after",
                "manual_recovery_required",
            }:
                open_operation = None
        return open_operation

    def requires_manual_recovery(self) -> bool:
        return any(entry.entry_type == "manual_recovery_required" for entry in self.entries())
