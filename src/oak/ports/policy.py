# SPDX-License-Identifier: Apache-2.0
"""Policy evaluation and pack-source ports.

Engines are interchangeable evaluators of the shared rule semantics: the
canonical decision document is assembled by the application layer from the
engine-neutral :class:`~oak.domain.policy_rules.PackEvaluation`, so swapping
engines can never change canonical content.
"""

from typing import Any, Protocol

from oak.domain.policy_rules import PackEvaluation


class PolicyEnginePort(Protocol):
    """Evaluate one schema-valid policy pack over one canonical subject."""

    @property
    def engine_id(self) -> str: ...

    def evaluate(self, pack: dict[str, Any], subject: dict[str, Any]) -> PackEvaluation: ...


class PolicyPackStorePort(Protocol):
    """Bounded read-only source of schema-valid policy packs."""

    def list_packs(self) -> tuple[dict[str, Any], ...]: ...

    def load(self, pack_id: str) -> dict[str, Any]: ...
