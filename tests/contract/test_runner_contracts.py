# SPDX-License-Identifier: Apache-2.0
"""OAK-S5 contract invariants shared between compiler and runner trust domains."""

import json
from pathlib import Path

from oak.contracts.signatures import _canonical_json_bytes
from oak.domain import canonical_json_bytes
from oak.domain.runner_adapters import (
    ADAPTER_IDENTITY_BY_ID,
    ALLOWED_KINDS_BY_ADAPTER,
    CONTAINER_ADAPTER_ID,
    REVIEW_ADAPTER_ID,
)

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {"command", "shell", "executable", "argv"}


def test_contract_signatures_canonical_bytes_match_domain() -> None:
    for document in (
        {"z": 1, "a": [3, 2, 1], "nested": {"b": True, "a": None}},
        {"unicode": "café", "n": 0.5},
    ):
        assert _canonical_json_bytes(document) == canonical_json_bytes(document)


def test_every_adapter_identity_has_a_disjoint_kind_set() -> None:
    review = ALLOWED_KINDS_BY_ADAPTER[REVIEW_ADAPTER_ID]
    container = ALLOWED_KINDS_BY_ADAPTER[CONTAINER_ADAPTER_ID]
    assert review.isdisjoint(container)
    assert review == {"inventory", "validate", "render", "plan", "verify"}
    assert container == {"apply", "rollback", "destroy"}
    for identity in ADAPTER_IDENTITY_BY_ID.values():
        assert set(identity) == {"id", "version", "digest", "parameter_schema_digest"}


def test_no_committed_schema_permits_execution_fields() -> None:
    for path in (ROOT / "schemas").glob("*.schema.json"):
        text = path.read_text(encoding="utf-8")
        document = json.loads(text)
        # Execution fields may only appear inside an explicit denial (propertyNames/not/enum).
        for field in FORBIDDEN:
            if f'"{field}"' in text:
                assert "propertyNames" in text, f"{path.name} names {field} outside a denial"
        assert document  # schema parses


def test_runner_plan_example_has_no_execution_fields() -> None:
    from oak.contracts import load_yaml_document

    plan = load_yaml_document(
        (ROOT / "examples/example-runner-plan.yaml").read_text(encoding="utf-8")
    )
    serialized = json.dumps(plan).casefold()
    for field in FORBIDDEN:
        assert f'"{field}":' not in serialized
