# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-003 executable module-boundary tests."""

from pathlib import Path

from tools.check_boundaries import check

ROOT = Path(__file__).resolve().parents[2]


def test_real_source_respects_module_boundaries() -> None:
    assert check(ROOT / "src") == []


def test_deliberate_violations_are_rejected() -> None:
    violations = check(ROOT / "tests" / "fixtures" / "import_violation")
    messages = sorted(violation.message for violation in violations)

    assert messages == [
        "oak.application must not import oak.adapters",
        "oak.compiler must not import httpx",
    ]
