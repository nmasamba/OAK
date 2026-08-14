# SPDX-License-Identifier: Apache-2.0
"""Readiness port."""

from typing import Protocol


class ReadinessProbe(Protocol):
    """A dependency probe that exposes only a boolean to the application layer."""

    def is_ready(self) -> bool:
        """Return whether the dependency can serve its required behavior."""
        ...
