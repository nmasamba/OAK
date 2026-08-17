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
    OperationRecord,
    OperationSpec,
    OperationStore,
    OutboxStore,
)

ALLOWED_OPERATION_KINDS = frozenset({"generate_candidates", "evaluate_candidate", "compile_bundle"})
FORBIDDEN_OPERATION_FIELDS = frozenset({"argv", "command", "executable", "shell", "shell_command"})
OperationHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class OperationSubmission:
    operation: OperationRecord
    duplicate: bool


class OperationService:
    def __init__(self, store: OperationStore, *, environment_id: str = "local") -> None:
        self._store = store
        self._environment_id = environment_id

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
        enqueued: EnqueuedOperation = self._store.enqueue(spec)
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
        try:
            result = handler(lease.operation.request)
        except OAKError as error:
            retry_at = _retry_time(now, lease.operation.attempt_count)
            return self._store.fail(
                lease,
                error_code=error.code,
                retriable=error.retriable,
                failed_at=now,
                retry_at=retry_at,
            )
        except Exception:
            return self._store.fail(
                lease,
                error_code="OAK-OPERATION-FAILED",
                retriable=False,
                failed_at=now,
                retry_at=now,
            )
        current = self._store.get(lease.operation.operation_id)
        if current.cancel_requested:
            return self._store.acknowledge_cancellation(lease, cancelled_at=now)
        return self._store.succeed(lease, result=result, completed_at=now)


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

    def run_once(self, *, now: str, lease_expires_at: str) -> WorkerCycleResult:
        operation = self._operation_worker.run_once(
            worker_id=self._worker_id,
            now=now,
            lease_expires_at=lease_expires_at,
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
