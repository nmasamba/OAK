# SPDX-License-Identifier: Apache-2.0
"""The deterministic built-in policy engine.

This is the reference implementation of the pack rule semantics and the only
engine the offline path ever requires.
"""

from typing import Any

from oak.domain.extension_sdk import BUILTIN_POLICY_ENGINE_ID
from oak.domain.policy_rules import PackEvaluation, evaluate_pack_rules


class BuiltinPolicyEngine:
    """Evaluate pack rules through `oak.domain.policy_rules` directly."""

    @property
    def engine_id(self) -> str:
        return BUILTIN_POLICY_ENGINE_ID

    def evaluate(self, pack: dict[str, Any], subject: dict[str, Any]) -> PackEvaluation:
        return evaluate_pack_rules(list(pack["rules"]), subject)
