# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-033 (RR-031): the lease heartbeat publishes at step boundaries once its interval
has passed, names the journal's head, and never stops an install when it cannot be written."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oak.runner.heartbeat import LeaseHeartbeat
from oak.runner.journal import RunnerJournal

STAMP = "2026-10-29T12:00:00Z"


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _heartbeat(
    tmp_path: Path, clock: _Clock, interval: float, failures: int = 0
) -> tuple[LeaseHeartbeat, list[tuple[int, dict[str, Any]]], RunnerJournal]:
    published: list[tuple[int, dict[str, Any]]] = []
    remaining = [failures]

    def publish(sequence: int, payload: dict[str, Any]) -> None:
        if remaining[0]:
            remaining[0] -= 1
            raise OSError("mailbox full")
        published.append((sequence, payload))

    journal = RunnerJournal(tmp_path / "journal.jsonl")
    return (
        LeaseHeartbeat(publish, journal, clock=clock, interval_seconds=interval),
        published,
        journal,
    )


def test_it_beats_when_forced_then_only_once_the_interval_has_passed(tmp_path: Path) -> None:
    clock = _Clock()
    heartbeat, published, journal = _heartbeat(tmp_path, clock, 30.0)
    journal.append("lease_accepted", STAMP, {"lease_id": "lease.1"})
    heartbeat.beat("lease_accepted", force=True)
    heartbeat.beat("operation", operation_kind="apply")  # too soon
    clock.now += 29.0
    heartbeat.beat("apply", operation_kind="apply")  # still too soon
    clock.now += 1.0
    journal.append("operation_before", STAMP, {"kind": "apply"})
    heartbeat.beat("apply", operation_kind="apply")
    assert [sequence for sequence, _ in published] == [1, 2]
    first, second = (payload for _, payload in published)
    assert first["stage"] == "lease_accepted" and first["operation_kind"] is None
    assert (first["journal_sequence"], first["journal_digest"]) == (1, journal.entries()[0].digest)
    assert second["stage"] == "apply" and second["operation_kind"] == "apply"
    assert (second["journal_sequence"], second["journal_digest"]) == journal.head()
    assert heartbeat.published == 2


def test_an_interval_of_zero_beats_at_every_boundary(tmp_path: Path) -> None:
    clock = _Clock()
    heartbeat, published, _journal = _heartbeat(tmp_path, clock, 0.0)
    for stage in ("lease_accepted", "operation", "apply", "operation_done"):
        heartbeat.beat(stage)
    assert [sequence for sequence, _ in published] == [1, 2, 3, 4]


def test_a_heartbeat_that_cannot_be_written_is_dropped_without_a_gap(tmp_path: Path) -> None:
    clock = _Clock()
    heartbeat, published, _journal = _heartbeat(tmp_path, clock, 0.0, failures=1)
    heartbeat.beat("lease_accepted", force=True)  # the mailbox refuses this one
    heartbeat.beat("operation")
    heartbeat.beat("operation_done")
    assert [sequence for sequence, _ in published] == [1, 2], "a failed beat left a hole"
    assert heartbeat.published == 2
