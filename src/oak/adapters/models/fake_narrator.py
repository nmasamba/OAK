# SPDX-License-Identifier: Apache-2.0
"""Deterministic report-narrator adapter for tests: a fixed answer, or an outage."""

import copy
from typing import Any

from oak.domain import OAKError
from oak.ports.interpreter import ProposalLimits

FAKE_MODEL = {
    "family": "huggingface",
    "model_id": "example-org/example-model",
    "provider_route": "example-route",
    "prompt_digest": "sha256:" + "1" * 64,
    "response_digest": "sha256:" + "2" * 64,
    "usage": {"input_tokens": 1000, "output_tokens": 100},
    "attempts": 1,
    "dropped_notes": 0,
}


class FakeReportNarrator:
    def __init__(
        self, notes: list[dict[str, Any]] | None = None, *, unavailable: bool = False
    ) -> None:
        self._notes = notes
        self._unavailable = unavailable
        self.calls: list[dict[str, Any]] = []

    def propose(self, facts: dict[str, Any], limits: ProposalLimits) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(facts))
        if self._unavailable:
            raise OAKError(
                "OAK-NARRATIVE-UNAVAILABLE", "the provider did not answer", retriable=True
            )
        return {
            "notes": copy.deepcopy(self._notes or []),
            "extensions": {"oak.community/model": copy.deepcopy(FAKE_MODEL)},
        }
