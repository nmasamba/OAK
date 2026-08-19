# SPDX-License-Identifier: Apache-2.0
"""Hermetic OPA adapter behavior: argv, module generation, failure mapping."""

from typing import Any

import pytest

from oak.adapters.policies.opa import (
    CommandResult,
    OpaPolicyEngine,
    render_rego_module,
)
from oak.domain import OAKError

RULES: list[dict[str, Any]] = [
    {
        "id": "rule.example",
        "description": "example",
        "outcome": "allow",
        "reason_code": "POL-EXAMPLE",
        "when": {"pointer": "/a/b", "operator": "equals", "value": "x"},
        "obligations": ["keep"],
    }
]
PACK = {"rules": RULES}


def _canned(value: dict[str, Any]) -> CommandResult:
    import json

    return CommandResult(
        returncode=0,
        stdout=json.dumps({"result": [{"expressions": [{"value": value}]}]}),
        stderr="",
    )


def test_argv_is_fixed_and_input_travels_via_stdin() -> None:
    captured: dict[str, Any] = {}

    def executor(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        captured["argv"] = argv
        captured["stdin"] = stdin
        captured["timeout"] = timeout
        return _canned({"r0": {"t": True, "f": False}})

    engine = OpaPolicyEngine(executor)
    evaluation = engine.evaluate(PACK, {"a": {"b": "x"}})
    argv = captured["argv"]
    assert argv[0] == "opa"
    assert argv[1:5] == ("eval", "--format=json", "--stdin-input", "--data")
    assert argv[5].endswith("pack.rego")
    assert argv[6] == "data.oak.result"
    assert b'"a":{"b":"x"}' in captured["stdin"]
    assert captured["timeout"] == 30
    assert evaluation.outcome == "allow"
    assert evaluation.rule_results[0].matched is True
    assert evaluation.obligations == ("keep",)


def test_module_generation_is_deterministic_and_literal_only() -> None:
    first = render_rego_module(RULES)
    second = render_rego_module(RULES)
    assert first == second
    assert "package oak" in first
    assert "import rego.v1" in first
    assert '"b"' in first
    for line in first.splitlines():
        assert not line.strip().startswith("input.")


def test_missing_binary_maps_to_unavailable() -> None:
    def executor(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        raise OAKError(
            "OAK-POLICY-ENGINE-UNAVAILABLE",
            "the opa binary is not installed; the built-in engine remains available",
        )

    with pytest.raises(OAKError) as denial:
        OpaPolicyEngine(executor).evaluate(PACK, {})
    assert denial.value.code == "OAK-POLICY-ENGINE-UNAVAILABLE"


def test_nonzero_exit_and_garbage_output_fail_closed() -> None:
    def failing(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        return CommandResult(returncode=2, stdout="", stderr="boom")

    with pytest.raises(OAKError) as failure:
        OpaPolicyEngine(failing).evaluate(PACK, {})
    assert failure.value.code == "OAK-POLICY-ENGINE-FAILED"

    def garbage(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        return CommandResult(returncode=0, stdout="not json", stderr="")

    with pytest.raises(OAKError) as unreadable:
        OpaPolicyEngine(garbage).evaluate(PACK, {})
    assert unreadable.value.code == "OAK-POLICY-ENGINE-FAILED"

    def missing_rule(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        return _canned({})

    with pytest.raises(OAKError) as omitted:
        OpaPolicyEngine(missing_rule).evaluate(PACK, {})
    assert omitted.value.code == "OAK-POLICY-ENGINE-FAILED"


def test_neither_true_nor_false_is_unknown_and_poisons_outcome() -> None:
    def executor(argv: tuple[str, ...], stdin: bytes, timeout: int) -> CommandResult:
        return _canned({"r0": {"t": False, "f": False}})

    evaluation = OpaPolicyEngine(executor).evaluate(PACK, {})
    assert evaluation.outcome == "unknown"
    assert evaluation.rule_results[0].unknown is True
    assert evaluation.reasons == ("POL-CONDITION-UNKNOWN",)
