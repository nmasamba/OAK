# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-006 operation submission ordering and idempotency tests."""

from typing import Any

import pytest

from oak.application import CommandContext, OperationService
from oak.domain import OAKError
from oak.ports import EnqueuedOperation, OperationRecord, OperationSpec

NOW = "2026-08-17T11:00:00Z"


def _record() -> OperationRecord:
    return OperationRecord(
        operation_id="operation.existing",
        workspace_id="workspace.operations",
        case_id="design-case.operations",
        kind="generate_candidates",
        state="succeeded",
        version=2,
        request_digest=f"sha256:{'1' * 64}",
        request={},
        result={"candidate_ids": ["candidate-01"]},
        problem=None,
        correlation_id="correlation-existing",
        attempt_count=1,
        max_attempts=3,
        next_attempt_at=NOW,
        leased_by=None,
        lease_expires_at=None,
        cancel_requested=False,
        cancel_requested_by=None,
        cancel_idempotency_key=None,
        cancel_correlation_id=None,
        cancel_requested_at=None,
        checkpoint={"stage": "completed"},
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
    )


class _SubmissionStore:
    def __init__(self, existing: OperationRecord | None) -> None:
        self.existing = existing
        self.enqueued = False
        self.seen_specs: list[OperationSpec] = []

    def idempotent(self, spec: OperationSpec) -> OperationRecord | None:
        self.seen_specs.append(spec)
        return self.existing

    def enqueue(self, spec: OperationSpec) -> EnqueuedOperation:
        del spec
        self.enqueued = True
        assert self.existing is not None
        return EnqueuedOperation(self.existing, duplicate=False)

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected operation-store call: {name}")


def _context() -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key="operation-submit-0001",
        expected_version="0.1.1",
        correlation_id="correlation-submit-0001",
        interface_origin="rest",
        occurred_at=NOW,
    )


def test_completed_duplicate_returns_before_current_version_precondition() -> None:
    record = _record()
    store = _SubmissionStore(record)
    service = OperationService(store)  # type: ignore[arg-type]
    precondition_called = False

    def stale_precondition() -> None:
        nonlocal precondition_called
        precondition_called = True
        raise OAKError("OAK-EXPECTED-VERSION", "stale")

    result = service.submit(
        kind="generate_candidates",
        workspace_id=record.workspace_id,
        case_id=record.case_id,
        request={},
        context=_context(),
        precondition=stale_precondition,
    )

    assert result.operation == record
    assert result.duplicate is True
    assert precondition_called is False
    assert store.enqueued is False


def test_new_submission_checks_precondition_before_enqueue() -> None:
    store = _SubmissionStore(None)
    service = OperationService(store)  # type: ignore[arg-type]

    with pytest.raises(OAKError) as error:
        service.submit(
            kind="generate_candidates",
            workspace_id="workspace.operations",
            case_id="design-case.operations",
            request={},
            context=_context(),
            precondition=lambda: (_ for _ in ()).throw(OAKError("OAK-EXPECTED-VERSION", "stale")),
        )

    assert error.value.code == "OAK-EXPECTED-VERSION"
    assert store.enqueued is False


def test_retry_metadata_does_not_change_operation_identity() -> None:
    record = _record()
    first_store = _SubmissionStore(record)
    retry_store = _SubmissionStore(record)
    first_context = _context()
    retry_context = CommandContext(
        actor=first_context.actor,
        tenant_id=first_context.tenant_id,
        idempotency_key=first_context.idempotency_key,
        expected_version="0.1.7",
        correlation_id="correlation-retry-0001",
        interface_origin="cli",
        occurred_at="2026-08-17T12:00:00Z",
    )

    for store, context in ((first_store, first_context), (retry_store, retry_context)):
        OperationService(store).submit(  # type: ignore[arg-type]
            kind="generate_candidates",
            workspace_id=record.workspace_id,
            case_id=record.case_id,
            request={},
            context=context,
        )

    assert first_store.seen_specs[0].request_digest == retry_store.seen_specs[0].request_digest
    assert first_store.seen_specs[0].operation_id == retry_store.seen_specs[0].operation_id
    assert first_store.seen_specs[0].request != retry_store.seen_specs[0].request
