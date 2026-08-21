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


def test_mcp_argument_bounds_mirror_the_rest_request_models() -> None:
    from oak.interfaces.api import models

    create = next(d for d in TOOL_DEFINITIONS if d.name == "oak_design_case_create")
    properties = create.input_schema["properties"]
    original_name = models.CreateDesignCaseRequest.model_fields["original_name"]
    content = models.CreateDesignCaseRequest.model_fields["content"]
    assert properties["original_name"]["maxLength"] == original_name.metadata[1].max_length
    assert properties["content"]["maxLength"] == content.metadata[1].max_length
    assert properties["idempotency_key"]["minLength"] == 16
    assert properties["idempotency_key"]["maxLength"] == 240
