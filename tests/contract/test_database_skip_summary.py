# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-018: a run that skips the PostgreSQL-gated tests says so.

Those tests skip unless OAK_TEST_DATABASE_URL is set, and a skip looks exactly like a pass
in pytest's summary line. CI and the release workflow set the variable; a local run ends
by counting what it skipped, so a sprint's closing gate cannot miss them unnoticed.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from tests.conftest import DATABASE_SKIP_REASON, pytest_terminal_summary

ROOT = Path(__file__).resolve().parents[2]


def _summary(skipped: list[SimpleNamespace]) -> list[str]:
    lines: list[str] = []
    reporter = SimpleNamespace(
        stats={"skipped": skipped} if skipped else {},
        write_line=lambda line, **markup: lines.append(line),
    )
    pytest_terminal_summary(reporter)  # type: ignore[arg-type]
    return lines


def test_a_run_that_skipped_the_database_tests_counts_them() -> None:
    lines = _summary(
        [
            SimpleNamespace(longrepr=("a.py", 1, f"Skipped: {DATABASE_SKIP_REASON} for a")),
            SimpleNamespace(longrepr=("b.py", 2, f"Skipped: {DATABASE_SKIP_REASON} for b")),
            SimpleNamespace(longrepr=("c.py", 3, "Skipped: docker is not available")),
        ]
    )

    assert len(lines) == 1
    assert lines[0].startswith("PostgreSQL-gated tests skipped: 2 (")


def test_a_run_that_skipped_none_says_nothing() -> None:
    assert _summary([SimpleNamespace(longrepr=("c.py", 3, "Skipped: docker"))]) == []
    assert _summary([]) == []


def test_every_database_skip_uses_the_counted_reason() -> None:
    """A gated test that skips with another wording would drop out of the count."""

    gate = re.compile(r"pytest\.skip\((.*OAK_TEST_DATABASE_URL.*)\)")
    reasons = [
        match.group(1)
        for path in sorted((ROOT / "tests").rglob("*.py"))
        for match in gate.finditer(path.read_text(encoding="utf-8"))
    ]

    assert len(reasons) >= 8
    assert all(DATABASE_SKIP_REASON in reason for reason in reasons), reasons
