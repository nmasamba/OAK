# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-001 bounded MCP protocol lifecycle and refusal tests."""

import io
import json
from typing import Any

from oak.interfaces.mcp.server import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPServer,
)
from oak.interfaces.mcp.tools import TOOL_DEFINITIONS, MCPToolExecutor


class _GuardControlPlane:
    """Any application dispatch during a refusal test is a failure."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected control-plane call: {name}")


def _server() -> MCPServer:
    executor = MCPToolExecutor(
        _GuardControlPlane(),  # type: ignore[arg-type]
        local_actor="local-user",
        local_tenant="local",
        clock=lambda: "2026-08-21T12:00:00Z",
    )
    return MCPServer(executor, server_version="test")


def _frame(server: MCPServer, document: dict[str, Any]) -> dict[str, Any] | None:
    return server.handle_frame(json.dumps(document, sort_keys=True).encode("utf-8"))


def _initialize(server: MCPServer, protocol_version: str = "2025-06-18") -> dict[str, Any]:
    response = _frame(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": protocol_version},
        },
    )
    assert response is not None
    return response


def test_initialize_negotiates_a_supported_protocol_version() -> None:
    response = _initialize(_server(), "2025-03-26")
    assert response["result"]["protocolVersion"] == "2025-03-26"
    assert response["result"]["capabilities"] == {"tools": {}}
    assert response["result"]["serverInfo"] == {"name": "oak-mcp", "version": "test"}


def test_unsupported_protocol_version_falls_back_to_the_server_latest() -> None:
    response = _initialize(_server(), "1999-01-01")
    assert response["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]


def test_requests_before_initialize_are_refused_except_ping() -> None:
    server = _server()
    ping = _frame(server, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ping is not None and ping["result"] == {}
    listing = _frame(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listing is not None
    assert listing["error"]["code"] == INVALID_REQUEST


def test_second_initialize_is_refused() -> None:
    server = _server()
    _initialize(server)
    again = _frame(
        server,
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
    )
    assert again is not None
    assert again["error"]["code"] == INVALID_REQUEST


def test_unknown_method_is_refused_not_ignored() -> None:
    server = _server()
    _initialize(server)
    for method in ("resources/read", "prompts/list", "completion/complete", "shell/execute"):
        response = _frame(server, {"jsonrpc": "2.0", "id": 9, "method": method})
        assert response is not None
        assert response["error"]["code"] == METHOD_NOT_FOUND


def test_unknown_notification_is_ignored_without_response() -> None:
    server = _server()
    _initialize(server)
    assert _frame(server, {"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None
    assert _frame(server, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_malformed_frames_are_parse_errors_and_do_not_stop_the_server() -> None:
    server = _server()
    _initialize(server)
    for raw in (b"not json", b"[1,2,3]", b'"string"', b'{"jsonrpc": "2.0", "jsonrpc": "2.0"}'):
        response = server.handle_frame(raw)
        assert response is not None
        assert response["error"]["code"] == PARSE_ERROR
        assert response["id"] is None
    invalid_utf8 = server.handle_frame(b'\xff\xfe{"jsonrpc": "2.0"}')
    assert invalid_utf8 is not None
    assert invalid_utf8["error"]["code"] == PARSE_ERROR
    ping = _frame(server, {"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert ping is not None and ping["result"] == {}


def test_request_id_must_be_a_string_or_integer() -> None:
    server = _server()
    response = _frame(server, {"jsonrpc": "2.0", "id": None, "method": "ping"})
    assert response is not None
    assert response["error"]["code"] == INVALID_REQUEST


def test_tools_list_returns_only_closed_bounded_schemas() -> None:
    server = _server()
    _initialize(server)
    response = _frame(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response is not None
    tools = response["result"]["tools"]
    assert len(tools) == len(TOOL_DEFINITIONS)
    for tool in tools:
        schema = tool["inputSchema"]
        assert schema["additionalProperties"] is False
        for name, property_schema in schema["properties"].items():
            if property_schema.get("type") == "string":
                assert property_schema["maxLength"] > 0, (tool["name"], name)
            else:
                assert property_schema == {"type": "object"}, (tool["name"], name)


def test_unknown_tool_is_refused_before_any_dispatch() -> None:
    server = _server()
    _initialize(server)
    for name in (
        "shell",
        "read_file",
        "oak_secret_resolve",
        "oak_plan_approve",
        "oak_runner_dispatch",
        "oak_policy_override",
        "oak_bundle_apply",
    ):
        response = _frame(
            server,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": name, "arguments": {}},
            },
        )
        assert response is not None
        assert response["error"]["code"] == INVALID_PARAMS
        assert response["error"]["data"]["code"] == "OAK-TOOL-UNKNOWN"


def test_arguments_violating_the_closed_schema_are_refused_before_dispatch() -> None:
    server = _server()
    _initialize(server)
    poisoned: tuple[dict[str, Any], ...] = (
        {"case_id": "design-case.example", "command": "rm -rf /"},
        {"case_id": "design-case.example", "argv": ["sh"]},
        {"case_id": 7},
        {},
        {"case_id": "x" * 161},
    )
    for arguments in poisoned:
        response = _frame(
            server,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "oak_design_case_get", "arguments": arguments},
            },
        )
        assert response is not None
        assert response["error"]["code"] == INVALID_PARAMS
        assert response["error"]["data"]["code"] == "OAK-REQUEST-INVALID"


def test_short_idempotency_key_is_refused_by_schema() -> None:
    server = _server()
    _initialize(server)
    response = _frame(
        server,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "oak_design_case_create",
                "arguments": {
                    "original_name": "brief.yaml",
                    "content": "title: x",
                    "idempotency_key": "short",
                },
            },
        },
    )
    assert response is not None
    assert response["error"]["data"]["code"] == "OAK-REQUEST-INVALID"


def test_confused_deputy_actor_is_denied_without_dispatch() -> None:
    server = _server()
    _initialize(server)
    response = _frame(
        server,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "oak_design_case_get",
                "arguments": {"case_id": "design-case.example", "actor": "administrator"},
            },
        },
    )
    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "OAK-ACTOR-DENIED"


def test_foreign_tenant_receives_an_opaque_denial_without_dispatch() -> None:
    server = _server()
    _initialize(server)
    response = _frame(
        server,
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "oak_design_case_get",
                "arguments": {"case_id": "design-case.example", "tenant_id": "other-tenant"},
            },
        },
    )
    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "OAK-TENANT-MISMATCH"
    assert result["structuredContent"]["message"] == "The requested resource was not found."


def test_oversized_frame_is_refused_and_the_session_continues() -> None:
    executor = MCPToolExecutor(
        _GuardControlPlane(),  # type: ignore[arg-type]
        local_actor="local-user",
        local_tenant="local",
    )
    server = MCPServer(executor, server_version="test", maximum_frame_bytes=512)
    oversized = (
        b'{"jsonrpc": "2.0", "id": 1, "method": "ping", "padding": "' + b"A" * 4096 + b'"}\n'
    )
    ping = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode("utf-8") + b"\n"
    reader = io.BytesIO(oversized + ping)
    writer = io.BytesIO()
    server.serve(reader, writer)
    responses = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(responses) == 2
    assert responses[0]["error"]["code"] == INVALID_REQUEST
    assert "limit" in responses[0]["error"]["message"]
    assert responses[1]["result"] == {}
