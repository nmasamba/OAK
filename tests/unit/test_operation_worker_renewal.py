# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-033 (RR-031): the operation worker extends its lease between its steps."""

from __future__ import annotations

from typing import Any

import pytest

from oak.application.operations import OperationWorker
from oak.domain import OAKError
from oak.ports import OperationSpec
from tests.mcp_support import MemoryOperationStore

NOW = "2026-10-29T12:00:00Z"


def _spec() -> OperationSpec:
    return OperationSpec(
        operation_id="operation.renewal",
        workspace_id="workspace.renewal",
        case_id="design-case.renewal",
        kind="generate_candidates",
        request_digest="sha256:" + "1" * 64,
        request={"case_id": "design-case.renewal"},
        correlation_id="correlation-renewal",
        idempotency_key="renewal-0000000001",
        max_attempts=3,
        created_at=NOW,
    )


class _Store(MemoryOperationStore):
    def __init__(self) -> None:
        super().__init__()
        self.renewals: list[tuple[str, str]] = []

    def heartbeat(self, lease: Any, *, now: str, lease_expires_at: str) -> Any:
        self.renewals.append((now, lease_expires_at))
        return super().heartbeat(lease, now=now, lease_expires_at=lease_expires_at)


def test_the_worker_renews_before_the_handler_and_before_recording_its_result() -> None:
    store = _Store()
    store.enqueue(_spec())
    moments = iter(
        [
            ("2026-10-29T12:00:01Z", "2026-10-29T12:02:01Z"),
            ("2026-10-29T12:00:40Z", "2026-10-29T12:02:40Z"),
        ]
    )
    worker = OperationWorker(store, {"generate_candidates": lambda request: {"ok": True}})
    record = worker.run_once(
        worker_id="worker-a",
        now=NOW,
        lease_expires_at="2026-10-29T12:02:00Z",
        renew=lambda: next(moments),
    )
    assert record is not None and record.state == "succeeded"
    assert store.renewals == [
        ("2026-10-29T12:00:01Z", "2026-10-29T12:02:01Z"),
        ("2026-10-29T12:00:40Z", "2026-10-29T12:02:40Z"),
    ]


def test_without_a_renewal_the_lease_is_the_cycle_s_own() -> None:
    store = _Store()
    store.enqueue(_spec())
    worker = OperationWorker(store, {"generate_candidates": lambda request: {"ok": True}})
    record = worker.run_once(worker_id="worker-a", now=NOW, lease_expires_at="2026-10-29T12:02:00Z")
    assert record is not None and record.state == "succeeded"
    assert store.renewals == []


def test_a_lease_another_worker_took_is_reported_lost_at_the_renewal() -> None:
    """Review R6: the in-memory store now refuses a renewal of a lease it no longer holds
    for this worker, as the PostgreSQL store does, so the loss is seen before the step."""

    from dataclasses import replace

    store = _Store()
    store.enqueue(_spec())

    def taken_over() -> tuple[str, str]:
        record = store.records["operation.renewal"]
        store.records["operation.renewal"] = replace(record, leased_by="worker-b")
        return ("2026-10-29T12:00:01Z", "2026-10-29T12:02:01Z")

    worker = OperationWorker(store, {"generate_candidates": lambda request: {"ok": True}})
    with pytest.raises(OAKError) as lost:
        worker.run_once(
            worker_id="worker-a",
            now=NOW,
            lease_expires_at="2026-10-29T12:02:00Z",
            renew=taken_over,
        )
    assert lost.value.code == "OAK-OPERATION-LEASE-LOST"
    assert store.records["operation.renewal"].state == "running", "the handler never ran"
