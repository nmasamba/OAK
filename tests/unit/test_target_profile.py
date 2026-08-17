# SPDX-License-Identifier: Apache-2.0
"""OAK-S2-010 bounded target-profile tests."""

from pathlib import Path

import pytest

from oak.adapters.targets import LocalTargetProfile
from oak.contracts import SchemaRegistry
from oak.domain import OAKError

ROOT = Path(__file__).resolve().parents[2]


def _loader() -> LocalTargetProfile:
    return LocalTargetProfile(SchemaRegistry.from_directory(ROOT / "schemas"))


def test_non_production_read_only_target_profile_is_valid() -> None:
    target = _loader().load(ROOT / "examples/targets/local-fixture.yaml")

    assert target["status"] == "non-production-fixture"
    assert target["permissions"]["mutation_allowed"] is False
    assert "apply" not in target["permissions"]["allowed_operations"]


@pytest.mark.parametrize(
    "source",
    (
        "target_profile_version: 0.1.0\nid: target.bad\npermissions:\n  mutation_allowed: true\n",
        "payload: &payload poisoned\ncopy: *payload\n",
    ),
)
def test_mutating_or_aliased_target_profile_is_rejected(tmp_path: Path, source: str) -> None:
    target = tmp_path / "target.yaml"
    target.write_text(source, encoding="utf-8")

    with pytest.raises(OAKError) as captured:
        _loader().load(target)

    assert captured.value.code == "OAK-TARGET-INVALID"
