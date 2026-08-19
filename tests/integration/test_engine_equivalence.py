# SPDX-License-Identifier: Apache-2.0
"""Builtin and OPA engines must produce identical canonical evaluations."""

import shutil
from typing import Any

import pytest
import yaml

from oak.adapters.policies import BuiltinPolicyEngine, LocalPolicyPackStore
from oak.adapters.policies.opa import OpaPolicyEngine
from oak.contracts import SchemaRegistry
from tests.runner_support import ROOT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("opa") is None,
        reason="the optional opa binary is not installed; the built-in engine is authoritative",
    ),
]

SUBJECT: dict[str, Any] = {
    "data": {"classification": "public", "records": 12},
    "tags": ["local", "no_runtime_egress"],
    "nested": [{"name": "alpha"}, {"name": "beta"}],
    "flag": True,
    "none_value": None,
    "false_value": False,
}

LEAF_CONDITIONS: list[dict[str, Any]] = [
    {"pointer": "/data/classification", "operator": "equals", "value": "public"},
    {"pointer": "/data/classification", "operator": "equals", "value": "internal"},
    {"pointer": "/data/classification", "operator": "not_equals", "value": "internal"},
    {"pointer": "/data/classification", "operator": "in", "value": ["public", "open"]},
    {"pointer": "/data/classification", "operator": "in", "value": ["secret"]},
    {"pointer": "/data/classification", "operator": "not_in", "value": ["secret"]},
    {"pointer": "/data/records", "operator": "less_or_equal", "value": 12},
    {"pointer": "/data/records", "operator": "less_or_equal", "value": 11},
    {"pointer": "/data/records", "operator": "greater_or_equal", "value": 13},
    {"pointer": "/data/records", "operator": "greater_or_equal", "value": 12.0},
    {"pointer": "/data/records", "operator": "exists"},
    {"pointer": "/data/missing", "operator": "exists"},
    {"pointer": "/data/missing", "operator": "absent"},
    {"pointer": "/none_value", "operator": "exists"},
    {"pointer": "/none_value", "operator": "equals", "value": None},
    {"pointer": "/false_value", "operator": "equals", "value": False},
    {"pointer": "/false_value", "operator": "equals", "value": 0},
    {"pointer": "/flag", "operator": "equals", "value": True},
    {"pointer": "/flag", "operator": "equals", "value": 1},
    {"pointer": "/flag", "operator": "less_or_equal", "value": 1},
    {"pointer": "/tags", "operator": "contains", "value": "no_runtime_egress"},
    {"pointer": "/tags", "operator": "contains", "value": "cloud"},
    {"pointer": "/tags", "operator": "subset_of", "value": ["local"]},
    {
        "pointer": "/tags",
        "operator": "subset_of",
        "value": ["local", "no_runtime_egress", "extra"],
    },
    {"pointer": "/tags", "operator": "subset_of", "value": []},
    {"pointer": "/nested/1/name", "operator": "equals", "value": "beta"},
    {"pointer": "/nested/2/name", "operator": "equals", "value": "gamma"},
    {"pointer": "/nested/01/name", "operator": "equals", "value": "beta"},
    {"pointer": "/data", "operator": "contains", "value": "public"},
    {"pointer": "/data/classification", "operator": "less_or_equal", "value": 5},
    {"pointer": "/data/classification", "operator": "in", "value": "not-a-list"},
    {"pointer": "/tags", "operator": "subset_of", "value": "not-a-list"},
    {"pointer": "/data/records", "operator": "equals"},
    {"pointer": "/data/records", "operator": "exists", "value": 12},
]

COMPOSITE_CONDITIONS: list[dict[str, Any]] = [
    {
        "all": [
            {"pointer": "/data/classification", "operator": "equals", "value": "public"},
            {"pointer": "/tags", "operator": "contains", "value": "local"},
        ]
    },
    {
        "all": [
            {"pointer": "/data/classification", "operator": "equals", "value": "internal"},
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
        ]
    },
    {
        "any": [
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
            {"pointer": "/data/classification", "operator": "equals", "value": "public"},
        ]
    },
    {
        "any": [
            {"pointer": "/data/missing", "operator": "equals", "value": "x"},
            {"pointer": "/data/classification", "operator": "equals", "value": "internal"},
        ]
    },
    {"not": {"pointer": "/data/missing", "operator": "exists"}},
    {"not": {"pointer": "/data/missing", "operator": "equals", "value": "x"}},
    {
        "all": [
            {
                "any": [
                    {"pointer": "/tags", "operator": "contains", "value": "cloud"},
                    {"not": {"pointer": "/flag", "operator": "equals", "value": False}},
                ]
            },
            {"pointer": "/data/records", "operator": "greater_or_equal", "value": 1},
        ]
    },
]


def _pack_for(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = ("allow", "deny", "review_required")
    return {
        "rules": [
            {
                "id": f"rule.case-{index:02d}",
                "description": "equivalence case",
                "outcome": outcomes[index % 3],
                "reason_code": f"POL-CASE-{index:02d}",
                "when": condition,
                "obligations": [f"obligation {index}"],
            }
            for index, condition in enumerate(conditions)
        ]
    }


def test_operator_corpus_evaluates_identically() -> None:
    pack = _pack_for(LEAF_CONDITIONS)
    builtin = BuiltinPolicyEngine().evaluate(pack, SUBJECT)
    opa = OpaPolicyEngine().evaluate(pack, SUBJECT)
    assert builtin == opa


def test_composite_corpus_evaluates_identically() -> None:
    pack = _pack_for(COMPOSITE_CONDITIONS)
    builtin = BuiltinPolicyEngine().evaluate(pack, SUBJECT)
    opa = OpaPolicyEngine().evaluate(pack, SUBJECT)
    assert builtin == opa


def test_escaped_pointer_tokens_evaluate_identically() -> None:
    pack = _pack_for([{"pointer": "/a~1b/c~0d", "operator": "equals", "value": "value"}])
    subject = {"a/b": {"c~d": "value"}}
    assert BuiltinPolicyEngine().evaluate(pack, subject) == OpaPolicyEngine().evaluate(
        pack, subject
    )


@pytest.mark.parametrize(
    "pack_path",
    [
        ROOT / "policy-packs" / "community-baseline.yaml",
        ROOT / "examples" / "example-policy-pack.yaml",
    ],
    ids=["bundled", "example"],
)
def test_shipped_pack_fixtures_evaluate_identically(pack_path: Any) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    store = LocalPolicyPackStore((pack_path.parent,), registry)
    pack = yaml.safe_load(pack_path.read_text())
    registry.validate("policy-pack.schema.json", pack)
    builtin_engine = BuiltinPolicyEngine()
    opa_engine = OpaPolicyEngine()
    for test in pack["tests"]:
        subject = dict(test["subject"])
        builtin = builtin_engine.evaluate(pack, subject)
        opa = opa_engine.evaluate(pack, subject)
        assert builtin == opa, test["name"]
        assert builtin.outcome == test["expected_outcome"], test["name"]
    del store
