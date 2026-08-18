# SPDX-License-Identifier: Apache-2.0
"""Separate restart-safe Community compiler and projection worker process."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from oak.application import CommunityWorker
from oak.bootstrap import create_persistent_worker


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
) -> None:
    while True:
        current = clock()
        result = worker.run_once(
            now=_timestamp(current),
            lease_expires_at=_timestamp(current + timedelta(seconds=60)),
        )
        if once:
            return
        if result.operation is None and result.outbox_claimed == 0:
            time.sleep(poll_seconds)


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
