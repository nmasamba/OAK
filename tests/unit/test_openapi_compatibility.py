# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-008 local OpenAPI breaking-change gate tests."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.check_openapi_compatibility import compatibility_errors, contract_signature

ROOT = Path(__file__).resolve().parents[2]

# Operations and schemas in the committed contract that no release has shipped yet. A
# change that adds one lists it here, so leaving it unguarded is a decision and not an
# oversight. The release that first ships it rewrites the baseline from its own contract
# (`docs/release-process.md`) and removes it from these sets. Nothing made that step
# visible before, so the baseline stayed at its Sprint 3 contents through `0.7.1` and
# `0.8.0`.
UNRELEASED_OPERATIONS: frozenset[str] = frozenset()
UNRELEASED_SCHEMAS: frozenset[str] = frozenset()

# Operations that shipped after Sprint 3 and that the baseline did not guard until it was
# refreshed from the `0.8.0` contract: the case list and the audit trail, published in
# `0.7.1`, and the `/v1/models` resources, which first shipped in `0.8.0`.
OPERATIONS_GUARDED_SINCE_THE_REFRESH = (
    ("get", "/v1/design-cases"),
    ("get", "/v1/design-cases/{case_id}/audit"),
    ("get", "/v1/models"),
    ("put", "/v1/models/credentials/{family}"),
    ("delete", "/v1/models/credentials/{family}"),
    ("put", "/v1/models/selection"),
    ("delete", "/v1/models/selection/{family}"),
    ("get", "/v1/models/{family}/catalogue"),
    ("post", "/v1/models/{family}:discover"),
    ("post", "/v1/models/{family}:verify"),
)


def _committed_openapi() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (ROOT / "openapi/oak.openapi.json").read_text(encoding="utf-8")
    )
    return document


def _baseline() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (ROOT / "openapi/oak.compatibility-baseline.json").read_text(encoding="utf-8")
    )
    return document


def _operations(signature: dict[str, Any]) -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, methods in signature["paths"].items()
        for method in methods
    }


def test_committed_openapi_matches_its_compatibility_baseline() -> None:
    assert compatibility_errors(_baseline(), _committed_openapi()) == ()


def test_compatibility_gate_rejects_removed_operation_and_required_field() -> None:
    current = _committed_openapi()
    baseline = contract_signature(current)
    incompatible = copy.deepcopy(current)
    del incompatible["paths"]["/version"]
    incompatible["components"]["schemas"]["VersionResponse"]["required"].remove("version")

    errors = compatibility_errors(baseline, incompatible)

    assert "removed path /version" in errors
    assert "changed required fields for schema VersionResponse" in errors


def test_every_operation_and_schema_in_the_contract_is_guarded_or_listed_as_unreleased() -> None:
    """A shipped shape the baseline does not hold can be removed without the gate noticing.

    That is how `/v1/models` and the audit trail went unguarded through two releases: the
    gate passes additive changes, as it should, and nothing ever added them to the baseline.
    """

    current = contract_signature(_committed_openapi())
    baseline = _baseline()

    unguarded_operations = _operations(current) - _operations(baseline) - UNRELEASED_OPERATIONS
    unguarded_schemas = set(current["schemas"]) - set(baseline["schemas"]) - UNRELEASED_SCHEMAS

    assert not unguarded_operations, (
        "operations neither in the baseline nor listed as unreleased: "
        f"{sorted(unguarded_operations)}"
    )
    assert not unguarded_schemas, (
        f"schemas neither in the baseline nor listed as unreleased: {sorted(unguarded_schemas)}"
    )
    # An entry the baseline already holds has shipped, so listing it as unreleased is stale.
    assert not UNRELEASED_OPERATIONS & _operations(baseline)
    assert not UNRELEASED_SCHEMAS & set(baseline["schemas"])


@pytest.mark.parametrize(("method", "path"), OPERATIONS_GUARDED_SINCE_THE_REFRESH)
def test_removing_an_operation_shipped_after_sprint_3_fails_the_gate(
    method: str, path: str
) -> None:
    removed = _committed_openapi()
    del removed["paths"][path][method]

    assert f"removed operation {method.upper()} {path}" in compatibility_errors(
        _baseline(), removed
    )


def test_removing_a_field_from_the_model_status_response_fails_the_gate() -> None:
    changed = _committed_openapi()
    del changed["components"]["schemas"]["ModelStatusResponse"]["properties"]["modes"]

    assert "removed property ModelStatusResponse.modes" in compatibility_errors(
        _baseline(), changed
    )
