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

    def revocation_state(
        self,
    ) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], ...]]:
        """Return the published (manifest, notices) so a successor can be built."""
        ...

    def publish_revocation(self, notice: dict[str, Any] | None, manifest: dict[str, Any]) -> None:
        """Write the notice (when given) and the signed manifest covering the set."""
        ...

    def read_messages(self) -> tuple[dict[str, Any], ...]: ...

    def acknowledge(self, message_id: str) -> None: ...
