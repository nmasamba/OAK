# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-001/007 MCP capability-matrix and cross-interface parity pins."""

from oak.domain import OAKError
from oak.interfaces.api.app import _error_status
from oak.interfaces.mcp.tools import NOT_FOUND_CODES, TOOL_DEFINITIONS, TOOL_NAMES

# The bounded surface from docs/build/interface-contract.md plus the documented
# operation-progress read query. Changing this set is a contract change and
# requires the compatibility policy's process, not a code-only edit.
DOCUMENTED_TOOLS = frozenset(
    {
        "oak_design_case_create",
        "oak_design_case_get",
        "oak_design_case_interpret",
        "oak_questions_list",
        "oak_claims_confirm",
        "oak_candidates_generate",
        "oak_candidates_list",
        "oak_candidate_evaluate",
        "oak_assurance_plan_create",
        "oak_bundle_compile",
        "oak_operation_get",
    }
)

# Capabilities the interface contract prohibits from ever appearing on MCP.
FORBIDDEN_TOOL_TERMS = (
    "shell",
    "command",
    "exec",
    "file",
    "secret",
    "approve",
    "approval",
    "sign",
    "revoke",
    "dispatch",
    "apply",
    "rollback",
    "destroy",
    "policy_override",
    "select",
)


def test_the_tool_registry_is_exactly_the_documented_capability_matrix() -> None:
    assert TOOL_NAMES == DOCUMENTED_TOOLS


def test_no_tool_name_carries_a_forbidden_capability() -> None:
    for name in TOOL_NAMES:
        segments = set(name.split("_"))
        for term in FORBIDDEN_TOOL_TERMS:
            if "_" in term:
                assert term not in name, (name, term)
            else:
                assert term not in segments, (name, term)


def test_every_tool_schema_is_closed_and_every_string_is_bounded() -> None:
    for definition in TOOL_DEFINITIONS:
        schema = definition.input_schema
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"], definition.name
        for property_name, property_schema in schema["properties"].items():
            if property_schema == {"type": "object"}:
                assert property_name in {"answers", "target"}, definition.name
                continue
            assert property_schema["type"] == "string", (definition.name, property_name)
            assert 0 < property_schema["minLength"] <= property_schema["maxLength"]


def test_mutating_tools_require_idempotency_and_versioned_tools_require_expected_version() -> None:
    mutating = {
        "oak_design_case_create",
        "oak_design_case_interpret",
        "oak_claims_confirm",
        "oak_candidates_generate",
        "oak_candidate_evaluate",
        "oak_assurance_plan_create",
        "oak_bundle_compile",
    }
    for definition in TOOL_DEFINITIONS:
        required = set(definition.input_schema["required"])
        if definition.name in mutating:
            assert "idempotency_key" in required, definition.name
            if definition.name != "oak_design_case_create":
                assert "expected_version" in required, definition.name
        else:
            assert "idempotency_key" not in required, definition.name
    confirm = next(d for d in TOOL_DEFINITIONS if d.name == "oak_claims_confirm")
    assert "actor" in set(confirm.input_schema["required"])


def test_mcp_opaque_not_found_family_matches_the_rest_404_family() -> None:
    for code in NOT_FOUND_CODES:
        assert _error_status(OAKError(code, "probe")) == 404, code
    for code in ("OAK-ACTOR-DENIED", "OAK-EXPECTED-VERSION", "OAK-CONFIRM-MALFORMED"):
        assert code not in NOT_FOUND_CODES
        assert _error_status(OAKError(code, "probe")) != 404, code


def _length_bounds(metadata: object) -> tuple[int | None, int | None]:
    """Extract (minLength, maxLength) from annotated-types metadata."""

    import annotated_types as at

    minimum = maximum = None
    for constraint in getattr(metadata, "metadata", metadata) or ():
        if isinstance(constraint, at.MinLen):
            minimum = constraint.min_length
        if isinstance(constraint, at.MaxLen):
            maximum = constraint.max_length
    return minimum, maximum


def _tool_property(tool_name: str, field: str) -> dict[str, object]:
    definition = next(d for d in TOOL_DEFINITIONS if d.name == tool_name)
    return definition.input_schema["properties"][field]


def test_mcp_argument_bounds_mirror_the_rest_request_models() -> None:
    import importlib
    from typing import get_args

    from oak.interfaces.api import models

    app = importlib.import_module("oak.interfaces.api.app")

    # Header-derived context bounds must equal the REST header source, checked
    # against every tool that carries each field — not a hardcoded literal.
    header_sources = {
        "idempotency_key": app.IdempotencyHeader,
        "expected_version": app.ExpectedVersionHeader,
        "correlation_id": app.CorrelationHeader,
    }
    for field, annotation in header_sources.items():
        rest_bounds = _length_bounds(get_args(annotation)[1])
        for definition in TOOL_DEFINITIONS:
            schema = definition.input_schema["properties"].get(field)
            if schema is None:
                continue
            assert (schema.get("minLength"), schema.get("maxLength")) == rest_bounds, (
                definition.name,
                field,
            )

    # Request-body model bounds must equal the matching MCP tool argument bounds.
    create = models.CreateDesignCaseRequest.model_fields
    assert _length_bounds(create["original_name"]) == (
        _tool_property("oak_design_case_create", "original_name").get("minLength"),
        _tool_property("oak_design_case_create", "original_name").get("maxLength"),
    )
    assert _length_bounds(create["content"]) == (
        _tool_property("oak_design_case_create", "content").get("minLength"),
        _tool_property("oak_design_case_create", "content").get("maxLength"),
    )

    # Every identifier-shaped MCP argument must match the REST identifier bounds
    # (case_id/candidate_id in the request models), including the minLength that
    # a previous version of this test never referenced.
    identifier_bounds = _length_bounds(models.EvaluateCandidateRequest.model_fields["case_id"])
    for tool_name, field in (
        ("oak_design_case_get", "case_id"),
        ("oak_design_case_interpret", "case_id"),
        ("oak_candidate_evaluate", "candidate_id"),
        ("oak_assurance_plan_create", "candidate_id"),
        ("oak_bundle_compile", "candidate_id"),
        ("oak_operation_get", "operation_id"),
    ):
        schema = _tool_property(tool_name, field)
        assert (schema.get("minLength"), schema.get("maxLength")) == identifier_bounds, (
            tool_name,
            field,
        )
