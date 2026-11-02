# SPDX-License-Identifier: Apache-2.0
"""Durable operation submission, status, cancellation, and worker orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from oak.application.context import CommandContext
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.ports import (
    EnqueuedOperation,
    OperationLease,
    OperationRecord,
    OperationSpec,
    OperationStore,
    OutboxStore,
)

ALLOWED_OPERATION_KINDS = frozenset(
    {"generate_candidates", "evaluate_candidate", "compile_bundle", "research_catalogue"}
)
FORBIDDEN_OPERATION_FIELDS = frozenset({"argv", "command", "executable", "shell", "shell_command"})
OperationHandler = Callable[[dict[str, Any]], dict[str, Any]]
# A fresh (now, lease_expires_at) pair, read from the clock when a step starts (RR-031).
LeaseRenewal = Callable[[], tuple[str, str]]
# The most operations a tenant may have queued or running at once (RR-024); `0` is no cap.
DEFAULT_OPERATIONS_PER_TENANT = 100


@dataclass(frozen=True, slots=True)
class OperationSubmission:
    operation: OperationRecord
    duplicate: bool


class OperationService:
    def __init__(
        self,
        store: OperationStore,
        *,
        environment_id: str = "local",
        maximum_active: int = DEFAULT_OPERATIONS_PER_TENANT,
    ) -> None:
        self._store = store
        self._environment_id = environment_id
        self._maximum_active = max(0, maximum_active)

    def submit(
        self,
        *,
        kind: str,
        workspace_id: str,
        case_id: str,
        request: dict[str, Any],
        context: CommandContext,
        max_attempts: int = 3,
        precondition: Callable[[], None] | None = None,
    ) -> OperationSubmission:
        self._validate_request(kind, request)
        if not context.idempotency_key:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "idempotency key is required")
        request_document = {
            "kind": kind,
            "workspace_id": workspace_id,
            "case_id": case_id,
            "request": request,
            "actor": context.actor,
            "tenant_id": context.tenant_id,
            "environment_id": self._environment_id,
            "expected_version": context.expected_version,
            "correlation_id": context.correlation_id,
            "interface_origin": context.interface_origin,
            "idempotency_key": context.idempotency_key,
            "occurred_at": context.occurred_at,
        }
        semantic_request = {
            "kind": kind,
            "workspace_id": workspace_id,
            "case_id": case_id,
            "request": request,
            "actor": context.actor,
            "tenant_id": context.tenant_id,
            "environment_id": self._environment_id,
        }
        try:
            request_digest = content_digest(canonical_json_bytes(semantic_request))
        except (TypeError, ValueError) as error:
            raise OAKError(
                "OAK-OPERATION-DOCUMENT", "operation request is not canonical JSON"
            ) from error
        identity = "\n".join(
            (
                context.tenant_id,
                self._environment_id,
                workspace_id,
                context.idempotency_key,
                request_digest,
            )
        ).encode("utf-8")
        spec = OperationSpec(
            operation_id=f"operation.{hashlib.sha256(identity).hexdigest()}",
            workspace_id=workspace_id,
            case_id=case_id,
            kind=kind,
            request_digest=request_digest,
            request=request_document,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            max_attempts=max_attempts,
            created_at=context.occurred_at,
        )
        existing = self._store.idempotent(spec)
        if existing is not None:
            return OperationSubmission(existing, duplicate=True)
        if precondition is not None:
            precondition()
        # A duplicate is answered above whatever the queue holds; a new operation joins it
        # only while the tenant is under its cap, which the store judges under one lock
        # with the insert, so two submissions cannot both find room for one (RR-024).
        enqueued: EnqueuedOperation = self._store.enqueue(spec, maximum_active=self._maximum_active)
        return OperationSubmission(enqueued.operation, enqueued.duplicate)

    def get(self, operation_id: str) -> OperationRecord:
        return self._store.get(operation_id)

    def cancel(self, operation_id: str, *, context: CommandContext) -> OperationRecord:
        if len(context.idempotency_key) < 16:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "idempotency key is required")
        return self._store.cancel(
            operation_id,
            actor=context.actor,
            idempotency_key=context.idempotency_key,
            correlation_id=context.correlation_id,
            requested_at=context.occurred_at,
        )

    @staticmethod
    def _validate_request(kind: str, request: dict[str, Any]) -> None:
        if kind not in ALLOWED_OPERATION_KINDS:
            raise OAKError("OAK-OPERATION-KIND", "operation kind is not supported")

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if str(key).casefold() in FORBIDDEN_OPERATION_FIELDS:
                        raise OAKError(
                            "OAK-OPERATION-UNSAFE-FIELD",
                            "operation request contains a prohibited execution field",
                        )
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(request)


class OperationWorker:
    """Run one typed application job under a durable lease."""

    def __init__(self, store: OperationStore, handlers: dict[str, OperationHandler]) -> None:
        self._store = store
        self._handlers = dict(handlers)

    def run_once(
        self,
        *,
        worker_id: str,
        now: str,
        lease_expires_at: str,
        renew: LeaseRenewal | None = None,
    ) -> OperationRecord | None:
        lease = self._store.claim(
            worker_id=worker_id,
            now=now,
            lease_expires_at=lease_expires_at,
        )
        if lease is None:
            return None
        handler = self._handlers.get(lease.operation.kind)
        if handler is None:
            return self._store.fail(
                lease,
                error_code="OAK-OPERATION-KIND",
                retriable=False,
                failed_at=now,
                retry_at=now,
            )
        self._store.checkpoint(
            lease,
            checkpoint={"stage": "started", "attempt": lease.operation.attempt_count},
            recorded_at=now,
        )
        lease = self._renewed(lease, renew)
        try:
            result = handler(lease.operation.request)
        except OAKError as error:
            retry_at = _retry_time(now, lease.operation.attempt_count)
            # OAK's own message for a refusal it knows, as a synchronous refusal shows it;
            # an unexpected exception keeps the generic one below (F1-20).
            return self._store.fail(
                lease,
                error_code=error.code,
                retriable=error.retriable,
                failed_at=now,
                retry_at=retry_at,
                message=error.message,
            )
        except Exception:
            return self._store.fail(
                lease,
                error_code="OAK-OPERATION-FAILED",
                retriable=False,
                failed_at=now,
                retry_at=now,
            )
        # The handler has committed its step, and a cancellation requested while it ran
        # cannot undo that: the operation succeeded, with its result, and still shows the
        # request (`cancel_requested`). Reporting it cancelled with the result dropped
        # told the client nothing happened while the case had moved on (F2-8).
        lease = self._renewed(lease, renew)
        return self._store.succeed(lease, result=result, completed_at=now)

    def _renewed(self, lease: OperationLease, renew: LeaseRenewal | None) -> OperationLease:
        """Extend the lease at a step boundary, measured from that moment rather than from
        the start of the cycle, so a long step runs under a lease of its own length; a lease
        another worker has since claimed is reported as lost here, before the step runs or
        its result is recorded (RR-031)."""

        if renew is None:
            return lease
        now, lease_expires_at = renew()
        return self._store.heartbeat(lease, now=now, lease_expires_at=lease_expires_at)


@dataclass(frozen=True, slots=True)
class WorkerCycleResult:
    operation: OperationRecord | None
    outbox_claimed: int
    outbox_applied: int


class CommunityWorker:
    """Process compiler jobs and the rebuildable local projection without runner authority."""

    def __init__(
        self,
        operation_worker: OperationWorker,
        outbox_store: OutboxStore,
        *,
        worker_id: str,
        projection_name: str = "design-case-index",
    ) -> None:
        self._operation_worker = operation_worker
        self._outbox_store = outbox_store
        self._worker_id = worker_id
        self._projection_name = projection_name

    def run_once(
        self, *, now: str, lease_expires_at: str, renew: LeaseRenewal | None = None
    ) -> WorkerCycleResult:
        operation = self._operation_worker.run_once(
            worker_id=self._worker_id,
            now=now,
            lease_expires_at=lease_expires_at,
            renew=renew,
        )
        messages = self._outbox_store.claim(
            consumer_id=self._worker_id,
            now=now,
            lease_expires_at=lease_expires_at,
            limit=100,
        )
        applied = 0
        for message in messages:
            try:
                if self._outbox_store.record_consumed(
                    message,
                    projection_name=self._projection_name,
                    processed_at=now,
                ):
                    applied += 1
                self._outbox_store.mark_delivered(
                    message,
                    consumer_id=self._worker_id,
                    delivered_at=now,
                )
            except OAKError as error:
                self._outbox_store.release(
                    message,
                    consumer_id=self._worker_id,
                    available_at=lease_expires_at,
                    error_code=error.code,
                )
            except Exception:
                self._outbox_store.release(
                    message,
                    consumer_id=self._worker_id,
                    available_at=lease_expires_at,
                    error_code="OAK-OUTBOX-CONSUMER-FAILED",
                )
        return WorkerCycleResult(
            operation=operation,
            outbox_claimed=len(messages),
            outbox_applied=applied,
        )


def _retry_time(value: str, attempt: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise OAKError("OAK-TIME-INVALID", "worker timestamp must include a timezone")
    delay_seconds = min(60, 2 ** max(0, attempt))
    return (
        (parsed.astimezone(UTC) + timedelta(seconds=delay_seconds))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
