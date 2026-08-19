# SPDX-License-Identifier: Apache-2.0
"""Deterministic bounded policy-rule semantics shared by every policy engine.

The rule language is data, never code: a rule matches when its condition holds
over a canonical JSON subject, and the pack decision aggregates matched rules
as deny > review_required > allow. Anything the language cannot decide —
an unresolved pointer, an operator/value type mismatch — fails closed into
`unknown`, which can never satisfy an automated approval.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from oak.domain.errors import OAKError

RULE_OUTCOMES = ("allow", "deny", "review_required")
DECISION_OUTCOMES = ("allow", "deny", "review_required", "unknown")
_OUTCOME_PRECEDENCE = {"deny": 0, "review_required": 1, "allow": 2}
_VALUE_OPERATORS = frozenset(
    {"equals", "not_equals", "in", "not_in", "less_or_equal", "greater_or_equal"}
)
_PRESENCE_OPERATORS = frozenset({"exists", "absent"})
_COLLECTION_OPERATORS = frozenset({"contains", "subset_of"})
MAXIMUM_CONDITION_DEPTH = 12
UNKNOWN_REASON_CODE = "POL-CONDITION-UNKNOWN"


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """One rule's contribution to a pack decision, in pack order."""

    rule_id: str
    matched: bool
    outcome: str
    reason_code: str
    obligations: tuple[str, ...]
    unknown: bool


@dataclass(frozen=True, slots=True)
class PackEvaluation:
    """The canonical aggregate of every rule evaluation for one subject."""

    outcome: str
    rule_results: tuple[RuleEvaluation, ...]
    reasons: tuple[str, ...]
    obligations: tuple[str, ...]


def evaluate_pack_rules(rules: list[dict[str, Any]], subject: dict[str, Any]) -> PackEvaluation:
    """Evaluate every rule over the subject and aggregate fail-closed."""

    results: list[RuleEvaluation] = []
    for rule in rules:
        matched = _evaluate_condition(rule["when"], subject, depth=0)
        if matched is None:
            results.append(
                RuleEvaluation(
                    rule_id=str(rule["id"]),
                    matched=False,
                    outcome="unknown",
                    reason_code=str(rule["reason_code"]),
                    obligations=(),
                    unknown=True,
                )
            )
            continue
        obligations = tuple(str(item) for item in rule["obligations"]) if matched else ()
        results.append(
            RuleEvaluation(
                rule_id=str(rule["id"]),
                matched=matched,
                outcome=str(rule["outcome"]),
                reason_code=str(rule["reason_code"]),
                obligations=obligations,
                unknown=False,
            )
        )
    return PackEvaluation(
        outcome=_aggregate_outcome(results),
        rule_results=tuple(results),
        reasons=_aggregate_reasons(results),
        obligations=tuple(sorted({item for result in results for item in result.obligations})),
    )


def pack_effective_window(pack: dict[str, Any], *, at: str) -> tuple[bool, str]:
    """Return whether the pack is effective at the given instant with a reason code."""

    moment = _timestamp(at)
    if pack["status"] != "published":
        return False, "OAK-POLICY-PACK-STATUS"
    if moment < _timestamp(str(pack["effective_from"])):
        return False, "OAK-POLICY-PACK-NOT-YET-EFFECTIVE"
    expires_at = pack["expires_at"]
    if expires_at is not None and moment >= _timestamp(str(expires_at)):
        return False, "OAK-POLICY-PACK-EXPIRED"
    return True, "OAK-POLICY-PACK-EFFECTIVE"


def _aggregate_outcome(results: list[RuleEvaluation]) -> str:
    if any(result.unknown for result in results):
        return "unknown"
    matched = [result for result in results if result.matched]
    if not matched:
        return "unknown"
    return min(matched, key=lambda result: _OUTCOME_PRECEDENCE[result.outcome]).outcome


def _aggregate_reasons(results: list[RuleEvaluation]) -> tuple[str, ...]:
    reasons = {result.reason_code for result in results if result.matched}
    reasons.update(UNKNOWN_REASON_CODE for result in results if result.unknown)
    return tuple(sorted(reasons))


def _evaluate_condition(
    condition: dict[str, Any], subject: dict[str, Any], *, depth: int
) -> bool | None:
    """Tri-state evaluation: True, False, or None when undecidable."""

    if depth > MAXIMUM_CONDITION_DEPTH:
        return None
    if "all" in condition:
        return _combine(
            [_evaluate_condition(item, subject, depth=depth + 1) for item in condition["all"]],
            require_all=True,
        )
    if "any" in condition:
        return _combine(
            [_evaluate_condition(item, subject, depth=depth + 1) for item in condition["any"]],
            require_all=False,
        )
    if "not" in condition:
        inner = _evaluate_condition(condition["not"], subject, depth=depth + 1)
        return None if inner is None else not inner
    return _evaluate_leaf(condition, subject)


def _combine(values: list[bool | None], *, require_all: bool) -> bool | None:
    if require_all:
        if any(value is False for value in values):
            return False
        if any(value is None for value in values):
            return None
        return True
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


def _evaluate_leaf(condition: dict[str, Any], subject: dict[str, Any]) -> bool | None:
    operator = str(condition["operator"])
    resolved, found = _resolve_pointer(subject, str(condition["pointer"]))
    if operator in _PRESENCE_OPERATORS:
        if "value" in condition:
            return None
        return found if operator == "exists" else not found
    if "value" not in condition:
        return None
    value = condition["value"]
    if not found:
        return None
    if operator in _VALUE_OPERATORS:
        return _evaluate_value_operator(operator, resolved, value)
    if operator in _COLLECTION_OPERATORS:
        return _evaluate_collection_operator(operator, resolved, value)
    return None


def _evaluate_value_operator(operator: str, resolved: Any, value: Any) -> bool | None:
    if operator == "equals":
        return _json_equal(resolved, value)
    if operator == "not_equals":
        return not _json_equal(resolved, value)
    if operator == "in":
        if not isinstance(value, list):
            return None
        return any(_json_equal(resolved, item) for item in value)
    if operator == "not_in":
        if not isinstance(value, list):
            return None
        return not any(_json_equal(resolved, item) for item in value)
    if not _comparable_numbers(resolved, value):
        return None
    if operator == "less_or_equal":
        return bool(resolved <= value)
    return bool(resolved >= value)


def _evaluate_collection_operator(operator: str, resolved: Any, value: Any) -> bool | None:
    if not isinstance(resolved, list):
        return None
    if operator == "contains":
        return any(_json_equal(item, value) for item in resolved)
    if not isinstance(value, list):
        return None
    return all(any(_json_equal(item, member) for member in resolved) for item in value)


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) is not isinstance(right, bool):
        return False
    result = left == right
    return bool(result)


def _comparable_numbers(left: Any, right: Any) -> bool:
    return (
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and not isinstance(left, bool)
        and not isinstance(right, bool)
    )


def _resolve_pointer(subject: dict[str, Any], pointer: str) -> tuple[Any, bool]:
    current: Any = subject
    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if key not in current:
                return None, False
            current = current[key]
        elif isinstance(current, list):
            if not key.isdigit() or int(key) >= len(current):
                return None, False
            current = current[int(key)]
        else:
            return None, False
    return current, True


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OAKError("OAK-POLICY-TIME", "policy timestamp is invalid") from error
