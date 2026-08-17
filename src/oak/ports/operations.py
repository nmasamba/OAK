# SPDX-License-Identifier: Apache-2.0
"""Durable leased operation contracts."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    workspace_id: str
    case_id: str
    kind: str
    request_digest: str
    request: dict[str, Any]
    correlation_id: str
    idempotency_key: str
    max_attempts: int
    created_at: str


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    workspace_id: str
    case_id: str
    kind: str
    state: str
    version: int
    request_digest: str
    request: dict[str, Any]
    result: dict[str, Any] | None
    problem: dict[str, Any] | None
    correlation_id: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: str
    leased_by: str | None
    lease_expires_at: str | None
    cancel_requested: bool
    cancel_requested_by: str | None
    cancel_idempotency_key: str | None
    cancel_correlation_id: str | None
    cancel_requested_at: str | None
    checkpoint: dict[str, Any] | None
    created_at: str
    updated_at: str
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class EnqueuedOperation:
    operation: OperationRecord
    duplicate: bool


@dataclass(frozen=True, slots=True)
class OperationLease:
    operation: OperationRecord
    worker_id: str
    lease_expires_at: str


class OperationStore(Protocol):
    def idempotent(self, spec: OperationSpec) -> OperationRecord | None: ...

    def enqueue(self, spec: OperationSpec) -> EnqueuedOperation: ...

    def get(self, operation_id: str) -> OperationRecord: ...

    def cancel(
        self,
        operation_id: str,
        *,
        actor: str,
        idempotency_key: str,
        correlation_id: str,
        requested_at: str,
    ) -> OperationRecord: ...

    def claim(
        self, *, worker_id: str, now: str, lease_expires_at: str
    ) -> OperationLease | None: ...

    def heartbeat(
        self, lease: OperationLease, *, now: str, lease_expires_at: str
    ) -> OperationLease: ...

    def checkpoint(
        self, lease: OperationLease, *, checkpoint: dict[str, Any], recorded_at: str
    ) -> OperationRecord: ...

    def succeed(
        self, lease: OperationLease, *, result: dict[str, Any], completed_at: str
    ) -> OperationRecord: ...

    def fail(
        self,
        lease: OperationLease,
        *,
        error_code: str,
        retriable: bool,
        failed_at: str,
        retry_at: str,
    ) -> OperationRecord: ...

    def acknowledge_cancellation(
        self, lease: OperationLease, *, cancelled_at: str
    ) -> OperationRecord: ...
