# SPDX-License-Identifier: Apache-2.0
"""Bounded target-profile input contract."""

from pathlib import Path
from typing import Any, Protocol


class TargetProfilePort(Protocol):
    def load(self, path: Path) -> dict[str, Any]: ...

    def validate_document(self, document: dict[str, Any]) -> dict[str, Any]: ...
