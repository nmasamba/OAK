# SPDX-License-Identifier: Apache-2.0
"""Untrusted brief intake port."""

from pathlib import Path
from typing import Protocol

from oak.domain.intake import IngestedBrief


class BriefIntakePort(Protocol):
    def read(self, path: Path) -> IngestedBrief: ...

    def read_content(self, *, original_name: str, content: bytes) -> IngestedBrief: ...
