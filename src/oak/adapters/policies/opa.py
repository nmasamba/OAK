# SPDX-License-Identifier: Apache-2.0
"""Optional OPA policy engine behind the policy port.

The adapter deterministically translates a pack's declarative condition trees
into one generated Rego module with explicit tri-state semantics (true, false,
undecidable), evaluates it with the local allowlisted ``opa`` binary over the
canonical subject, and reassembles the engine-neutral
:class:`~oak.domain.policy_rules.PackEvaluation` through the shared domain
aggregation. Pack content reaches Rego only as JSON-encoded literals — never
as identifiers, file names, or argv — and the built-in engine remains the
required offline reference implementation.
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oak.domain import OAKError
from oak.domain.extension_sdk import OPA_POLICY_ENGINE_ID
from oak.domain.policy_rules import (
    MAXIMUM_CONDITION_DEPTH,
    PackEvaluation,
    RuleEvaluation,
    aggregate_evaluations,
)

ALLOWLISTED_EXECUTABLES = frozenset({"opa"})
MAXIMUM_OUTPUT_BYTES = 1_048_576
EVALUATION_TIMEOUT_SECONDS = 30
_QUERY = "data.oak.result"

_HELPERS = """package oak

import rego.v1

_oak_step(cur, key) := out if {
\tis_object(cur)
\tout := cur[key]
}

_oak_step(cur, key) := out if {
\tis_array(cur)
\tregex.match(`^[0-9]+$`, key)
\tindex := to_number(key)
\tindex < count(cur)
\tout := cur[index]
}

_oak_eq(left, right) if left == right
"""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandExecutor = Callable[[tuple[str, ...], bytes, int], CommandResult]


def default_executor(argv: tuple[str, ...], stdin: bytes, timeout_seconds: int) -> CommandResult:
    resolved = shutil.which(argv[0])
    if resolved is None:
        raise OAKError(
            "OAK-POLICY-ENGINE-UNAVAILABLE",
            "the opa binary is not installed; the built-in engine remains available",
        )
    completed = subprocess.run(
        [resolved, *argv[1:]],
        input=stdin,
        capture_output=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
        env={"PATH": os.defpath},
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout[:MAXIMUM_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        stderr=completed.stderr[:MAXIMUM_OUTPUT_BYTES].decode("utf-8", errors="replace"),
    )


class OpaPolicyEngine:
    """Evaluate pack conditions through a generated tri-state Rego module."""

    def __init__(self, executor: CommandExecutor = default_executor) -> None:
        self._executor = executor

    @property
    def engine_id(self) -> str:
        return OPA_POLICY_ENGINE_ID

    def evaluate(self, pack: dict[str, Any], subject: dict[str, Any]) -> PackEvaluation:
        rules = list(pack["rules"])
        module = render_rego_module(rules)
        verdicts = self._run_opa(module, subject, expected_rules=len(rules))
        results: list[RuleEvaluation] = []
        for index, rule in enumerate(rules):
            verdict = verdicts[index]
            definitely_true = verdict["t"] is True
            definitely_false = verdict["f"] is True
            unknown = not definitely_true and not definitely_false
            obligations = (
                tuple(str(item) for item in rule["obligations"]) if definitely_true else ()
            )
            results.append(
                RuleEvaluation(
                    rule_id=str(rule["id"]),
                    matched=definitely_true,
                    outcome="unknown" if unknown else str(rule["outcome"]),
                    reason_code=str(rule["reason_code"]),
                    obligations=obligations,
                    unknown=unknown,
                )
            )
        return aggregate_evaluations(results)

    def _run_opa(
        self, module: str, subject: dict[str, Any], *, expected_rules: int
    ) -> list[dict[str, Any]]:
        stdin = json.dumps(
            subject,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        directory = Path(tempfile.mkdtemp(prefix="oak-opa-"))
        directory.chmod(0o700)
        module_path = directory / "pack.rego"
        try:
            module_path.write_text(module, encoding="utf-8")
            argv = (
                "opa",
                "eval",
                "--format=json",
                "--stdin-input",
                "--data",
                str(module_path),
                _QUERY,
            )
            if argv[0] not in ALLOWLISTED_EXECUTABLES:  # pragma: no cover - fixed literal
                raise OAKError("OAK-POLICY-ENGINE-FAILED", "policy engine argv is not allowlisted")
            try:
                completed = self._executor(argv, stdin, EVALUATION_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise OAKError("OAK-POLICY-ENGINE-FAILED", "opa evaluation timed out") from error
        finally:
            try:
                module_path.unlink(missing_ok=True)
                directory.rmdir()
            except OSError:
                pass
        if completed.returncode != 0:
            raise OAKError("OAK-POLICY-ENGINE-FAILED", "opa evaluation failed")
        return _parse_verdicts(completed.stdout, expected_rules=expected_rules)


def _parse_verdicts(stdout: str, *, expected_rules: int) -> list[dict[str, Any]]:
    try:
        payload = json.loads(stdout)
        value = payload["result"][0]["expressions"][0]["value"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise OAKError(
            "OAK-POLICY-ENGINE-FAILED", "opa evaluation returned an unreadable result"
        ) from error
    verdicts: list[dict[str, Any]] = []
    for index in range(expected_rules):
        verdict = value.get(f"r{index}") if isinstance(value, dict) else None
        if not isinstance(verdict, dict) or "t" not in verdict or "f" not in verdict:
            raise OAKError("OAK-POLICY-ENGINE-FAILED", "opa evaluation omitted a rule verdict")
        verdicts.append(verdict)
    return verdicts


def render_rego_module(rules: list[dict[str, Any]]) -> str:
    """Deterministically render the tri-state Rego module for a pack's rules."""

    renderer = _RegoRenderer()
    for index, rule in enumerate(rules):
        renderer.add_rule(index, rule["when"])
    return renderer.render()


class _RegoRenderer:
    """Emit one `n<i>_t` / `n<i>_f` pair per condition node; neither = unknown."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._results: list[str] = []
        self._counter = 0

    def add_rule(self, index: int, condition: dict[str, Any]) -> None:
        node = self._node(condition, depth=0)
        self._results.append(f'result["r{index}"] := {{"t": n{node}_t, "f": n{node}_f}}')

    def render(self) -> str:
        return "\n".join([_HELPERS, *self._lines, "", *self._results, ""])

    def _fresh(self) -> int:
        self._counter += 1
        return self._counter

    def _constant(self, node: int, *, truth: bool | None) -> int:
        self._lines.append(f"n{node}_t := {'true' if truth is True else 'false'}")
        self._lines.append(f"n{node}_f := {'true' if truth is False else 'false'}")
        return node

    def _node(self, condition: dict[str, Any], *, depth: int) -> int:
        node = self._fresh()
        if depth > MAXIMUM_CONDITION_DEPTH:
            return self._constant(node, truth=None)
        if "all" in condition:
            if not condition["all"]:
                return self._constant(node, truth=None)
            children = [self._node(item, depth=depth + 1) for item in condition["all"]]
            joined = "; ".join(f"n{child}_t" for child in children)
            self._lines.append(f"default n{node}_t := false")
            self._lines.append(f"n{node}_t if {{ {joined} }}")
            self._lines.append(f"default n{node}_f := false")
            for child in children:
                self._lines.append(f"n{node}_f if {{ n{child}_f }}")
            return node
        if "any" in condition:
            if not condition["any"]:
                return self._constant(node, truth=None)
            children = [self._node(item, depth=depth + 1) for item in condition["any"]]
            self._lines.append(f"default n{node}_t := false")
            for child in children:
                self._lines.append(f"n{node}_t if {{ n{child}_t }}")
            joined = "; ".join(f"n{child}_f" for child in children)
            self._lines.append(f"default n{node}_f := false")
            self._lines.append(f"n{node}_f if {{ {joined} }}")
            return node
        if "not" in condition:
            child = self._node(condition["not"], depth=depth + 1)
            self._lines.append(f"n{node}_t := n{child}_f")
            self._lines.append(f"n{node}_f := n{child}_t")
            return node
        return self._leaf(node, condition)

    def _value_chain(self, node: int, pointer: str) -> None:
        tokens = [token.replace("~1", "/").replace("~0", "~") for token in pointer.split("/")[1:]]
        steps = ["step0 := input"]
        for position, token in enumerate(tokens):
            steps.append(f"step{position + 1} := _oak_step(step{position}, {json.dumps(token)})")
        body = "; ".join(steps)
        self._lines.append(f"n{node}_v := step{len(tokens)} if {{ {body} }}")

    def _leaf(self, node: int, condition: dict[str, Any]) -> int:
        operator = str(condition["operator"])
        has_value = "value" in condition
        raw = condition.get("value")
        value = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        self._value_chain(node, str(condition["pointer"]))
        self._lines.append(f"default n{node}_t := false")
        self._lines.append(f"default n{node}_f := false")
        if operator in {"exists", "absent"}:
            if has_value:
                return self._constant(self._fresh(), truth=None)
            defined_side = "t" if operator == "exists" else "f"
            undefined_side = "f" if operator == "exists" else "t"
            self._lines.append(f"n{node}_{defined_side} if {{ v := n{node}_v; v == v }}")
            self._lines.append(f"n{node}_{undefined_side} if {{ not n{node}_{defined_side} }}")
            return node
        if not has_value:
            return self._constant(self._fresh(), truth=None)
        if operator in {"equals", "not_equals"}:
            positive = f"v := n{node}_v; _oak_eq(v, {value})"
            negative = f"v := n{node}_v; not _oak_eq(v, {value})"
            first, second = (positive, negative) if operator == "equals" else (negative, positive)
            self._lines.append(f"n{node}_t if {{ {first} }}")
            self._lines.append(f"n{node}_f if {{ {second} }}")
            return node
        if operator in {"in", "not_in"}:
            if not isinstance(raw, list):
                return self._constant(self._fresh(), truth=None)
            member = f"v := n{node}_v; some c in {value}; _oak_eq(v, c)"
            non_member = f"v := n{node}_v; count([c | some c in {value}; _oak_eq(v, c)]) == 0"
            first, second = (member, non_member) if operator == "in" else (non_member, member)
            self._lines.append(f"n{node}_t if {{ {first} }}")
            self._lines.append(f"n{node}_f if {{ {second} }}")
            return node
        if operator in {"less_or_equal", "greater_or_equal"}:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                return self._constant(self._fresh(), truth=None)
            holds = "<=" if operator == "less_or_equal" else ">="
            fails = ">" if operator == "less_or_equal" else "<"
            guard = f"v := n{node}_v; is_number(v)"
            self._lines.append(f"n{node}_t if {{ {guard}; v {holds} {value} }}")
            self._lines.append(f"n{node}_f if {{ {guard}; v {fails} {value} }}")
            return node
        if operator == "contains":
            guard = f"v := n{node}_v; is_array(v)"
            self._lines.append(f"n{node}_t if {{ {guard}; some c in v; _oak_eq(c, {value}) }}")
            self._lines.append(
                f"n{node}_f if {{ {guard}; count([c | some c in v; _oak_eq(c, {value})]) == 0 }}"
            )
            return node
        if operator == "subset_of":
            if not isinstance(raw, list):
                return self._constant(self._fresh(), truth=None)
            guard = f"v := n{node}_v; is_array(v)"
            missing = f"[m | some m in v; count([c | some c in {value}; _oak_eq(m, c)]) == 0]"
            self._lines.append(f"n{node}_t if {{ {guard}; count({missing}) == 0 }}")
            self._lines.append(f"n{node}_f if {{ {guard}; count({missing}) > 0 }}")
            return node
        return self._constant(self._fresh(), truth=None)
