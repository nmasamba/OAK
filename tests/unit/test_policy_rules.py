# SPDX-License-Identifier: Apache-2.0
"""Deterministic bounded policy-rule semantics."""

from typing import Any

import pytest

from oak.domain.policy_rules import (
    MAXIMUM_CONDITION_DEPTH,
    UNKNOWN_REASON_CODE,
    evaluate_pack_rules,
    pack_effective_window,
)


def _rule(
    *,
    rule_id: str = "rule.test",
    outcome: str = "deny",
    reason_code: str = "POL-TEST",
    when: dict[str, Any],
    obligations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "description": "test rule",
        "outcome": outcome,
        "reason_code": reason_code,
        "when": when,
        "obligations": obligations or [],
    }


SUBJECT: dict[str, Any] = {
    "data": {"classification": "public", "records": 12},
    "tags": ["local", "no_runtime_egress"],
    "nested": [{"name": "alpha"}, {"name": "beta"}],
    "flag": True,
}


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ({"pointer": "/data/classification", "operator": "equals", "value": "public"}, True),
        ({"pointer": "/data/classification", "operator": "not_equals", "value": "internal"}, True),
        ({"pointer": "/data/classification", "operator": "in", "value": ["public", "open"]}, True),
        ({"pointer": "/data/classification", "operator": "not_in", "value": ["secret"]}, True),
        ({"pointer": "/data/records", "operator": "less_or_equal", "value": 12}, True),
        ({"pointer": "/data/records", "operator": "greater_or_equal", "value": 13}, False),
        ({"pointer": "/data/records", "operator": "exists"}, True),
        ({"pointer": "/data/missing", "operator": "absent"}, True),
        ({"pointer": "/tags", "operator": "contains", "value": "no_runtime_egress"}, True),
        ({"pointer": "/tags", "operator": "subset_of", "value": ["local"]}, False),
        (
            {
                "pointer": "/tags",
                "operator": "subset_of",
                "value": ["local", "no_runtime_egress", "extra"],
            },
            True,
        ),
        ({"pointer": "/nested/1/name", "operator": "equals", "value": "beta"}, True),
        ({"pointer": "/flag", "operator": "equals", "value": True}, True),
        ({"pointer": "/flag", "operator": "equals", "value": 1}, False),
    ],
)
def test_leaf_operators(when: dict[str, Any], expected: bool) -> None:
    result = evaluate_pack_rules([_rule(when=when)], SUBJECT)
    assert result.rule_results[0].matched is expected
    assert result.rule_results[0].unknown is False


@pytest.mark.parametrize(
    "when",
    [
        {"pointer": "/data/missing", "operator": "equals", "value": "public"},
        {"pointer": "/data/classification", "operator": "less_or_equal", "value": 5},
        {"pointer": "/data/classification", "operator": "in", "value": "public"},
        {"pointer": "/data/classification", "operator": "contains", "value": "public"},
        {"pointer": "/tags", "operator": "subset_of", "value": "local"},
        {"pointer": "/data/records", "operator": "equals"},
        {"pointer": "/data/records", "operator": "exists", "value": 12},
        {"pointer": "/flag", "operator": "less_or_equal", "value": 1},
    ],
)
def test_undecidable_leaves_fail_closed_to_unknown(when: dict[str, Any]) -> None:
    result = evaluate_pack_rules([_rule(when=when)], SUBJECT)
    assert result.outcome == "unknown"
    assert result.rule_results[0].unknown is True
    assert result.rule_results[0].matched is False
    assert UNKNOWN_REASON_CODE in result.reasons


def test_composite_conditions() -> None:
    when = {
        "all": [
            {"pointer": "/data/classification", "operator": "equals", "value": "public"},
            {
                "any": [
                    {"pointer": "/tags", "operator": "contains", "value": "cloud"},
                    {"pointer": "/tags", "operator": "contains", "value": "local"},
                ]
            },
            {"not": {"pointer": "/data/missing", "operator": "exists"}},
        ]
    }
    result = evaluate_pack_rules([_rule(when=when, outcome="allow")], SUBJECT)
    assert result.rule_results[0].matched is True
    assert result.outcome == "allow"


def test_all_short_circuits_false_over_unknown() -> None:
    when = {
        "all": [
            {"pointer": "/data/classification", "operator": "equals", "value": "internal"},
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
        ]
    }
    result = evaluate_pack_rules([_rule(when=when)], SUBJECT)
    assert result.rule_results[0].matched is False
    assert result.rule_results[0].unknown is False


def test_any_short_circuits_true_over_unknown() -> None:
    when = {
        "any": [
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
            {"pointer": "/data/classification", "operator": "equals", "value": "public"},
        ]
    }
    result = evaluate_pack_rules([_rule(when=when, outcome="allow")], SUBJECT)
    assert result.rule_results[0].matched is True


def test_unknown_inside_any_without_true_is_unknown() -> None:
    when = {
        "any": [
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
            {"pointer": "/data/classification", "operator": "equals", "value": "internal"},
        ]
    }
    result = evaluate_pack_rules([_rule(when=when)], SUBJECT)
    assert result.outcome == "unknown"


def test_depth_bound_fails_closed() -> None:
    when: dict[str, Any] = {"pointer": "/flag", "operator": "exists"}
    for _ in range(MAXIMUM_CONDITION_DEPTH + 1):
        when = {"not": when}
    result = evaluate_pack_rules([_rule(when=when)], SUBJECT)
    assert result.outcome == "unknown"


def test_aggregation_deny_beats_review_beats_allow() -> None:
    rules = [
        _rule(
            rule_id="rule.allow",
            outcome="allow",
            reason_code="POL-ALLOW",
            when={"pointer": "/flag", "operator": "exists"},
            obligations=["keep flag"],
        ),
        _rule(
            rule_id="rule.review",
            outcome="review_required",
            reason_code="POL-REVIEW",
            when={"pointer": "/flag", "operator": "exists"},
        ),
        _rule(
            rule_id="rule.deny",
            outcome="deny",
            reason_code="POL-DENY",
            when={"pointer": "/flag", "operator": "exists"},
        ),
    ]
    result = evaluate_pack_rules(rules, SUBJECT)
    assert result.outcome == "deny"
    assert result.reasons == ("POL-ALLOW", "POL-DENY", "POL-REVIEW")
    assert result.obligations == ("keep flag",)
    without_deny = evaluate_pack_rules(rules[:2], SUBJECT)
    assert without_deny.outcome == "review_required"
    allow_only = evaluate_pack_rules(rules[:1], SUBJECT)
    assert allow_only.outcome == "allow"


def test_no_matched_rule_is_unknown_not_allow() -> None:
    result = evaluate_pack_rules(
        [_rule(when={"pointer": "/data/missing", "operator": "exists"}, outcome="allow")],
        SUBJECT,
    )
    assert result.outcome == "unknown"


def test_any_unknown_rule_poisons_the_aggregate() -> None:
    rules = [
        _rule(
            rule_id="rule.allow",
            outcome="allow",
            reason_code="POL-ALLOW",
            when={"pointer": "/flag", "operator": "exists"},
        ),
        _rule(
            rule_id="rule.unknown",
            reason_code="POL-UNKNOWN",
            when={"pointer": "/data/missing", "operator": "equals", "value": 1},
        ),
    ]
    assert evaluate_pack_rules(rules, SUBJECT).outcome == "unknown"


def test_unmatched_rules_contribute_no_obligations_or_reasons() -> None:
    rules = [
        _rule(
            rule_id="rule.unmatched",
            reason_code="POL-UNMATCHED",
            when={"pointer": "/data/classification", "operator": "equals", "value": "internal"},
            obligations=["never applied"],
        ),
        _rule(
            rule_id="rule.matched",
            outcome="allow",
            reason_code="POL-MATCHED",
            when={"pointer": "/flag", "operator": "exists"},
        ),
    ]
    result = evaluate_pack_rules(rules, SUBJECT)
    assert result.reasons == ("POL-MATCHED",)
    assert result.obligations == ()


def test_escaped_pointer_tokens_resolve() -> None:
    subject = {"a/b": {"c~d": "value"}}
    result = evaluate_pack_rules(
        [_rule(when={"pointer": "/a~1b/c~0d", "operator": "equals", "value": "value"})],
        subject,
    )
    assert result.rule_results[0].matched is True


def _pack(
    status: str = "published", expires: str | None = "2027-08-01T00:00:00Z"
) -> dict[str, Any]:
    return {
        "status": status,
        "effective_from": "2026-08-01T00:00:00Z",
        "expires_at": expires,
    }


def test_effective_window() -> None:
    assert pack_effective_window(_pack(), at="2026-08-19T00:00:00Z") == (
        True,
        "OAK-POLICY-PACK-EFFECTIVE",
    )
    assert pack_effective_window(_pack(), at="2026-07-31T23:59:59Z") == (
        False,
        "OAK-POLICY-PACK-NOT-YET-EFFECTIVE",
    )
    assert pack_effective_window(_pack(), at="2027-08-01T00:00:00Z") == (
        False,
        "OAK-POLICY-PACK-EXPIRED",
    )
    assert pack_effective_window(_pack(expires=None), at="2030-01-01T00:00:00Z") == (
        True,
        "OAK-POLICY-PACK-EFFECTIVE",
    )
    assert pack_effective_window(_pack(status="draft"), at="2026-08-19T00:00:00Z") == (
        False,
        "OAK-POLICY-PACK-STATUS",
    )
