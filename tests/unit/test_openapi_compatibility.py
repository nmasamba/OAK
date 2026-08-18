# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-008 local OpenAPI breaking-change gate tests."""

import copy
import json
from pathlib import Path

from scripts.check_openapi_compatibility import compatibility_errors, contract_signature

ROOT = Path(__file__).resolve().parents[2]


def test_committed_openapi_matches_its_compatibility_baseline() -> None:
    current = json.loads((ROOT / "openapi/oak.openapi.json").read_text(encoding="utf-8"))
    baseline = json.loads(
        (ROOT / "openapi/oak.compatibility-baseline.json").read_text(encoding="utf-8")
    )

    assert compatibility_errors(baseline, current) == ()


def test_compatibility_gate_rejects_removed_operation_and_required_field() -> None:
    current = json.loads((ROOT / "openapi/oak.openapi.json").read_text(encoding="utf-8"))
    baseline = contract_signature(current)
    incompatible = copy.deepcopy(current)
    del incompatible["paths"]["/version"]
    incompatible["components"]["schemas"]["VersionResponse"]["required"].remove("version")

    errors = compatibility_errors(baseline, incompatible)

    assert "removed path /version" in errors
    assert "changed required fields for schema VersionResponse" in errors
