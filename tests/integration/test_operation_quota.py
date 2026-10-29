# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-034 (RR-024): a tenant may have at most a configured number of operations queued
or running; a duplicate submission is still answered, and a finished one makes room."""

from __future__ import annotations

import threading

import pytest

from oak.application import (
    DEFAULT_OPERATIONS_PER_TENANT,
    CommandContext,
    OperationService,
    OperationWorker,
)
from oak.domain import OAKError
from tests.mcp_support import MemoryOperationStore

pytestmark = pytest.mark.integration
NOW = "2026-10-29T12:00:00Z"
LATER = "2026-10-29T12:02:00Z"


def _context(key: str) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=None,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


def _submit(service: OperationService, key: str) -> bool:
    submission = service.submit(
        kind="generate_candidates",
        workspace_id="workspace.quota",
        case_id="design-case.quota",
        request={"case_id": "design-case.quota"},
        context=_context(key),
    )
    return submission.duplicate


def test_the_cap_refuses_a_new_operation_past_it_and_a_duplicate_still_answers() -> None:
    store = MemoryOperationStore()
    service = OperationService(store, environment_id="quota-test", maximum_active=2)
    assert _submit(service, "quota-first-0000001") is False
    assert _submit(service, "quota-second-000001") is False
    assert store.active_count() == 2
    with pytest.raises(OAKError) as refusal:
        _submit(service, "quota-third-0000001")
    assert refusal.value.code == "OAK-OPERATION-QUOTA"
    assert refusal.value.retriable is True
    assert "2 operation(s)" in refusal.value.message
    assert store.active_count() == 2, "the refused operation was queued anyway"
    # The same request again is the same operation, whatever the queue holds.
    assert _submit(service, "quota-first-0000001") is True

    worker = OperationWorker(store, {"generate_candidates": lambda request: {"ok": True}})
    record = worker.run_once(worker_id="w", now=NOW, lease_expires_at=LATER)
    assert record is not None and record.state == "succeeded"
    assert store.active_count() == 1
    assert _submit(service, "quota-third-0000001") is False


def test_a_running_operation_counts_and_a_failed_one_does_not() -> None:
    store = MemoryOperationStore()
    service = OperationService(store, environment_id="quota-test", maximum_active=1)
    _submit(service, "quota-running-00001")
    lease = store.claim(worker_id="w", now=NOW, lease_expires_at=LATER)
    assert lease is not None and store.active_count() == 1
    with pytest.raises(OAKError) as refusal:
        _submit(service, "quota-running-00002")
    assert refusal.value.code == "OAK-OPERATION-QUOTA"
    store.fail(
        lease, error_code="OAK-OPERATION-FAILED", retriable=False, failed_at=NOW, retry_at=NOW
    )
    assert store.active_count() == 0
    assert _submit(service, "quota-running-00002") is False


def test_zero_means_no_cap_and_the_default_is_generous() -> None:
    store = MemoryOperationStore()
    unlimited = OperationService(store, environment_id="quota-test", maximum_active=0)
    for index in range(DEFAULT_OPERATIONS_PER_TENANT + 5):
        _submit(unlimited, f"quota-open-{index:08d}")
    assert store.active_count() == DEFAULT_OPERATIONS_PER_TENANT + 5

    assert DEFAULT_OPERATIONS_PER_TENANT >= 100
    capped = OperationService(MemoryOperationStore(), environment_id="quota-test")
    for index in range(DEFAULT_OPERATIONS_PER_TENANT):
        _submit(capped, f"quota-default-{index:05d}")
    with pytest.raises(OAKError) as refusal:
        _submit(capped, "quota-default-past")
    assert refusal.value.code == "OAK-OPERATION-QUOTA"


def test_the_cap_holds_when_submissions_race() -> None:
    """Review L1: the count and the insert are one locked step in the store, so two
    submissions arriving together cannot both find room for one."""

    store = MemoryOperationStore()
    service = OperationService(store, environment_id="quota-test", maximum_active=1)
    outcomes: list[str] = []
    gate = threading.Barrier(2)

    def submit(key: str) -> None:
        gate.wait()
        try:
            _submit(service, key)
            outcomes.append("queued")
        except OAKError as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=submit, args=(f"quota-race-{n:08d}",)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["OAK-OPERATION-QUOTA", "queued"]
    assert store.active_count() == 1
