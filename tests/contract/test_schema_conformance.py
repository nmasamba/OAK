# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-004 canonical schema/runtime conformance tests."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from oak.contracts import (
    CanonicalDocument,
    ContractValidationError,
    SchemaRegistry,
    load_json_document,
    load_yaml_document,
)
from scripts.validate_repository import EXAMPLE_BY_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    return load_yaml_document(path.read_text(encoding="utf-8"))


def test_every_canonical_schema_loads_and_has_a_public_example() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")

    assert set(EXAMPLE_BY_SCHEMA) == set(registry.names) - {"common.schema.json"}
    for schema_name, example_name in EXAMPLE_BY_SCHEMA.items():
        registry.validate(schema_name, _load_yaml(ROOT / "examples" / example_name))


@pytest.mark.parametrize("schema_name,example_name", sorted(EXAMPLE_BY_SCHEMA.items()))
def test_yaml_runtime_json_round_trip_has_no_semantic_drift(
    schema_name: str, example_name: str
) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    source = _load_yaml(ROOT / "examples" / example_name)

    runtime = CanonicalDocument.model_validate(source)
    result = json.loads(runtime.model_dump_json())

    assert result == source
    registry.validate(schema_name, result)


def test_invalid_document_is_rejected_with_a_safe_path() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")

    with pytest.raises(ContractValidationError) as captured:
        registry.validate("design-case.schema.json", {})

    assert captured.value.schema_name == "design-case.schema.json"
    assert captured.value.path.startswith("/")


@pytest.mark.parametrize("field", ("command", "shell", "executable", "argv"))
def test_runner_plan_rejects_execution_fields_even_when_nested(field: str) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    plan = _load_yaml(ROOT / "examples/example-runner-plan.yaml")
    poisoned = copy.deepcopy(plan)
    poisoned["operations"][0]["parameters"]["nested"] = {field: "untrusted"}

    with pytest.raises(ContractValidationError):
        registry.validate("runner-plan.schema.json", poisoned)


@pytest.mark.parametrize(
    "source",
    (
        '{"id":"first","id":"second"}',
        '{"value":NaN}',
        "[]",
    ),
)
def test_json_runtime_rejects_duplicate_nonfinite_or_non_object_input(source: str) -> None:
    with pytest.raises(ValueError):
        load_json_document(source)


@pytest.mark.parametrize(
    "source", ("value: .nan\n", "1: numeric-key\n", "value: !!set {a: null}\n")
)
def test_yaml_runtime_rejects_non_json_values(source: str) -> None:
    with pytest.raises(ValueError):
        load_yaml_document(source)
