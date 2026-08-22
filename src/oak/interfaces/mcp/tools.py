# SPDX-License-Identifier: Apache-2.0
"""Bounded typed MCP tool registry over the shared application services.

Every tool maps one bounded typed call onto ``CommunityControlPlane``. There is no
generic command executor, file reader, secret resolver, policy override, approval,
signing, revocation, or runner dispatch tool, and none may be added without failing
the capability-matrix contract tests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jsonschema.validators import validator_for

from oak.application import CommandContext, CommunityControlPlane
from oak.contracts import ContractValidationError, payload_safe_reason
from oak.domain import OAKError

# Argument bounds mirror the REST request models exactly so a value accepted by one
# interface is accepted by every interface.
_IDENTIFIER = {"type": "string", "minLength": 3, "maxLength": 160}
_ORIGINAL_NAME = {"type": "string", "minLength": 1, "maxLength": 240}
_CONTENT = {"type": "string", "minLength": 1, "maxLength": 262_144}
_IDEMPOTENCY_KEY = {"type": "string", "minLength": 16, "maxLength": 240}
_EXPECTED_VERSION = {"type": "string", "minLength": 3, "maxLength": 90}
_CORRELATION_ID = {"type": "string", "minLength": 8, "maxLength": 160}
_ACTOR = {"type": "string", "minLength": 1, "maxLength": 120}
_TENANT = {"type": "string", "minLength": 1, "maxLength": 120}
_DOCUMENT = {"type": "object"}

# Codes whose messages are replaced with an opaque detail so no interface leaks
# existence information. This set must stay equal to the REST 404 family in
# ``oak.interfaces.api.app._error_status``; a contract test pins the two together.
NOT_FOUND_CODES = frozenset(
    {
        "OAK-CASE-NOT-FOUND",
        "OAK-CANDIDATE-NOT-FOUND",
        "OAK-OPERATION-NOT-FOUND",
        "OAK-WORKSPACE-NOT-FOUND",
        "OAK-ARTIFACT-NOT-FOUND",
        "OAK-TENANT-MISMATCH",
    }
)
OPAQUE_NOT_FOUND_DETAIL = "The requested resource was not found."


class ToolArgumentError(ValueError):
    """Tool arguments failed the closed input schema."""

    def __init__(self, errors: tuple[dict[str, str], ...]) -> None:
        super().__init__("tool arguments did not match the tool contract")
        self.errors = errors


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


def _schema(
    properties: dict[str, dict[str, Any]],
    *,
    required: tuple[str, ...],
    context: bool = False,
) -> dict[str, Any]:
    merged = dict(properties)
    if context:
        merged["actor"] = _ACTOR
        merged["tenant_id"] = _TENANT
        merged["correlation_id"] = _CORRELATION_ID
    return {
        "type": "object",
        "properties": merged,
        "required": list(required),
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="oak_design_case_create",
        description=(
            "Create a design case from bounded brief content. Canonical draft only; "
            "the content is stored as untrusted data."
        ),
        input_schema=_schema(
            {
                "original_name": _ORIGINAL_NAME,
                "content": _CONTENT,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("original_name", "content", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_design_case_get",
        description="Read one design case with its current typed intent. Read only.",
        input_schema=_schema(
            {"case_id": _IDENTIFIER},
            required=("case_id",),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_design_case_interpret",
        description=(
            "Deterministically interpret the case brief into a typed draft intent with "
            "provenance. Proposal only; nothing is confirmed."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_questions_list",
        description="List the current deterministic clarification questions. Read only.",
        input_schema=_schema(
            {"case_id": _IDENTIFIER},
            required=("case_id",),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_claims_confirm",
        description=(
            "Record confirm/correct/reject/accept-risk decisions as immutable successors. "
            "Requires the named actor and the expected case version."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "answers": _DOCUMENT,
                "actor": _ACTOR,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "answers", "actor", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_candidates_generate",
        description=(
            "Submit deterministic candidate generation as a durable asynchronous "
            "operation. Returns an operation reference, not candidates."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_candidates_list",
        description="List generated candidates with rejection reasons. Read only.",
        input_schema=_schema(
            {"case_id": _IDENTIFIER},
            required=("case_id",),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_candidate_evaluate",
        description=(
            "Submit the deterministic reference evaluation for one candidate as a durable "
            "asynchronous operation. Evidence only; selects nothing."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "candidate_id": _IDENTIFIER,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "candidate_id", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_assurance_plan_create",
        description=(
            "Create the selected candidate's deterministic assurance plan. Plan only; "
            "no approval or execution."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "candidate_id": _IDENTIFIER,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "candidate_id", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_bundle_compile",
        description=(
            "Submit deterministic bundle compilation for a validated target profile as a "
            "durable asynchronous operation. No target mutation; the compiled plan is "
            "inert until separately signed, approved, and verified."
        ),
        input_schema=_schema(
            {
                "case_id": _IDENTIFIER,
                "candidate_id": _IDENTIFIER,
                "target": _DOCUMENT,
                "expected_version": _EXPECTED_VERSION,
                "idempotency_key": _IDEMPOTENCY_KEY,
            },
            required=("case_id", "candidate_id", "target", "expected_version", "idempotency_key"),
            context=True,
        ),
    ),
    ToolDefinition(
        name="oak_operation_get",
        description="Read one durable operation's state, progress, and result. Read only.",
        input_schema=_schema(
            {"operation_id": _IDENTIFIER},
            required=("operation_id",),
            context=True,
        ),
    ),
)

TOOL_NAMES: frozenset[str] = frozenset(definition.name for definition in TOOL_DEFINITIONS)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_error_document(error: OAKError) -> dict[str, Any]:
    """Map a domain error to the audit-safe shape shared with the REST problem body."""

    message = OPAQUE_NOT_FOUND_DETAIL if error.code in NOT_FOUND_CODES else error.message
    return {"code": error.code, "message": message, "retriable": error.retriable}


def _operation_document(record: Any, *, duplicate: bool = False) -> dict[str, Any]:
    return {
        "operation_id": record.operation_id,
        "workspace_id": record.workspace_id,
        "case_id": record.case_id,
        "kind": record.kind,
        "state": record.state,
        "version": record.version,
        "result": record.result,
        "problem": record.problem,
        "correlation_id": record.correlation_id,
        "attempt_count": record.attempt_count,
        "max_attempts": record.max_attempts,
        "next_attempt_at": record.next_attempt_at,
        "lease_expires_at": record.lease_expires_at,
        "cancel_requested": record.cancel_requested,
        "checkpoint": record.checkpoint,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "completed_at": record.completed_at,
        "duplicate": duplicate,
    }


class MCPToolExecutor:
    """Validate, authorize, and dispatch one tool call onto the control plane."""

    def __init__(
        self,
        control_plane: CommunityControlPlane,
        *,
        local_actor: str,
        local_tenant: str,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._plane = control_plane
        self._local_actor = local_actor
        self._local_tenant = local_tenant
        self._clock = clock
        self._validators = {
            definition.name: validator_for(definition.input_schema)(definition.input_schema)
            for definition in TOOL_DEFINITIONS
        }
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "oak_design_case_create": self._create,
            "oak_design_case_get": self._get,
            "oak_design_case_interpret": self._interpret,
            "oak_questions_list": self._questions,
            "oak_claims_confirm": self._confirm,
            "oak_candidates_generate": self._generate,
            "oak_candidates_list": self._list_candidates,
            "oak_candidate_evaluate": self._evaluate,
            "oak_assurance_plan_create": self._assure,
            "oak_bundle_compile": self._compile,
            "oak_operation_get": self._operation,
        }
        if set(self._handlers) != TOOL_NAMES:
            raise RuntimeError("tool handlers and tool definitions have drifted")

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "inputSchema": definition.input_schema,
            }
            for definition in TOOL_DEFINITIONS
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return an MCP tool result; domain denials become in-band error results."""

        handler = self._handlers.get(name)
        if handler is None:
            # Unknown-tool signal raised before the guarded call, so it can never
            # be confused with an exception raised inside a handler.
            raise KeyError(name)
        self._validate_arguments(name, arguments)
        try:
            document = handler(arguments)
        except OAKError as error:
            return self._error_result(safe_error_document(error))
        except ContractValidationError:
            return self._error_result(
                {
                    "code": "OAK-CONTRACT-INVALID",
                    "message": "input failed canonical contract validation",
                    "retriable": False,
                }
            )
        except Exception:
            # Any other handler failure (including a KeyError/TypeError while
            # assembling a document from persisted state) becomes an in-band
            # OAK-INTERNAL result rather than propagating: a handler KeyError must
            # not be reported to the client as an unknown tool, and no exception
            # may terminate the stdio session.
            return self._error_result(
                {
                    "code": "OAK-INTERNAL",
                    "message": "The request could not be completed safely.",
                    "retriable": False,
                }
            )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(document, ensure_ascii=False, sort_keys=True),
                }
            ],
            "structuredContent": document,
            "isError": False,
        }

    def _validate_arguments(self, name: str, arguments: dict[str, Any]) -> None:
        errors = sorted(
            self._validators[name].iter_errors(arguments),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            reported = tuple(
                {
                    "path": "/" + "/".join(str(part) for part in error.absolute_path),
                    "message": payload_safe_reason(error),
                }
                for error in errors
            )
            raise ToolArgumentError(reported)

    @staticmethod
    def _error_result(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"{document['code']}: {document['message']}"}],
            "structuredContent": document,
            "isError": True,
        }

    def _authority(self, arguments: dict[str, Any]) -> tuple[str, str]:
        requested_actor = str(arguments.get("actor") or self._local_actor)
        requested_tenant = str(arguments.get("tenant_id") or self._local_tenant)
        if requested_tenant != self._local_tenant:
            raise OAKError("OAK-TENANT-MISMATCH", "requested resource was not found")
        if requested_actor != self._local_actor:
            raise OAKError("OAK-ACTOR-DENIED", "local actor is not authorized")
        return requested_actor, requested_tenant

    def _context(
        self,
        arguments: dict[str, Any],
        *,
        expected_version: str | None,
    ) -> CommandContext:
        actor, tenant = self._authority(arguments)
        idempotency_key = str(arguments["idempotency_key"])
        correlation = str(
            arguments.get("correlation_id")
            or "correlation." + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
        )
        return CommandContext(
            actor=actor,
            tenant_id=tenant,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            correlation_id=correlation,
            interface_origin="mcp",
            occurred_at=self._clock(),
        )

    def _create(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=None)
        result = self._plane.create_design_case(
            original_name=str(arguments["original_name"]),
            content=str(arguments["content"]).encode("utf-8"),
            context=context,
        )
        return {"case": result.case, "duplicate": result.duplicate}

    def _get(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _, tenant = self._authority(arguments)
        result = self._plane.get_design_case(str(arguments["case_id"]), tenant_id=tenant)
        return {"case": result.case, "intent": result.intent, "duplicate": False}

    def _interpret(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        result = self._plane.interpret(str(arguments["case_id"]), context)
        return {"case": result.case, "intent": result.intent, "duplicate": result.duplicate}

    def _questions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _, tenant = self._authority(arguments)
        case = self._plane.get_design_case(str(arguments["case_id"]), tenant_id=tenant).case
        return {
            "case_id": str(case["id"]),
            "case_version": str(case["version"]),
            "status": str(case["status"]),
            "questions": list(case["unresolved_questions"]),
        }

    def _confirm(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        answers = arguments["answers"]
        if not isinstance(answers, dict):
            raise OAKError("OAK-CONFIRM-MALFORMED", "answers are malformed")
        result = self._plane.confirm(str(arguments["case_id"]), answers, context)
        return {"case": result.case, "intent": result.intent, "duplicate": result.duplicate}

    def _generate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        submission = self._plane.submit_generate_candidates(str(arguments["case_id"]), context)
        return _operation_document(submission.operation, duplicate=submission.duplicate)

    def _list_candidates(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _, tenant = self._authority(arguments)
        items = self._plane.list_candidates(str(arguments["case_id"]), tenant_id=tenant)
        return {"items": list(items)}

    def _evaluate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        submission = self._plane.submit_evaluate_candidate(
            str(arguments["case_id"]), str(arguments["candidate_id"]), context
        )
        return _operation_document(submission.operation, duplicate=submission.duplicate)

    def _assure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        result = self._plane.create_assurance_plan(
            str(arguments["case_id"]), str(arguments["candidate_id"]), context
        )
        return {
            "case": result.case,
            "assurance_plan": result.assurance_plan,
            "duplicate": result.duplicate,
        }

    def _compile(self, arguments: dict[str, Any]) -> dict[str, Any]:
        context = self._context(arguments, expected_version=str(arguments["expected_version"]))
        target = arguments["target"]
        if not isinstance(target, dict):
            raise OAKError("OAK-PLAN-INPUT", "target profile is malformed")
        submission = self._plane.submit_compile_bundle(
            str(arguments["case_id"]), str(arguments["candidate_id"]), target, context
        )
        return _operation_document(submission.operation, duplicate=submission.duplicate)

    def _operation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        _, tenant = self._authority(arguments)
        record = self._plane.get_operation(str(arguments["operation_id"]), tenant_id=tenant)
        return _operation_document(record)
