# SPDX-License-Identifier: Apache-2.0
"""Provider-neutral optional interpretation proposal port."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProposalLimits:
    maximum_input_bytes: int = 262_144
    maximum_output_bytes: int = 131_072
    timeout_seconds: float = 30.0


class ModelInterpreterPort(Protocol):
    def propose(
        self,
        source_record: dict[str, Any],
        source_content: bytes,
        limits: ProposalLimits,
    ) -> dict[str, Any]: ...
