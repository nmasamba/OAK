# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL bounded-retry operation leases and checkpoints."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from oak.adapters.persistence.models import job_checkpoints, operations
from oak.adapters.persistence.postgresql import _format_time, _parse_time
from oak.domain import OAKError, canonical_json_bytes
from oak.ports.operations import (
    EnqueuedOperation,
    OperationLease,
    OperationRecord,
    OperationSpec,
)

MAXIMUM_OPERATION_DOCUMENT_BYTES = 262_144
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})


class PostgreSQLOperationStore:
    """Persist operation state with tenant/environment scope on every query."""

    def __init__(
        self,
        engine: Engine,
        *,
        tenant_id: str,
        environment_id: str = "local",
    ) -> None:
        self._engine = engine
        self.tenant_id = tenant_id
        self.environment_id = environment_id

    def enqueue(self, spec: OperationSpec) -> EnqueuedOperation:
        self._validate_spec(spec)
        try:
            with self._engine.begin() as connection:
                existing = (
                    connection.execute(
                        select(operations).where(
                            self._scope(),
                            operations.c.workspace_id == spec.workspace_id,
                            operations.c.idempotency_key == spec.idempotency_key,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if existing["request_digest"] != spec.request_digest:
                        raise OAKError(
                            "OAK-IDEMPOTENCY-CONFLICT",
                            "idempotency key was already used for different operation input",
                        )
                    return EnqueuedOperation(self._record(existing), duplicate=True)
                row = (
                    connection.execute(
                        insert(operations)
                        .values(
                            tenant_id=self.tenant_id,
                            environment_id=self.environment_id,
                            operation_id=spec.operation_id,
                            workspace_id=spec.workspace_id,
                            case_id=spec.case_id,
                            kind=spec.kind,
                            state="queued",
                            version=0,
                            request_digest=spec.request_digest,
                            request=spec.request,
                            result=None,
                            problem=None,
                            correlation_id=spec.correlation_id,
                            idempotency_key=spec.idempotency_key,
                            attempt_count=0,
                            max_attempts=spec.max_attempts,
                            next_attempt_at=_parse_time(spec.created_at),
                            leased_by=None,
                            lease_expires_at=None,
                            heartbeat_at=None,
                            cancel_requested=False,
                            cancel_requested_by=None,
                            cancel_idempotency_key=None,
                            cancel_correlation_id=None,
                            cancel_requested_at=None,
                            checkpoint=None,
                            created_at=_parse_time(spec.created_at),
                            updated_at=_parse_time(spec.created_at),
                            completed_at=None,
                        )
                        .returning(operations)
                    )
                    .mappings()
                    .one()
                )
        except IntegrityError as error:
            raced_operation = self.idempotent(spec)
            if raced_operation is None:
                raise OAKError(
                    "OAK-OPERATION-CONFLICT", "operation identity already exists"
                ) from error
            return EnqueuedOperation(raced_operation, duplicate=True)
        return EnqueuedOperation(self._record(row), duplicate=False)

    def idempotent(self, spec: OperationSpec) -> OperationRecord | None:
        self._validate_spec(spec)
        with self._engine.connect() as connection:
            existing = (
                connection.execute(
                    select(operations).where(
                        self._scope(),
                        operations.c.workspace_id == spec.workspace_id,
                        operations.c.idempotency_key == spec.idempotency_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if existing is None:
            return None
        if existing["request_digest"] != spec.request_digest:
            raise OAKError(
                "OAK-IDEMPOTENCY-CONFLICT",
                "idempotency key was already used for different operation input",
            )
        return self._record(existing)

    def get(self, operation_id: str) -> OperationRecord:
        with self._engine.connect() as connection:
            row = self._operation_row(connection, operation_id)
        return self._record(row)

    def cancel(
        self,
        operation_id: str,
        *,
        actor: str,
        idempotency_key: str,
        correlation_id: str,
        requested_at: str,
    ) -> OperationRecord:
        if len(idempotency_key) < 16 or len(idempotency_key) > 240:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "cancellation idempotency key is invalid")
        requested = _parse_time(requested_at)
        with self._engine.begin() as connection:
            row = self._operation_row(connection, operation_id, for_update=True)
            state = str(row["state"])
            if state in TERMINAL_STATES or bool(row["cancel_requested"]):
                return self._record(row)
            values: dict[str, Any] = {
                "cancel_requested": True,
                "cancel_requested_by": actor,
                "cancel_idempotency_key": idempotency_key,
                "cancel_correlation_id": correlation_id,
                "cancel_requested_at": requested,
                "updated_at": requested,
                "version": int(row["version"]) + 1,
            }
            if state == "queued":
                values.update(
                    state="cancelled",
                    completed_at=requested,
                    leased_by=None,
                    lease_expires_at=None,
                )
            else:
                values["state"] = "cancelling"
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(operation_id))
                    .values(**values)
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        return self._record(updated_row)

    def claim(self, *, worker_id: str, now: str, lease_expires_at: str) -> OperationLease | None:
        now_value = _parse_time(now)
        lease_value = _parse_time(lease_expires_at)
        if lease_value <= now_value:
            raise OAKError("OAK-OPERATION-LEASE", "operation lease must expire after claim time")
        with self._engine.begin() as connection:
            self._expire_exhausted(connection, now_value)
            row = (
                connection.execute(
                    select(operations)
                    .where(
                        self._scope(),
                        operations.c.cancel_requested.is_(False),
                        operations.c.attempt_count < operations.c.max_attempts,
                        operations.c.next_attempt_at <= now_value,
                        or_(
                            operations.c.state == "queued",
                            and_(
                                operations.c.state == "running",
                                operations.c.lease_expires_at <= now_value,
                            ),
                        ),
                    )
                    .order_by(operations.c.next_attempt_at, operations.c.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(str(row["operation_id"])))
                    .values(
                        state="running",
                        version=int(row["version"]) + 1,
                        attempt_count=int(row["attempt_count"]) + 1,
                        leased_by=worker_id,
                        lease_expires_at=lease_value,
                        heartbeat_at=now_value,
                        updated_at=now_value,
                        problem=None,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        operation = self._record(updated_row)
        return OperationLease(operation, worker_id=worker_id, lease_expires_at=lease_expires_at)

    def heartbeat(
        self, lease: OperationLease, *, now: str, lease_expires_at: str
    ) -> OperationLease:
        now_value = _parse_time(now)
        lease_value = _parse_time(lease_expires_at)
        if lease_value <= now_value:
            raise OAKError("OAK-OPERATION-LEASE", "heartbeat lease must extend into the future")
        with self._engine.begin() as connection:
            row = self._require_lease(connection, lease, now=now_value)
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(lease.operation.operation_id))
                    .values(
                        version=int(row["version"]) + 1,
                        heartbeat_at=now_value,
                        lease_expires_at=lease_value,
                        updated_at=now_value,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        operation = self._record(updated_row)
        return OperationLease(operation, lease.worker_id, lease_expires_at)

    def checkpoint(
        self, lease: OperationLease, *, checkpoint: dict[str, Any], recorded_at: str
    ) -> OperationRecord:
        self._validate_document(checkpoint, label="checkpoint")
        recorded = _parse_time(recorded_at)
        with self._engine.begin() as connection:
            row = self._require_lease(connection, lease, now=recorded)
            sequence = (
                int(
                    connection.scalar(
                        select(
                            func.coalesce(func.max(job_checkpoints.c.checkpoint_sequence), 0)
                        ).where(
                            self._scope(job_checkpoints),
                            job_checkpoints.c.operation_id == lease.operation.operation_id,
                        )
                    )
                    or 0
                )
                + 1
            )
            connection.execute(
                insert(job_checkpoints).values(
                    tenant_id=self.tenant_id,
                    environment_id=self.environment_id,
                    operation_id=lease.operation.operation_id,
                    checkpoint_sequence=sequence,
                    checkpoint=checkpoint,
                    created_at=recorded,
                )
            )
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(lease.operation.operation_id))
                    .values(
                        version=int(row["version"]) + 1,
                        checkpoint=checkpoint,
                        updated_at=recorded,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        return self._record(updated_row)

    def succeed(
        self, lease: OperationLease, *, result: dict[str, Any], completed_at: str
    ) -> OperationRecord:
        self._validate_document(result, label="operation result")
        completed = _parse_time(completed_at)
        with self._engine.begin() as connection:
            row = self._require_lease(connection, lease, now=completed)
            cancelled = bool(row["cancel_requested"])
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(lease.operation.operation_id))
                    .values(
                        state="cancelled" if cancelled else "succeeded",
                        version=int(row["version"]) + 1,
                        result=None if cancelled else result,
                        problem=None,
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=completed,
                        completed_at=completed,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        return self._record(updated_row)

    def fail(
        self,
        lease: OperationLease,
        *,
        error_code: str,
        retriable: bool,
        failed_at: str,
        retry_at: str,
    ) -> OperationRecord:
        self._validate_error_code(error_code)
        failed = _parse_time(failed_at)
        retry = _parse_time(retry_at)
        with self._engine.begin() as connection:
            row = self._require_lease(connection, lease, now=failed)
            will_retry = (
                retriable
                and not bool(row["cancel_requested"])
                and int(row["attempt_count"]) < int(row["max_attempts"])
            )
            state = (
                "queued"
                if will_retry
                else ("cancelled" if bool(row["cancel_requested"]) else "failed")
            )
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(lease.operation.operation_id))
                    .values(
                        state=state,
                        version=int(row["version"]) + 1,
                        problem={
                            "code": error_code,
                            "message": "operation failed safely",
                            "retriable": will_retry,
                        },
                        next_attempt_at=retry if will_retry else failed,
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=failed,
                        completed_at=None if will_retry else failed,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        return self._record(updated_row)

    def acknowledge_cancellation(
        self, lease: OperationLease, *, cancelled_at: str
    ) -> OperationRecord:
        cancelled = _parse_time(cancelled_at)
        with self._engine.begin() as connection:
            row = self._require_lease(connection, lease, now=cancelled)
            if not bool(row["cancel_requested"]):
                raise OAKError(
                    "OAK-OPERATION-NOT-CANCELLING", "operation has no cancellation request"
                )
            updated_row = (
                connection.execute(
                    update(operations)
                    .where(self._identity(lease.operation.operation_id))
                    .values(
                        state="cancelled",
                        version=int(row["version"]) + 1,
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=cancelled,
                        completed_at=cancelled,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
        return self._record(updated_row)

    def _expire_exhausted(self, connection: Any, now: Any) -> None:
        connection.execute(
            update(operations)
            .where(
                self._scope(),
                operations.c.state == "running",
                operations.c.lease_expires_at <= now,
                operations.c.attempt_count >= operations.c.max_attempts,
            )
            .values(
                state="failed",
                problem={
                    "code": "OAK-OPERATION-ATTEMPTS-EXHAUSTED",
                    "message": "operation failed safely",
                    "retriable": False,
                },
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )
        connection.execute(
            update(operations)
            .where(
                self._scope(),
                operations.c.state == "cancelling",
                operations.c.lease_expires_at <= now,
            )
            .values(
                state="cancelled",
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )

    def _require_lease(self, connection: Any, lease: OperationLease, *, now: Any) -> Any:
        row = self._operation_row(connection, lease.operation.operation_id, for_update=True)
        if (
            row["state"] not in {"running", "cancelling"}
            or row["leased_by"] != lease.worker_id
            or row["lease_expires_at"] is None
            or row["lease_expires_at"] <= now
        ):
            raise OAKError("OAK-OPERATION-LEASE-LOST", "operation lease is no longer current")
        return row

    def _operation_row(
        self, connection: Any, operation_id: str, *, for_update: bool = False
    ) -> Any:
        statement = select(operations).where(self._identity(operation_id))
        if for_update:
            statement = statement.with_for_update()
        row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            raise OAKError("OAK-OPERATION-NOT-FOUND", "operation was not found")
        return row

    def _identity(self, operation_id: str) -> Any:
        return and_(self._scope(), operations.c.operation_id == operation_id)

    def _scope(self, table: Any = operations) -> Any:
        return and_(
            table.c.tenant_id == self.tenant_id,
            table.c.environment_id == self.environment_id,
        )

    def _record(self, row: Any) -> OperationRecord:
        request = row["request"]
        if not isinstance(request, dict):
            raise OAKError("OAK-OPERATION-CORRUPT", "operation request is not an object")
        result = row["result"]
        problem = row["problem"]
        checkpoint = row["checkpoint"]
        return OperationRecord(
            operation_id=str(row["operation_id"]),
            workspace_id=str(row["workspace_id"]),
            case_id=str(row["case_id"]),
            kind=str(row["kind"]),
            state=str(row["state"]),
            version=int(row["version"]),
            request_digest=str(row["request_digest"]),
            request=request,
            result=result if isinstance(result, dict) else None,
            problem=problem if isinstance(problem, dict) else None,
            correlation_id=str(row["correlation_id"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            next_attempt_at=_format_time(row["next_attempt_at"]),
            leased_by=str(row["leased_by"]) if row["leased_by"] is not None else None,
            lease_expires_at=(
                _format_time(row["lease_expires_at"])
                if row["lease_expires_at"] is not None
                else None
            ),
            cancel_requested=bool(row["cancel_requested"]),
            cancel_requested_by=(
                str(row["cancel_requested_by"]) if row["cancel_requested_by"] is not None else None
            ),
            cancel_idempotency_key=(
                str(row["cancel_idempotency_key"])
                if row["cancel_idempotency_key"] is not None
                else None
            ),
            cancel_correlation_id=(
                str(row["cancel_correlation_id"])
                if row["cancel_correlation_id"] is not None
                else None
            ),
            cancel_requested_at=(
                _format_time(row["cancel_requested_at"])
                if row["cancel_requested_at"] is not None
                else None
            ),
            checkpoint=checkpoint if isinstance(checkpoint, dict) else None,
            created_at=_format_time(row["created_at"]),
            updated_at=_format_time(row["updated_at"]),
            completed_at=(
                _format_time(row["completed_at"]) if row["completed_at"] is not None else None
            ),
        )

    def _validate_spec(self, spec: OperationSpec) -> None:
        if not 1 <= spec.max_attempts <= 10:
            raise OAKError("OAK-OPERATION-ATTEMPTS", "operation attempts must be between 1 and 10")
        if len(spec.idempotency_key) < 16 or len(spec.idempotency_key) > 240:
            raise OAKError("OAK-IDEMPOTENCY-KEY", "operation idempotency key is invalid")
        self._validate_document(spec.request, label="operation request")
        _parse_time(spec.created_at)

    @staticmethod
    def _validate_document(document: dict[str, Any], *, label: str) -> None:
        try:
            content = canonical_json_bytes(document)
        except (TypeError, ValueError) as error:
            raise OAKError("OAK-OPERATION-DOCUMENT", f"{label} is not canonical JSON") from error
        if len(content) > MAXIMUM_OPERATION_DOCUMENT_BYTES:
            raise OAKError("OAK-OPERATION-SIZE", f"{label} exceeds the size limit")

    @staticmethod
    def _validate_error_code(error_code: str) -> None:
        if not error_code.startswith("OAK-") or len(error_code) > 120:
            raise OAKError("OAK-OPERATION-ERROR-CODE", "operation error code is invalid")
