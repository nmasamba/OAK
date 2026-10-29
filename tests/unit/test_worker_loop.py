# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005 (F2-2): the worker outlives a failed cycle and leases outlast every handler."""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from oak.application import WorkerCycleResult
from oak.domain import OAKError
from oak.interfaces.logs import configure_logging
from oak.interfaces.worker import LEASE_SECONDS, run_worker


class _Stop(BaseException):
    """Ends the loop from inside `sleep` once the test has seen enough."""


class _Worker:
    def __init__(self, failures: list[BaseException]) -> None:
        self.failures = list(failures)
        self.calls: list[dict[str, str]] = []

    def run_once(self, *, now: str, lease_expires_at: str) -> Any:
        self.calls.append({"now": now, "lease_expires_at": lease_expires_at})
        if self.failures:
            raise self.failures.pop(0)
        return WorkerCycleResult(operation=None, outbox_claimed=0, outbox_applied=0)


def test_a_failed_cycle_is_reported_by_code_and_the_loop_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _Worker(
        [
            OAKError("OAK-OPERATION-LEASE-LOST", "operation lease is no longer current"),
            ConnectionError("the database restarted: secret detail"),
        ]
    )
    pauses: list[float] = []

    def sleep(seconds: float) -> None:
        pauses.append(seconds)
        if len(worker.calls) >= 3:
            raise _Stop

    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    stream = io.StringIO()
    monkeypatch.delenv("OAK_LOG_LEVEL", raising=False)
    configure_logging("oak-worker", stream=stream)
    try:
        with pytest.raises(_Stop):
            run_worker(worker, once=False, sleep=sleep, poll_seconds=0.5)  # type: ignore[arg-type]
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
        logging.captureWarnings(False)

    assert len(worker.calls) == 3
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [(line["event"], line["code"], line["error_type"]) for line in lines] == [
        ("cycle_failed", "OAK-OPERATION-LEASE-LOST", "OAKError"),
        ("cycle_failed", "OAK-WORKER-CYCLE", "ConnectionError"),
    ]
    assert "secret detail" not in stream.getvalue()
    assert pauses[:2] == [1.0, 2.0], "it backs off rather than spinning"


def test_once_mode_still_surfaces_the_error() -> None:
    worker = _Worker([OAKError("OAK-OPERATION-LEASE-LOST", "lost")])
    with pytest.raises(OAKError):
        run_worker(worker, once=True)  # type: ignore[arg-type]


def test_the_lease_is_longer_than_the_research_deadline() -> None:
    from oak.adapters.models.research_sources import DEADLINE_SECONDS

    worker = _Worker([])
    moment = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    run_worker(worker, once=True, clock=lambda: moment)  # type: ignore[arg-type]
    assert worker.calls[0]["lease_expires_at"] == "2026-10-23T12:02:00Z"
    assert LEASE_SECONDS >= 2 * DEADLINE_SECONDS
