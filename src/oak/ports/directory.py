# SPDX-License-Identifier: Apache-2.0
"""Tenant-scoped read-only design-case directory port."""

from typing import Any, Protocol


class CaseDirectoryPort(Protocol):
    """List current design-case heads for one tenant/environment scope.

    The directory is a read-only query surface over authoritative case heads; it
    never authorizes state transitions and returns deterministically ordered rows.
    """

    def list_cases(self) -> tuple[dict[str, Any], ...]: ...
