# SPDX-License-Identifier: Apache-2.0
"""Deterministic optional model-proposal adapter for contract tests."""

import copy
from typing import Any

from oak.domain import OAKError
from oak.ports.interpreter import ProposalLimits


class FakeModelInterpreter:
    def __init__(
        self,
        proposal: dict[str, Any] | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self._proposal = proposal
        self._unavailable = unavailable

    def propose(
        self,
        source_record: dict[str, Any],
        source_content: bytes,
        limits: ProposalLimits,
    ) -> dict[str, Any]:
        if len(source_content) > limits.maximum_input_bytes:
            raise OAKError("OAK-INTERPRETER-INPUT-LIMIT", "proposal input exceeds its limit")
        if self._unavailable:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE",
                "optional interpretation provider is unavailable",
                retriable=True,
            )
        if self._proposal is None:
            raise OAKError("OAK-INTERPRETER-MALFORMED", "optional interpreter returned no proposal")
        return copy.deepcopy(self._proposal)
