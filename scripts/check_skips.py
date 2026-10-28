# SPDX-License-Identifier: Apache-2.0
"""Fail unless a CI job's test runs skipped exactly what that job is expected to skip.

A skipped test reads like a pass in a green tick, so each job that runs `make check` sets
`OAK_SKIP_LEDGER`; `tests/conftest.py` writes every skipped test and its reason there, and
this script compares the count per reason with the job's row in `tests/expected-skips.json`.
A new reason, a reason the job no longer meets, or a count that moved fails the job, so a
skip that widens is a reviewed change to what the job proves (RR-014). Adding a test behind
a gate a job does not meet (a PostgreSQL-gated test on macOS) means raising that count.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = ROOT / "tests" / "expected-skips.json"


def tally(lines: Iterable[str]) -> dict[str, int]:
    """Count a ledger's skips by reason."""

    counts: Counter[str] = Counter()
    for line in lines:
        if line.strip():
            counts[str(json.loads(line)["reason"])] += 1
    return dict(counts)


def compare(actual: Mapping[str, int], expected: Mapping[str, int]) -> list[str]:
    """Every difference between what a job skipped and what it is expected to skip."""

    problems: list[str] = []
    for reason in sorted(set(actual) | set(expected)):
        found, wanted = actual.get(reason, 0), expected.get(reason, 0)
        if found != wanted:
            problems.append(f"{found} skipped, {wanted} expected: {reason}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("job", help="the job's key in tests/expected-skips.json")
    arguments = parser.parse_args(argv)
    expectations = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    if arguments.job not in expectations:
        print(f"skips refused: no expectation for job {arguments.job!r}", file=sys.stderr)
        return 1
    lines = (
        arguments.ledger.read_text(encoding="utf-8").splitlines()
        if arguments.ledger.is_file()
        else []
    )
    actual = tally(lines)
    expected = {str(key): int(value) for key, value in expectations[arguments.job].items()}
    for reason, count in sorted(actual.items()):
        print(f"skipped {count:>4}  {reason}")
    problems = compare(actual, expected)
    if problems:
        print(f"skips refused for {arguments.job}:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"skips as expected for {arguments.job}: {sum(actual.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
