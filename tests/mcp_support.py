# SPDX-License-Identifier: Apache-2.0
"""Shared harness for MCP interface tests.

Builds a real file-backed ``CommunityControlPlane`` with an in-memory durable
operation store, so MCP behavior is tested end-to-end without PostgreSQL.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import CommunityControlPlane, OperationService, OperationWorker
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from oak.interfaces.mcp.server import MCPServer, create_server
from oak.ports import EnqueuedOperation, OperationLease, OperationRecord, OperationSpec

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-21T12:00:00Z"
LATER = "2026-08-21T12:01:00Z"


class MemoryOperationStore:
    """Deterministic in-memory ``OperationStore`` for database-free tests."""

    def __init__(self) -> None:
        self.records: dict[str, OperationRecord] = {}

    def idempotent(self, spec: OperationSpec) -> OperationRecord | None:
        return self.records.get(spec.operation_id)

    def enqueue(self, spec: OperationSpec) -> EnqueuedOperation:
        existing = self.records.get(spec.operation_id)
        if existing is not None:
            return EnqueuedOperation(existing, duplicate=True)
        record = OperationRecord(
            operation_id=spec.operation_id,
            workspace_id=spec.workspace_id,
            case_id=spec.case_id,
            kind=spec.kind,
            state="queued",
            version=1,
            request_digest=spec.request_digest,
            request=spec.request,
            result=None,
            problem=None,
            correlation_id=spec.correlation_id,
            attempt_count=0,
            max_attempts=spec.max_attempts,
            next_attempt_at=spec.created_at,
            leased_by=None,
            lease_expires_at=None,
            cancel_requested=False,
            cancel_requested_by=None,
            cancel_idempotency_key=None,
            cancel_correlation_id=None,
            cancel_requested_at=None,
            checkpoint=None,
            created_at=spec.created_at,
            updated_at=spec.created_at,
            completed_at=None,
        )
        self.records[spec.operation_id] = record
        return EnqueuedOperation(record, duplicate=False)

    def get(self, operation_id: str) -> OperationRecord:
        record = self.records.get(operation_id)
        if record is None:
            raise OAKError("OAK-OPERATION-NOT-FOUND", "operation was not found")
        return record

    def cancel(
        self,
        operation_id: str,
        *,
        actor: str,
        idempotency_key: str,
        correlation_id: str,
        requested_at: str,
    ) -> OperationRecord:
        record = self.get(operation_id)
        updated = replace(
            record,
            cancel_requested=True,
            cancel_requested_by=actor,
            cancel_idempotency_key=idempotency_key,
            cancel_correlation_id=correlation_id,
            cancel_requested_at=requested_at,
            state="cancelled" if record.state == "queued" else record.state,
            updated_at=requested_at,
        )
        self.records[operation_id] = updated
        return updated

    def claim(self, *, worker_id: str, now: str, lease_expires_at: str) -> OperationLease | None:
        for operation_id, record in sorted(self.records.items()):
            if record.state == "queued" and record.next_attempt_at <= now:
                updated = replace(
                    record,
                    state="running",
                    leased_by=worker_id,
                    lease_expires_at=lease_expires_at,
                    attempt_count=record.attempt_count + 1,
                    updated_at=now,
                )
                self.records[operation_id] = updated
                return OperationLease(updated, worker_id, lease_expires_at)
        return None

    def heartbeat(
        self, lease: OperationLease, *, now: str, lease_expires_at: str
    ) -> OperationLease:
        record = replace(self.get(lease.operation.operation_id), lease_expires_at=lease_expires_at)
        self.records[record.operation_id] = record
        return OperationLease(record, lease.worker_id, lease_expires_at)

    def checkpoint(
        self, lease: OperationLease, *, checkpoint: dict[str, Any], recorded_at: str
    ) -> OperationRecord:
        record = replace(
            self.get(lease.operation.operation_id),
            checkpoint=checkpoint,
            updated_at=recorded_at,
        )
        self.records[record.operation_id] = record
        return record

    def succeed(
        self, lease: OperationLease, *, result: dict[str, Any], completed_at: str
    ) -> OperationRecord:
        record = replace(
            self.get(lease.operation.operation_id),
            state="succeeded",
            result=result,
            leased_by=None,
            lease_expires_at=None,
            updated_at=completed_at,
            completed_at=completed_at,
        )
        self.records[record.operation_id] = record
        return record

    def fail(
        self,
        lease: OperationLease,
        *,
        error_code: str,
        retriable: bool,
        failed_at: str,
        retry_at: str,
    ) -> OperationRecord:
        current = self.get(lease.operation.operation_id)
        exhausted = current.attempt_count >= current.max_attempts
        record = replace(
            current,
            state="queued" if retriable and not exhausted else "failed",
            problem={"code": error_code, "retriable": retriable},
            next_attempt_at=retry_at,
            leased_by=None,
            lease_expires_at=None,
            updated_at=failed_at,
            completed_at=None if retriable and not exhausted else failed_at,
        )
        self.records[record.operation_id] = record
        return record

    def acknowledge_cancellation(
        self, lease: OperationLease, *, cancelled_at: str
    ) -> OperationRecord:
        record = replace(
            self.get(lease.operation.operation_id),
            state="cancelled",
            leased_by=None,
            lease_expires_at=None,
            updated_at=cancelled_at,
            completed_at=cancelled_at,
        )
        self.records[record.operation_id] = record
        return record


def build_file_control_plane(
    tmp_path: Path,
) -> tuple[CommunityControlPlane, MemoryOperationStore]:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir(parents=True, exist_ok=True)
    store = MemoryOperationStore()

    def repository_factory(workspace_id: str, tenant_id: str) -> FileWorkspaceRepository:
        del tenant_id  # tenant scope is enforced by the workspace manifest itself
        return FileWorkspaceRepository(workspaces / workspace_id, registry)

    def operation_service_factory(tenant_id: str) -> OperationService:
        del tenant_id
        return OperationService(store, environment_id="mcp-test")

    control_plane = CommunityControlPlane(
        repository_factory,
        operation_service_factory,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )
    return control_plane, store


def drain_operations(control_plane: CommunityControlPlane, store: MemoryOperationStore) -> int:
    """Run queued operations to completion; returns how many were executed."""

    worker = OperationWorker(
        store,
        {
            "generate_candidates": control_plane.execute_operation,
            "evaluate_candidate": control_plane.execute_operation,
            "compile_bundle": control_plane.execute_operation,
        },
    )
    executed = 0
    while True:
        record = worker.run_once(worker_id="mcp-test-worker", now=NOW, lease_expires_at=LATER)
        if record is None:
            return executed
        executed += 1


class MCPClient:
    """Speak real newline-delimited JSON-RPC frames to an ``MCPServer``."""

    def __init__(self, server: MCPServer, *, protocol_version: str = "2025-06-18") -> None:
        self._server = server
        self._next_id = 0
        initialization = self.request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "oak-tests", "version": "0"},
            },
        )
        assert "result" in initialization, initialization

    def frame(self, document: dict[str, Any]) -> dict[str, Any] | None:
        return self._server.handle_frame(
            json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        response = self.frame(message)
        assert response is not None, f"request {method} produced no response"
        return response

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return the tool result object (may be an in-band error)."""

        response = self.request("tools/call", {"name": name, "arguments": arguments})
        assert "result" in response, response
        result: dict[str, Any] = response["result"]
        return result

    def call_ok(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.call(name, arguments)
        assert result["isError"] is False, result
        structured: dict[str, Any] = result["structuredContent"]
        return structured

    def call_error(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.call(name, arguments)
        assert result["isError"] is True, result
        structured: dict[str, Any] = result["structuredContent"]
        return structured


def build_server(tmp_path: Path) -> tuple[MCPServer, CommunityControlPlane, MemoryOperationStore]:
    control_plane, store = build_file_control_plane(tmp_path)
    server = create_server(
        control_plane,
        server_version="test",
        local_actor="local-user",
        local_tenant="local",
        clock=lambda: NOW,
    )
    return server, control_plane, store


__all__ = [
    "LATER",
    "NOW",
    "ROOT",
    "MCPClient",
    "MemoryOperationStore",
    "build_file_control_plane",
    "build_server",
    "drain_operations",
]
