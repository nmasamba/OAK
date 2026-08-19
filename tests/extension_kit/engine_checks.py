# SPDX-License-Identifier: Apache-2.0
"""Policy-engine contract checks: determinism, reference parity, fail-closed."""

from typing import Any

from oak.adapters.policies import BuiltinPolicyEngine
from oak.ports.policy import PolicyEnginePort

UNDECIDABLE_SUBJECT: dict[str, Any] = {"nothing": {"resolves": True}}
UNDECIDABLE_PACK: dict[str, Any] = {
    "rules": [
        {
            "id": "rule.kit-undecidable",
            "description": "kit fixture over an unresolvable pointer",
            "outcome": "allow",
            "reason_code": "POL-KIT-UNDECIDABLE",
            "when": {"pointer": "/absent/pointer", "operator": "equals", "value": 1},
            "obligations": [],
        }
    ]
}


def check_engine_determinism(
    engine: PolicyEnginePort, pack: dict[str, Any], subjects: list[dict[str, Any]]
) -> None:
    """The same pack and subject must evaluate identically on repeat."""

    for subject in subjects:
        first = engine.evaluate(pack, subject)
        second = engine.evaluate(pack, subject)
        assert first == second, (
            f"engine {engine.engine_id} is nondeterministic for subject {subject!r}"
        )


def check_engine_matches_reference(
    engine: PolicyEnginePort, pack: dict[str, Any], subjects: list[dict[str, Any]]
) -> None:
    """Every engine must reproduce the built-in reference evaluation exactly."""

    reference = BuiltinPolicyEngine()
    for subject in subjects:
        expected = reference.evaluate(pack, subject)
        actual = engine.evaluate(pack, subject)
        assert actual == expected, (
            f"engine {engine.engine_id} diverged from the built-in reference for "
            f"subject {subject!r}: {actual} != {expected}"
        )


def check_engine_fails_closed_on_unknown(engine: PolicyEnginePort) -> None:
    """An undecidable condition can never produce an automated allow."""

    evaluation = engine.evaluate(UNDECIDABLE_PACK, UNDECIDABLE_SUBJECT)
    assert evaluation.outcome == "unknown", (
        f"engine {engine.engine_id} produced {evaluation.outcome} for an "
        "undecidable condition; unknown must never satisfy a gate"
    )
    assert evaluation.rule_results[0].unknown is True
