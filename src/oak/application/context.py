# SPDX-License-Identifier: Apache-2.0
"""Transport-neutral command context."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandContext:
    actor: str
    tenant_id: str
    idempotency_key: str
    expected_version: str | None
    correlation_id: str
    interface_origin: str
    occurred_at: str
