# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL at-least-once outbox claiming and consumer deduplication."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from oak.adapters.persistence.models import (
    outbox_consumer_receipts,
    outbox_events,
    projection_positions,
)
from oak.adapters.persistence.postgresql import _format_time, _parse_time
from oak.domain import OAKError
from oak.ports.events import OutboxLag, OutboxMessage


class PostgreSQLOutboxStore:
    """Lease outbox rows without converting at-least-once into an exactly-once claim."""

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

    def claim(
        self,
        *,
        consumer_id: str,
        now: str,
        lease_expires_at: str,
        limit: int = 100,
    ) -> tuple[OutboxMessage, ...]:
        if not 1 <= limit <= 100:
            raise OAKError("OAK-OUTBOX-LIMIT", "outbox claim limit must be between 1 and 100")
        now_value = _parse_time(now)
        lease_value = _parse_time(lease_expires_at)
        if lease_value <= now_value:
            raise OAKError("OAK-OUTBOX-LEASE", "outbox lease must expire after claim time")
        with self._engine.begin() as connection:
            rows = list(
                connection.execute(
                    select(outbox_events)
                    .where(
                        self._scope(outbox_events),
                        outbox_events.c.delivered_at.is_(None),
                        outbox_events.c.available_at <= now_value,
                        or_(
                            outbox_events.c.claim_expires_at.is_(None),
                            outbox_events.c.claim_expires_at <= now_value,
                        ),
                    )
                    .order_by(
                        outbox_events.c.occurred_at,
                        outbox_events.c.workspace_id,
                        outbox_events.c.aggregate_sequence,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).mappings()
            )
            messages: list[OutboxMessage] = []
            for row in rows:
                attempts = int(row["delivery_attempts"]) + 1
                connection.execute(
                    update(outbox_events)
                    .where(self._identity(row))
                    .values(
                        claimed_by=consumer_id,
                        claim_expires_at=lease_value,
                        delivery_attempts=attempts,
                        last_error_code=None,
                    )
                )
                messages.append(self._message(row, delivery_attempts=attempts))
        return tuple(messages)

    def mark_delivered(
        self,
        message: OutboxMessage,
        *,
        consumer_id: str,
        delivered_at: str,
    ) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(
                update(outbox_events)
                .where(
                    self._message_identity(message),
                    outbox_events.c.claimed_by == consumer_id,
                    outbox_events.c.delivered_at.is_(None),
                )
                .values(
                    delivered_at=_parse_time(delivered_at),
                    claimed_by=None,
                    claim_expires_at=None,
                    last_error_code=None,
                )
            )
            if result.rowcount != 1:
                raise OAKError(
                    "OAK-OUTBOX-LEASE-LOST", "outbox delivery lease is no longer current"
                )

    def release(
        self,
        message: OutboxMessage,
        *,
        consumer_id: str,
        available_at: str,
        error_code: str,
    ) -> None:
        if not error_code or len(error_code) > 120:
            raise OAKError("OAK-OUTBOX-ERROR-CODE", "outbox error code is invalid")
        with self._engine.begin() as connection:
            result = connection.execute(
                update(outbox_events)
                .where(
                    self._message_identity(message),
                    outbox_events.c.claimed_by == consumer_id,
                    outbox_events.c.delivered_at.is_(None),
                )
                .values(
                    available_at=_parse_time(available_at),
                    claimed_by=None,
                    claim_expires_at=None,
                    last_error_code=error_code,
                )
            )
            if result.rowcount != 1:
                raise OAKError(
                    "OAK-OUTBOX-LEASE-LOST", "outbox delivery lease is no longer current"
                )

    def record_consumed(
        self,
        message: OutboxMessage,
        *,
        projection_name: str,
        processed_at: str,
    ) -> bool:
        if not projection_name or len(projection_name) > 160:
            raise OAKError("OAK-PROJECTION-NAME", "projection name is invalid")
        processed = _parse_time(processed_at)
        with self._engine.begin() as connection:
            inserted_event_id = connection.scalar(
                postgresql_insert(outbox_consumer_receipts)
                .values(
                    tenant_id=self.tenant_id,
                    environment_id=self.environment_id,
                    consumer_name=projection_name,
                    event_id=message.event_id,
                    processed_at=processed,
                )
                .on_conflict_do_nothing(
                    index_elements=(
                        outbox_consumer_receipts.c.tenant_id,
                        outbox_consumer_receipts.c.environment_id,
                        outbox_consumer_receipts.c.consumer_name,
                        outbox_consumer_receipts.c.event_id,
                    )
                )
                .returning(outbox_consumer_receipts.c.event_id)
            )
            if inserted_event_id is None:
                return False
            excluded = postgresql_insert(projection_positions).excluded
            connection.execute(
                postgresql_insert(projection_positions)
                .values(
                    tenant_id=self.tenant_id,
                    environment_id=self.environment_id,
                    projection_name=projection_name,
                    aggregate_id=message.aggregate_id,
                    indexed_through=message.aggregate_sequence,
                    updated_at=processed,
                )
                .on_conflict_do_update(
                    index_elements=(
                        projection_positions.c.tenant_id,
                        projection_positions.c.environment_id,
                        projection_positions.c.projection_name,
                        projection_positions.c.aggregate_id,
                    ),
                    set_={
                        "indexed_through": func.greatest(
                            projection_positions.c.indexed_through,
                            excluded.indexed_through,
                        ),
                        "updated_at": excluded.updated_at,
                    },
                )
            )
        return True

    def lag(self, *, projection_name: str) -> OutboxLag:
        with self._engine.connect() as connection:
            pending = (
                connection.execute(
                    select(
                        func.count().label("count"),
                        func.min(outbox_events.c.occurred_at).label("oldest"),
                        func.coalesce(func.max(outbox_events.c.aggregate_sequence), 0).label(
                            "latest"
                        ),
                    ).where(
                        self._scope(outbox_events),
                        outbox_events.c.delivered_at.is_(None),
                    )
                )
                .mappings()
                .one()
            )
            latest = int(
                connection.scalar(
                    select(func.coalesce(func.max(outbox_events.c.aggregate_sequence), 0)).where(
                        self._scope(outbox_events)
                    )
                )
                or 0
            )
            indexed = int(
                connection.scalar(
                    select(
                        func.coalesce(func.max(projection_positions.c.indexed_through), 0)
                    ).where(self._projection_scope(projection_name))
                )
                or 0
            )
        oldest = pending["oldest"]
        return OutboxLag(
            pending_events=int(pending["count"]),
            oldest_pending_at=_format_time(oldest) if oldest is not None else None,
            latest_sequence=latest,
            indexed_through=indexed,
        )

    def _scope(self, table: Any) -> Any:
        return and_(
            table.c.tenant_id == self.tenant_id,
            table.c.environment_id == self.environment_id,
        )

    def _projection_scope(self, projection_name: str) -> Any:
        return and_(
            projection_positions.c.tenant_id == self.tenant_id,
            projection_positions.c.environment_id == self.environment_id,
            projection_positions.c.projection_name == projection_name,
        )

    def _identity(self, row: Any) -> Any:
        return and_(
            self._scope(outbox_events),
            outbox_events.c.workspace_id == row["workspace_id"],
            outbox_events.c.event_id == row["event_id"],
        )

    def _message_identity(self, message: OutboxMessage) -> Any:
        return and_(
            self._scope(outbox_events),
            outbox_events.c.workspace_id == message.workspace_id,
            outbox_events.c.event_id == message.event_id,
        )

    def _message(self, row: Any, *, delivery_attempts: int) -> OutboxMessage:
        payload = row["payload"]
        if not isinstance(payload, dict):
            raise OAKError("OAK-OUTBOX-CORRUPT", "outbox payload is not an object")
        return OutboxMessage(
            tenant_id=self.tenant_id,
            environment_id=self.environment_id,
            workspace_id=str(row["workspace_id"]),
            event_id=str(row["event_id"]),
            aggregate_id=str(row["aggregate_id"]),
            aggregate_sequence=int(row["aggregate_sequence"]),
            event_type=str(row["event_type"]),
            payload=payload,
            payload_digest=str(row["payload_digest"]),
            occurred_at=_format_time(row["occurred_at"]),
            delivery_attempts=delivery_attempts,
        )
