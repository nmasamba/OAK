# SPDX-License-Identifier: Apache-2.0
"""Hermetic OPA adapter behavior: argv, module generation, failure mapping."""

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.policies.opa import (
    CommandResult,
    OpaPolicyEngine,
    opa_executor,
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

    def executor(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        captured["argv"] = argv
        captured["stdin"] = stdin
        captured["timeout"] = timeout
        captured["directory"] = working_directory
        captured["mode"] = stat.S_IMODE(working_directory.stat().st_mode)
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
    # The child starts in the evaluation's own private directory, which holds the module
    # and is removed afterwards (RR-027).
    assert Path(argv[5]).parent == captured["directory"]
    assert captured["mode"] == 0o700
    assert not captured["directory"].exists()
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
    def executor(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        raise OAKError(
            "OAK-POLICY-ENGINE-UNAVAILABLE",
            "the opa binary is not installed; the built-in engine remains available",
        )

    with pytest.raises(OAKError) as denial:
        OpaPolicyEngine(executor).evaluate(PACK, {})
    assert denial.value.code == "OAK-POLICY-ENGINE-UNAVAILABLE"


def test_nonzero_exit_and_garbage_output_fail_closed() -> None:
    def failing(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        return CommandResult(returncode=2, stdout="", stderr="boom")

    with pytest.raises(OAKError) as failure:
        OpaPolicyEngine(failing).evaluate(PACK, {})
    assert failure.value.code == "OAK-POLICY-ENGINE-FAILED"

    def garbage(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        return CommandResult(returncode=0, stdout="not json", stderr="")

    with pytest.raises(OAKError) as unreadable:
        OpaPolicyEngine(garbage).evaluate(PACK, {})
    assert unreadable.value.code == "OAK-POLICY-ENGINE-FAILED"

    def missing_rule(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        return _canned({})

    with pytest.raises(OAKError) as omitted:
        OpaPolicyEngine(missing_rule).evaluate(PACK, {})
    assert omitted.value.code == "OAK-POLICY-ENGINE-FAILED"


def test_neither_true_nor_false_is_unknown_and_poisons_outcome() -> None:
    def executor(
        argv: tuple[str, ...], stdin: bytes, timeout: int, working_directory: Path
    ) -> CommandResult:
        return _canned({"r0": {"t": False, "f": False}})

    evaluation = OpaPolicyEngine(executor).evaluate(PACK, {})
    assert evaluation.outcome == "unknown"
    assert evaluation.rule_results[0].unknown is True
    assert evaluation.reasons == ("POL-CONDITION-UNKNOWN",)


AGREES = '{"result":[{"expressions":[{"value":{"r0":{"t":true,"f":false}}}]}]}'
DISAGREES = '{"result":[{"expressions":[{"value":{"r0":{"t":false,"f":true}}}]}]}'


def _fake_opa(
    directory: Path, version: str, *, answer: str = AGREES, log: Path | None = None
) -> Path:
    """A stand-in `opa`: `version` prints a version line, anything else prints `answer`."""

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opa"
    record = f'echo "$(pwd) $1" >> "{log}"\n' if log is not None else ""
    path.write_text(
        "#!/bin/sh\n"
        + record
        + f'if [ "$1" = version ]; then echo "Version: {version}"; exit 0; fi\n'
        + "cat >/dev/null\n"
        + f"printf '%s' '{answer}'\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_opa_is_resolved_once_on_absolute_path_entries_and_runs_in_a_private_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OAK-V1-010 (RR-002, RR-027)."""

    log = tmp_path / "calls.log"
    _fake_opa(tmp_path / "bin", "1.19.1", answer=DISAGREES)
    trusted = _fake_opa(tmp_path / "trusted", "1.19.1", log=log)
    monkeypatch.chdir(tmp_path)
    # `bin` is relative, so it is skipped; the absolute entry after it is used.
    monkeypatch.setenv("PATH", os.pathsep.join(("bin", str(trusted.parent))))
    engine = OpaPolicyEngine()
    # Built once: a later PATH, reaching a binary that disagrees, changes nothing.
    _fake_opa(tmp_path / "later", "1.19.1", answer=DISAGREES)
    monkeypatch.setenv("PATH", str(tmp_path / "later"))

    evaluation = engine.evaluate(PACK, {"a": {"b": "x"}})

    assert evaluation.outcome == "allow"
    calls = [line.split(" ") for line in log.read_text(encoding="utf-8").splitlines()]
    assert [argument for _directory, argument in calls] == ["version", "eval"]
    for directory, _argument in calls:
        assert Path(directory).name.startswith("oak-opa-")
        assert not Path(directory).exists(), "the private directory is removed afterwards"


@pytest.mark.parametrize("version", ["0.70.0", "0.59.0"])
def test_an_opa_older_than_one_is_refused_before_anything_is_evaluated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    log = tmp_path / "calls.log"
    _fake_opa(tmp_path / "old", version, log=log)
    monkeypatch.setenv("PATH", str(tmp_path / "old"))

    with pytest.raises(OAKError) as refused:
        OpaPolicyEngine()
    assert refused.value.code == "OAK-POLICY-ENGINE-UNAVAILABLE"
    assert [line.split(" ")[1] for line in log.read_text(encoding="utf-8").splitlines()] == [
        "version"
    ]


def test_an_opa_that_reports_no_version_or_none_at_all_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_opa(tmp_path / "garbled", "unknown")
    for path in (tmp_path / "garbled", tmp_path / "empty"):
        monkeypatch.setenv("PATH", str(path))
        with pytest.raises(OAKError) as refused:
            opa_executor()
        assert refused.value.code == "OAK-POLICY-ENGINE-UNAVAILABLE"


def test_the_minimum_version_itself_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_opa(tmp_path / "floor", "1.0.0")
    monkeypatch.setenv("PATH", str(tmp_path / "floor"))

    assert OpaPolicyEngine().evaluate(PACK, {"a": {"b": "x"}}).outcome == "allow"
