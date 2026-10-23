# SPDX-License-Identifier: Apache-2.0
"""Separate restart-safe Community compiler and projection worker process."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from oak.application import CommunityWorker
from oak.bootstrap import create_persistent_worker
from oak.domain import OAKError

# Twice the research run's 60-second deadline, so no handler outlives its lease and a
# second worker never sweeps a running job to failed while it is still sending (RR-031).
LEASE_SECONDS = 120
MAXIMUM_BACKOFF_SECONDS = 30.0


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def run_worker(
    worker: CommunityWorker,
    *,
    once: bool,
    clock: Callable[[], datetime] = _now,
    poll_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run worker cycles until stopped; one failed cycle never ends the process.

    A lost lease, a database restart or any other error in a cycle used to escape and
    end the worker, and Compose does not restart it, so every queued operation then
    waited forever (F2-2). The cycle's code (never its message, which may carry data) is
    written to stderr and the loop backs off and goes on.
    """

    failures = 0
    while True:
        current = clock()
        try:
            result = worker.run_once(
                now=_timestamp(current),
                lease_expires_at=_timestamp(current + timedelta(seconds=LEASE_SECONDS)),
            )
        except Exception as error:
            if once:
                raise
            failures += 1
            code = error.code if isinstance(error, OAKError) else type(error).__name__
            print(f"oak-worker: a cycle failed ({code}); retrying", file=sys.stderr, flush=True)
            sleep(min(MAXIMUM_BACKOFF_SECONDS, poll_seconds * 2 ** min(failures, 6)))
            continue
        failures = 0
        if once:
            return
        if result.operation is None and result.outbox_claimed == 0:
            sleep(poll_seconds)


def _environment_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    worker_id = os.getenv("OAK_WORKER_ID", "oak-worker-local")
    if not worker_id or len(worker_id) > 160:
        raise SystemExit("OAK_WORKER_ID must contain 1 to 160 characters")
    try:
        worker = create_persistent_worker(worker_id=worker_id)
    except RuntimeError as error:
        raise SystemExit(f"OAK-WORKER-CONFIG: {error}") from error
    run_worker(worker, once=_environment_flag("OAK_WORKER_ONCE"))


if __name__ == "__main__":  # pragma: no cover
    main()
