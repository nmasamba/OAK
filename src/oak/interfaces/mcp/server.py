# SPDX-License-Identifier: Apache-2.0
"""Bounded stdio MCP server process.

The transport is newline-delimited JSON-RPC 2.0 over stdio, the tools-only subset of
the Model Context Protocol. Frames are size-bounded before parsing, unknown methods
and tools are refused, and every tool call is mediated by the shared application
services; the server itself holds no state and no authority.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterator
from typing import Any, BinaryIO

from oak.application import CommunityControlPlane
from oak.bootstrap import create_persistent_control_plane, create_system_information_service
from oak.contracts import load_json_document
from oak.interfaces.mcp.tools import MCPToolExecutor, ToolArgumentError

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
MAXIMUM_FRAME_BYTES = 1_048_576
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _frames(reader: BinaryIO, maximum_bytes: int) -> Iterator[bytes | None]:
    """Yield newline-delimited frames; an oversized frame yields ``None``.

    The limit is enforced while reading: ``readline`` never buffers more than one
    bounded chunk, and the remainder of an oversized line is discarded in bounded
    chunks without being retained.
    """

    while True:
        chunk = reader.readline(maximum_bytes + 1)
        if chunk == b"":
            return
        if len(chunk) > maximum_bytes and not chunk.endswith(b"\n"):
            while True:
                remainder = reader.readline(maximum_bytes)
                if remainder == b"" or remainder.endswith(b"\n"):
                    break
            yield None
            continue
        frame = chunk.rstrip(b"\r\n")
        if frame:
            yield frame


class MCPServer:
    """Serve the bounded tool set to one stdio client until end of input."""

    def __init__(
        self,
        executor: MCPToolExecutor,
        *,
        server_version: str,
        maximum_frame_bytes: int = MAXIMUM_FRAME_BYTES,
    ) -> None:
        self._executor = executor
        self._server_version = server_version
        self._maximum_frame_bytes = maximum_frame_bytes
        self._initialized = False

    def serve(self, reader: BinaryIO, writer: BinaryIO) -> None:
        for frame in _frames(reader, self._maximum_frame_bytes):
            if frame is None:
                self._write(
                    writer,
                    self._error(
                        None,
                        INVALID_REQUEST,
                        f"frame exceeds the {self._maximum_frame_bytes}-byte limit",
                    ),
                )
                continue
            response = self.handle_frame(frame)
            if response is not None:
                self._write(writer, response)

    def handle_frame(self, frame: bytes) -> dict[str, Any] | None:
        """Handle one raw frame; returns the response document or ``None``."""

        try:
            message = load_json_document(frame.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._error(None, PARSE_ERROR, "frame is not a JSON-RPC object")
        return self._handle_message(message)

    def _handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        is_request = "id" in message
        if is_request and not isinstance(request_id, (str, int)):
            return self._error(None, INVALID_REQUEST, "request id must be a string or integer")
        method = message.get("method")
        if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
            if not is_request:
                return None
            return self._error(request_id, INVALID_REQUEST, "message is not a JSON-RPC request")
        params = message.get("params", {})
        if not isinstance(params, dict):
            if not is_request:
                return None
            return self._error(request_id, INVALID_REQUEST, "params must be an object")
        if not is_request:
            # Notifications carry no response channel; only the initialized
            # notification is meaningful and everything else is ignored.
            return None
        if method == "initialize":
            return self._initialize(request_id, params)
        if method == "ping":
            return self._result(request_id, {})
        if not self._initialized:
            return self._error(request_id, INVALID_REQUEST, "server is not initialized")
        if method == "tools/list":
            return self._result(request_id, {"tools": self._executor.list_tools()})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        return self._error(request_id, METHOD_NOT_FOUND, "method is not supported")

    def _initialize(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        if self._initialized:
            return self._error(request_id, INVALID_REQUEST, "server is already initialized")
        requested = params.get("protocolVersion")
        negotiated = (
            requested
            if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        self._initialized = True
        return self._result(
            request_id,
            {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "oak-mcp", "version": self._server_version},
            },
        )

    def _call_tool(self, request_id: str | int | None, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return self._error(request_id, INVALID_PARAMS, "tool call params are invalid")
        try:
            result = self._executor.call(name, arguments)
        except KeyError:
            return self._error(
                request_id,
                INVALID_PARAMS,
                "tool is not available",
                data={"code": "OAK-TOOL-UNKNOWN"},
            )
        except ToolArgumentError as error:
            return self._error(
                request_id,
                INVALID_PARAMS,
                "tool arguments did not match the tool contract",
                data={"code": "OAK-REQUEST-INVALID", "errors": list(error.errors)},
            )
        return self._result(request_id, result)

    @staticmethod
    def _result(request_id: str | int | None, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(
        request_id: str | int | None,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    @staticmethod
    def _write(writer: BinaryIO, response: dict[str, Any]) -> None:
        writer.write(
            json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        )
        writer.flush()


def create_server(
    control_plane: CommunityControlPlane,
    *,
    server_version: str,
    local_actor: str | None = None,
    local_tenant: str | None = None,
    clock: Callable[[], str] | None = None,
) -> MCPServer:
    bound_actor: str = (
        local_actor if local_actor else os.environ.get("OAK_LOCAL_ACTOR") or "local-user"
    )
    bound_tenant: str = (
        local_tenant if local_tenant else os.environ.get("OAK_LOCAL_TENANT") or "local"
    )
    if clock is None:
        executor = MCPToolExecutor(
            control_plane, local_actor=bound_actor, local_tenant=bound_tenant
        )
    else:
        executor = MCPToolExecutor(
            control_plane, local_actor=bound_actor, local_tenant=bound_tenant, clock=clock
        )
    return MCPServer(executor, server_version=server_version)


def main() -> None:
    try:
        control_plane = create_persistent_control_plane()
    except RuntimeError as error:
        raise SystemExit(f"OAK-MCP-CONFIG: {error}") from error
    information = create_system_information_service().get_information()
    server = create_server(control_plane, server_version=information.version)
    server.serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":  # pragma: no cover
    main()
