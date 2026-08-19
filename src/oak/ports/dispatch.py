# SPDX-License-Identifier: Apache-2.0
"""Outbound-only dispatch transport port between control plane and runner."""

from typing import Any, Protocol


class DispatchTransport(Protocol):
    """Deliver signed canonical documents to a runner it never connects into."""

    def deliver(
        self,
        envelope: dict[str, Any],
        attachments: dict[str, dict[str, Any]],
    ) -> None: ...

    def publish_revocation(self, notice: dict[str, Any]) -> None: ...

    def read_messages(self) -> tuple[dict[str, Any], ...]: ...

    def acknowledge(self, message_id: str) -> None: ...
