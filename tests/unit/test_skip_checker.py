# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-023 (RR-014): a CI job fails unless it skipped exactly what it is expected to."""

import json
from pathlib import Path

import pytest

from scripts import check_skips
from scripts.check_skips import compare, tally


def _ledger(*reasons: str) -> list[str]:
    return [
        json.dumps({"test": f"tests/x.py::t{index}", "reason": reason})
        for index, reason in enumerate(reasons)
    ]


def test_a_ledger_is_counted_by_reason() -> None:
    assert tally([*_ledger("no database", "no database", "no opa"), ""]) == {
        "no database": 2,
        "no opa": 1,
    }


def test_exactly_the_expected_skips_pass() -> None:
    assert compare({"no database": 2}, {"no database": 2}) == []


@pytest.mark.parametrize(
    ("actual", "problem"),
    [
        ({"no database": 3}, "3 skipped, 2 expected: no database"),
        ({"no database": 1}, "1 skipped, 2 expected: no database"),
        ({}, "0 skipped, 2 expected: no database"),
        ({"no database": 2, "no docker": 1}, "1 skipped, 0 expected: no docker"),
    ],
)
def test_a_skip_that_widens_narrows_or_appears_is_refused(
    actual: dict[str, int], problem: str
) -> None:
    assert compare(actual, {"no database": 2}) == [problem]


def test_the_script_refuses_an_unexpected_count_and_an_unknown_job(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    expectations = tmp_path / "expected-skips.json"
    expectations.write_text(json.dumps({"job": {"no database": 1}}), encoding="utf-8")
    monkeypatch.setattr(check_skips, "EXPECTATIONS", expectations)
    ledger = tmp_path / "skips.jsonl"
    ledger.write_text("\n".join(_ledger("no database")) + "\n", encoding="utf-8")

    assert check_skips.main([str(ledger), "job"]) == 0
    assert "skips as expected for job: 1" in capsys.readouterr().out

    ledger.write_text("\n".join(_ledger("no database", "no docker")) + "\n", encoding="utf-8")
    assert check_skips.main([str(ledger), "job"]) == 1
    assert "1 skipped, 0 expected: no docker" in capsys.readouterr().err

    assert check_skips.main([str(ledger), "another-job"]) == 1
    assert "no expectation for job 'another-job'" in capsys.readouterr().err


def test_a_missing_ledger_is_a_run_that_skipped_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expectations = tmp_path / "expected-skips.json"
    expectations.write_text(json.dumps({"job": {"no database": 1}}), encoding="utf-8")
    monkeypatch.setattr(check_skips, "EXPECTATIONS", expectations)

    assert check_skips.main([str(tmp_path / "absent.jsonl"), "job"]) == 1


def test_every_job_the_workflows_check_has_an_expectation() -> None:
    root = Path(__file__).resolve().parents[2]
    expectations = json.loads((root / "tests" / "expected-skips.json").read_text("utf-8"))
    workflows = "".join(
        (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for name in ("ci.yml", "release.yml")
    )
    named = {
        line.rsplit(" ", 1)[-1]
        for line in workflows.splitlines()
        if "scripts/check_skips.py" in line
    }
    assert named == set(expectations)
    for job, reasons in expectations.items():
        assert all(isinstance(count, int) and count > 0 for count in reasons.values()), job


def test_the_ledger_records_each_skip_and_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from tests import conftest

    reports = [
        SimpleNamespace(nodeid="tests/a.py::gated", longrepr=("a.py", 3, "Skipped: a gate")),
        SimpleNamespace(nodeid="tests/b.py::inside", longrepr=("b.py", 9, "another gate")),
    ]
    reporter = SimpleNamespace(stats={"skipped": reports}, write_line=lambda *a, **k: None)
    ledger = tmp_path / "skips.jsonl"
    monkeypatch.setenv("OAK_SKIP_LEDGER", str(ledger))

    conftest.pytest_terminal_summary(reporter)  # type: ignore[arg-type]
    conftest.pytest_terminal_summary(reporter)  # type: ignore[arg-type]

    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert lines == 2 * [
        {"test": "tests/a.py::gated", "reason": "a gate"},
        {"test": "tests/b.py::inside", "reason": "another gate"},
    ]
