# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-004 durable lease, cancellation, checkpoint, and retry contracts."""

import hashlib
import os
from pathlib import Path

import pytest

from oak.adapters.persistence import PostgreSQLOperationStore, create_postgresql_engine
from oak.domain import OAKError
from oak.ports import OperationSpec

pytestmark = pytest.mark.integration
NOW = "2026-08-17T11:00:00Z"


@pytest.fixture
def operation_store(tmp_path: Path) -> PostgreSQLOperationStore:
    database_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for PostgreSQL operation tests")
    environment = f"test-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]}"
    engine = create_postgresql_engine(database_url)
    store = PostgreSQLOperationStore(
        engine,
        tenant_id="local",
        environment_id=environment,
    )
    yield store
    engine.dispose()


def _spec(
    operation_id: str,
    *,
    key: str,
    request_digest: str = f"sha256:{'1' * 64}",
    max_attempts: int = 3,
) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        workspace_id="workspace.operations",
        case_id="design-case.operations",
        kind="evaluate_candidate",
        request_digest=request_digest,
        request={"candidate_id": "candidate-03"},
        correlation_id=f"correlation-{operation_id}",
        idempotency_key=key,
        max_attempts=max_attempts,
        created_at=NOW,
    )


def test_operation_enqueue_is_durable_and_idempotent(
    operation_store: PostgreSQLOperationStore,
) -> None:
    spec = _spec("operation.enqueue", key="operation-enqueue-0001")

    first = operation_store.enqueue(spec)
    retry = operation_store.enqueue(spec)

    assert first.duplicate is False
    assert retry.duplicate is True
    assert retry.operation == first.operation
    assert operation_store.get(spec.operation_id) == first.operation
    with pytest.raises(OAKError) as conflict:
        operation_store.enqueue(
            _spec(
                "operation.other-id",
                key=spec.idempotency_key,
                request_digest=f"sha256:{'2' * 64}",
            )
        )
    assert conflict.value.code == "OAK-IDEMPOTENCY-CONFLICT"


def test_operation_lease_heartbeat_checkpoint_and_success(
    operation_store: PostgreSQLOperationStore,
) -> None:
    spec = _spec("operation.success", key="operation-success-0001")
    operation_store.enqueue(spec)

    lease = operation_store.claim(
        worker_id="worker-a",
        now="2026-08-17T11:00:01Z",
        lease_expires_at="2026-08-17T11:01:01Z",
    )

    assert lease is not None
    assert lease.operation.state == "running"
    assert lease.operation.attempt_count == 1
    assert (
        operation_store.claim(
            worker_id="worker-b",
            now="2026-08-17T11:00:02Z",
            lease_expires_at="2026-08-17T11:01:02Z",
        )
        is None
    )
    lease = operation_store.heartbeat(
        lease,
        now="2026-08-17T11:00:30Z",
        lease_expires_at="2026-08-17T11:02:00Z",
    )
    checkpointed = operation_store.checkpoint(
        lease,
        checkpoint={"stage": "evaluation_complete", "candidate_id": "candidate-03"},
        recorded_at="2026-08-17T11:00:40Z",
    )
    assert checkpointed.checkpoint == {
        "stage": "evaluation_complete",
        "candidate_id": "candidate-03",
    }
    succeeded = operation_store.succeed(
        lease,
        result={"evaluation_id": "evaluation.candidate-03"},
        completed_at="2026-08-17T11:00:50Z",
    )
    assert succeeded.state == "succeeded"
    assert succeeded.result == {"evaluation_id": "evaluation.candidate-03"}
    assert succeeded.leased_by is None
    assert succeeded.completed_at == "2026-08-17T11:00:50Z"


def test_operation_cancellation_is_durable_and_cooperative(
    operation_store: PostgreSQLOperationStore,
) -> None:
    queued = _spec("operation.cancel-queued", key="operation-cancel-queued-0001")
    operation_store.enqueue(queued)
    cancelled_queued = operation_store.cancel(
        queued.operation_id,
        actor="local-user",
        idempotency_key="cancel-operation-queued-0001",
        correlation_id="correlation-cancel-queued",
        requested_at="2026-08-17T11:00:01Z",
    )
    assert cancelled_queued.state == "cancelled"
    assert cancelled_queued.cancel_requested is True
    assert operation_store.get(queued.operation_id).state == "cancelled"

    running = _spec("operation.cancel-running", key="operation-cancel-running-0001")
    operation_store.enqueue(running)
    lease = operation_store.claim(
        worker_id="worker-a",
        now="2026-08-17T11:00:02Z",
        lease_expires_at="2026-08-17T11:01:02Z",
    )
    assert lease is not None
    cancelling = operation_store.cancel(
        running.operation_id,
        actor="local-user",
        idempotency_key="cancel-operation-running-0001",
        correlation_id="correlation-cancel-running",
        requested_at="2026-08-17T11:00:03Z",
    )
    assert cancelling.state == "cancelling"
    assert cancelling.cancel_requested is True
    cancelled = operation_store.acknowledge_cancellation(
        lease,
        cancelled_at="2026-08-17T11:00:04Z",
    )
    assert cancelled.state == "cancelled"
    assert cancelled.result is None


def test_operation_lease_expiry_retry_backoff_and_terminal_failure(
    operation_store: PostgreSQLOperationStore,
) -> None:
    spec = _spec(
        "operation.retry",
        key="operation-retry-0001",
        max_attempts=2,
    )
    operation_store.enqueue(spec)
    first = operation_store.claim(
        worker_id="worker-a",
        now="2026-08-17T11:00:01Z",
        lease_expires_at="2026-08-17T11:01:01Z",
    )
    assert first is not None
    assert (
        operation_store.claim(
            worker_id="worker-b",
            now="2026-08-17T11:00:30Z",
            lease_expires_at="2026-08-17T11:01:30Z",
        )
        is None
    )

    reclaimed = operation_store.claim(
        worker_id="worker-b",
        now="2026-08-17T11:02:00Z",
        lease_expires_at="2026-08-17T11:03:00Z",
    )
    assert reclaimed is not None
    assert reclaimed.operation.operation_id == spec.operation_id
    assert reclaimed.operation.attempt_count == 2
    failed = operation_store.fail(
        reclaimed,
        error_code="OAK-EVALUATION-TRANSIENT",
        retriable=True,
        failed_at="2026-08-17T11:02:10Z",
        retry_at="2026-08-17T11:04:10Z",
    )
    assert failed.state == "failed"
    assert failed.problem == {
        "code": "OAK-EVALUATION-TRANSIENT",
        "message": "operation failed safely",
        "retriable": False,
    }
    assert failed.attempt_count == failed.max_attempts == 2
    assert (
        operation_store.claim(
            worker_id="worker-c",
            now="2026-08-17T11:05:00Z",
            lease_expires_at="2026-08-17T11:06:00Z",
        )
        is None
    )


def test_expired_final_attempt_is_swept_to_safe_failure(
    operation_store: PostgreSQLOperationStore,
) -> None:
    spec = _spec(
        "operation.crash-final",
        key="operation-crash-final-0001",
        max_attempts=1,
    )
    operation_store.enqueue(spec)
    lease = operation_store.claim(
        worker_id="worker-a",
        now="2026-08-17T11:00:01Z",
        lease_expires_at="2026-08-17T11:01:01Z",
    )
    assert lease is not None

    assert (
        operation_store.claim(
            worker_id="worker-b",
            now="2026-08-17T11:02:00Z",
            lease_expires_at="2026-08-17T11:03:00Z",
        )
        is None
    )
    swept = operation_store.get(spec.operation_id)
    assert swept.state == "failed"
    assert swept.problem == {
        "code": "OAK-OPERATION-ATTEMPTS-EXHAUSTED",
        "message": "operation failed safely",
        "retriable": False,
    }
