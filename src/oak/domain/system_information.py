# SPDX-License-Identifier: Apache-2.0
"""Immutable system-information query results."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SystemInformation:
    """Safe build information shared by all interfaces."""

    name: str
    version: str
    commit: str
    schema_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Readiness:
    """Coarse readiness without dependency or secret details."""

    status: Literal["ready", "not_ready"]
