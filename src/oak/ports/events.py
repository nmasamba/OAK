# SPDX-License-Identifier: Apache-2.0
"""Transactional outbox and rebuildable projection ports."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    tenant_id: str
    environment_id: str
    workspace_id: str
    event_id: str
    aggregate_id: str
    aggregate_sequence: int
    event_type: str
    payload: dict[str, Any]
    payload_digest: str
    occurred_at: str
    delivery_attempts: int


@dataclass(frozen=True, slots=True)
class OutboxLag:
    pending_events: int
    oldest_pending_at: str | None
    latest_sequence: int
    indexed_through: int

    @property
    def sequence_lag(self) -> int:
        return max(0, self.latest_sequence - self.indexed_through)


class OutboxStore(Protocol):
    def claim(
        self,
        *,
        consumer_id: str,
        now: str,
        lease_expires_at: str,
        limit: int,
    ) -> tuple[OutboxMessage, ...]: ...

    def mark_delivered(
        self,
        message: OutboxMessage,
        *,
        consumer_id: str,
        delivered_at: str,
    ) -> None: ...

    def release(
        self,
        message: OutboxMessage,
        *,
        consumer_id: str,
        available_at: str,
        error_code: str,
    ) -> None: ...

    def record_consumed(
        self,
        message: OutboxMessage,
        *,
        projection_name: str,
        processed_at: str,
    ) -> bool: ...

    def lag(self, *, projection_name: str) -> OutboxLag: ...
