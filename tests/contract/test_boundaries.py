# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-003 executable module-boundary tests."""

from pathlib import Path

from tools.check_boundaries import check

ROOT = Path(__file__).resolve().parents[2]


def test_real_source_respects_module_boundaries() -> None:
    assert check(ROOT / "src") == []


def test_deliberate_application_to_adapter_import_is_rejected() -> None:
    violations = check(ROOT / "tests" / "fixtures" / "import_violation")

    assert len(violations) == 1
    assert "oak.application must not import oak.adapters" in violations[0].message
