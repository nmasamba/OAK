# SPDX-License-Identifier: Apache-2.0
"""The runner's signed lease heartbeat (RR-031).

While a dispatch runs, the runner publishes a signed `heartbeat` message, a kind the
runner-message schema has always listed, at every step boundary once the interval has
passed: lease accepted, before and after each operation, between the containers an apply
creates and starts, and on every readiness poll. Each names the lease and the journal's
head at that moment, so the control plane can see that the runner is alive and how far
its journal reached, and `oak ingest` refuses a later completion whose journal no longer
reaches a head a heartbeat reported. A heartbeat is a report, never an authority: it moves
no state, extends no lease and is bound to its lease like every runner message.

A heartbeat that cannot be written does not stop the install; the completion, which can,
says what happened. The interval is `OAK_RUNNER_HEARTBEAT_SECONDS`; `0` disables it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from oak.runner.journal import RunnerJournal

HEARTBEAT_INTERVAL_SECONDS = 30.0
Publish = Callable[[int, dict[str, Any]], None]


class LeaseHeartbeat:
    def __init__(
        self,
        publish: Publish,
        journal: RunnerJournal,
        *,
        clock: Callable[[], float],
        interval_seconds: float,
    ) -> None:
        self._publish = publish
        self._journal = journal
        self._clock = clock
        self._interval = max(0.0, float(interval_seconds))
        self._sequence = 0
        self._last: float | None = None

    @property
    def published(self) -> int:
        return self._sequence

    def beat(self, stage: str, *, operation_kind: str | None = None, force: bool = False) -> None:
        """Publish a heartbeat if the interval has passed since the last one, or when forced."""

        now = self._clock()
        if not force and self._last is not None and now - self._last < self._interval:
            return
        sequence, digest = self._journal.head()
        payload = {
            "stage": stage,
            "operation_kind": operation_kind,
            "journal_sequence": sequence,
            "journal_digest": digest,
        }
        try:
            self._publish(self._sequence + 1, payload)
        except (OSError, ValueError):
            return
        self._sequence += 1
        self._last = now


__all__ = ["HEARTBEAT_INTERVAL_SECONDS", "LeaseHeartbeat"]
