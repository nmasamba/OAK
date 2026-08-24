# SPDX-License-Identifier: Apache-2.0
"""FastAPI transport mapping for shared OAK application services."""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from oak.application import CommandContext, CommunityControlPlane, SystemInformationService
from oak.bootstrap import create_persistent_control_plane, create_system_information_service
from oak.domain import OAKError
from oak.interfaces.api.models import (
    ArtifactListResponse,
    AssurancePlanRequest,
    AssuranceResponse,
    AuditTrailResponse,
    CandidateListResponse,
    CanonicalExport,
    CompileBundleRequest,
    ConfirmClaimsRequest,
    CreateDesignCaseRequest,
    DesignCaseListResponse,
    DesignCaseResponse,
    EvaluateCandidateRequest,
    FieldProblem,
    HealthResponse,
    OperationResponse,
    OutboxLagResponse,
    Problem,
    ReadinessResponse,
    SelectCandidateRequest,
    SelectionResponse,
    VersionResponse,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"
MAXIMUM_REQUEST_BYTES = 94_371_840
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=240)]
ExpectedVersionHeader = Annotated[str, Header(alias="If-Match", min_length=3, max_length=90)]
CorrelationHeader = Annotated[
    str | None, Header(alias="X-Correlation-ID", min_length=8, max_length=160)
]


@dataclass(frozen=True, slots=True)
class _Authority:
    actor: str
    tenant_id: str


def _local_authority(
    actor: Annotated[str | None, Header(alias="X-OAK-Actor")] = None,
    tenant_id: Annotated[str | None, Header(alias="X-OAK-Tenant")] = None,
) -> _Authority:
    local_actor = os.getenv("OAK_LOCAL_ACTOR", "local-user")
    local_tenant = os.getenv("OAK_LOCAL_TENANT", "local")
    requested_actor = actor or local_actor
    requested_tenant = tenant_id or local_tenant
    if requested_tenant != local_tenant:
        raise OAKError("OAK-TENANT-MISMATCH", "requested resource was not found")
    if requested_actor != local_actor:
        raise OAKError("OAK-ACTOR-DENIED", "local actor is not authorized")
    return _Authority(actor=requested_actor, tenant_id=requested_tenant)


AuthorityDependency = Annotated[_Authority, Depends(_local_authority)]


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )


class _BoundedRequestMiddleware:
    """Buffer at most the documented request limit, including chunked bodies."""

    def __init__(self, app: ASGIApp, *, maximum_bytes: int) -> None:
        self._app = app
        self._maximum_bytes = maximum_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self._maximum_bytes:
                response = _problem_response(
                    Problem(
                        title="Request too large",
                        status=413,
                        code="OAK-REQUEST-SIZE",
                        detail="The request exceeds the local API size limit.",
                    )
                )
                await response(scope, receive, send)
                return
            more_body = bool(message.get("more_body", False))
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self._app(scope, replay, send)


def _field_problems(errors: Sequence[dict[str, Any]]) -> tuple[FieldProblem, ...]:
    result: list[FieldProblem] = []
    for error in errors:
        location = "/" + "/".join(str(part) for part in error.get("loc", ()))
        result.append(FieldProblem(path=location, message=str(error.get("msg", "invalid value"))))
    return tuple(result)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _etag(version: str) -> str:
    return f'"{version}"'


def _expected_version(value: str) -> str:
    """Parse an `If-Match` precondition into a case version.

    A malformed header is deliberately *not* `OAK-EXPECTED-VERSION`. That code maps to
    409 and to CLI exit 4, both of which mean "re-read the resource and retry" — and a
    client that sent a weak or empty entity tag will never succeed by retrying, so a
    retry loop keyed on that signal spins forever. An unusable precondition is a
    client-input error, not a concurrency conflict.
    """

    normalized = value.strip()
    if normalized.startswith("W/"):
        raise OAKError("OAK-PRECONDITION-INVALID", "weak entity tags are not accepted")
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        normalized = normalized[1:-1]
    if not normalized:
        raise OAKError("OAK-PRECONDITION-INVALID", "expected version is required")
    return normalized


def _cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode()).decode().rstrip("=")


def _cursor_offset(value: str | None) -> int:
    if value is None:
        return 0
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("ascii")
        prefix, offset = decoded.split(":", 1)
        if prefix != "v1":
            raise ValueError("unknown cursor version")
        parsed = int(offset)
    except (ValueError, UnicodeError) as error:
        raise OAKError("OAK-CURSOR-INVALID", "pagination cursor is invalid") from error
    if parsed < 0:
        raise OAKError("OAK-CURSOR-INVALID", "pagination cursor is invalid")
    return parsed


def _operation_response(record: Any, *, duplicate: bool = False) -> OperationResponse:
    return OperationResponse(
        operation_id=record.operation_id,
        workspace_id=record.workspace_id,
        case_id=record.case_id,
        kind=record.kind,
        state=record.state,
        version=record.version,
        result=record.result,
        problem=record.problem,
        correlation_id=record.correlation_id,
        attempt_count=record.attempt_count,
        max_attempts=record.max_attempts,
        next_attempt_at=record.next_attempt_at,
        lease_expires_at=record.lease_expires_at,
        cancel_requested=record.cancel_requested,
        checkpoint=record.checkpoint,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        duplicate=duplicate,
    )


def _error_status(error: OAKError) -> int:
    if error.code == "OAK-ACTOR-DENIED":
        return 403
    if error.code in {
        "OAK-CASE-NOT-FOUND",
        "OAK-CANDIDATE-NOT-FOUND",
        "OAK-OPERATION-NOT-FOUND",
        "OAK-WORKSPACE-NOT-FOUND",
        "OAK-ARTIFACT-NOT-FOUND",
        "OAK-TENANT-MISMATCH",
    }:
        return 404
    if error.code in {
        "OAK-EXPECTED-VERSION",
        "OAK-IDEMPOTENCY-CONFLICT",
        "OAK-CASE-CONFLICT",
        "OAK-OPERATION-CONFLICT",
    } or error.code.endswith("-STATE"):
        return 409
    if error.code.endswith("-SIZE"):
        return 413
    return 422


def create_app(
    service: SystemInformationService | None = None,
    control_plane: CommunityControlPlane | None = None,
    *,
    clock: Callable[[], str] = _utc_now,
) -> FastAPI:
    application_service = service or create_system_information_service()
    persistent_service = control_plane
    information = application_service.get_information()
    api = FastAPI(
        title="OAK Community API",
        summary="Local persistent Community control plane",
        description=(
            "A local, non-production design and planning control plane. Compilation produces "
            "draft artifacts only; this API has no approval, runner dispatch, or target "
            "mutation path."
        ),
        version=information.version,
        openapi_version="3.1.0",
    )
    api.add_middleware(_BoundedRequestMiddleware, maximum_bytes=MAXIMUM_REQUEST_BYTES)

    def plane() -> CommunityControlPlane:
        nonlocal persistent_service
        if persistent_service is None:
            persistent_service = create_persistent_control_plane()
        return persistent_service

    def command_context(
        request: Request,
        auth: _Authority,
        *,
        idempotency_key: str,
        expected_version: str | None,
        correlation_id: str | None,
    ) -> CommandContext:
        correlation = correlation_id or (
            "correlation." + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
        )
        request.state.correlation_id = correlation
        return CommandContext(
            actor=auth.actor,
            tenant_id=auth.tenant_id,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            correlation_id=correlation,
            interface_origin="api",
            occurred_at=clock(),
        )

    @api.exception_handler(OAKError)
    async def oak_error_handler(request: Request, error: OAKError) -> JSONResponse:
        status = _error_status(error)
        detail = "The requested resource was not found." if status == 404 else error.message
        return _problem_response(
            Problem(
                title="OAK request failed",
                status=status,
                code=error.code,
                detail=detail,
                correlation_id=getattr(request.state, "correlation_id", None),
                retriable=error.retriable,
            )
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Request validation failed",
                status=422,
                code="OAK-REQUEST-INVALID",
                detail="The request did not match the API contract.",
                correlation_id=getattr(request.state, "correlation_id", None),
                errors=_field_problems(error.errors()),
            )
        )

    @api.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "OAK-NOT-FOUND" if error.status_code == 404 else "OAK-HTTP-ERROR"
        detail = (
            "The requested resource was not found."
            if error.status_code == 404
            else "Request failed."
        )
        return _problem_response(
            Problem(
                title="Not found" if error.status_code == 404 else "HTTP request failed",
                status=error.status_code,
                code=code,
                detail=detail,
                correlation_id=getattr(request.state, "correlation_id", None),
            )
        )

    @api.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _error: Exception) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Internal error",
                status=500,
                code="OAK-INTERNAL",
                detail="The request could not be completed safely.",
                correlation_id=getattr(request.state, "correlation_id", None),
            )
        )

    @api.get("/healthz", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse()

    @api.get("/readyz", response_model=ReadinessResponse, tags=["system"])
    def readiness() -> ReadinessResponse:
        result = application_service.get_readiness()
        if result.status != "ready":
            raise HTTPException(status_code=503, detail="not ready")
        return ReadinessResponse(status=result.status)

    @api.get("/version", response_model=VersionResponse, tags=["system"])
    def version() -> VersionResponse:
        result = application_service.get_information()
        return VersionResponse(
            name=result.name,
            version=result.version,
            commit=result.commit,
            schema_versions=result.schema_versions,
        )

    @api.post(
        "/v1/design-cases",
        response_model=DesignCaseResponse,
        status_code=201,
        tags=["design-cases"],
    )
    def create_design_case(
        body: CreateDesignCaseRequest,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> DesignCaseResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=None,
            correlation_id=correlation_id,
        )
        result = plane().create_design_case(
            original_name=body.original_name,
            content=body.content.encode("utf-8"),
            context=context,
        )
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return DesignCaseResponse(case=result.case, duplicate=result.duplicate)

    @api.get(
        "/v1/design-cases",
        response_model=DesignCaseListResponse,
        tags=["design-cases"],
    )
    def list_design_cases(
        auth: AuthorityDependency,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> DesignCaseListResponse:
        items = plane().list_design_cases(tenant_id=auth.tenant_id)
        offset = _cursor_offset(cursor)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        return DesignCaseListResponse(
            items=page,
            next_cursor=_cursor(next_offset) if next_offset < len(items) else None,
        )

    @api.get(
        "/v1/design-cases/{case_id}",
        response_model=DesignCaseResponse,
        tags=["design-cases"],
    )
    def get_design_case(
        case_id: str,
        response: Response,
        auth: AuthorityDependency,
    ) -> DesignCaseResponse:
        result = plane().get_design_case(case_id, tenant_id=auth.tenant_id)
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return DesignCaseResponse(
            case=result.case,
            intent=result.intent,
            duplicate=False,
        )

    @api.post(
        "/v1/design-cases/{case_id}:interpret",
        response_model=DesignCaseResponse,
        tags=["design-cases"],
    )
    def interpret_design_case(
        case_id: str,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> DesignCaseResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().interpret(case_id, context)
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return DesignCaseResponse(
            case=result.case,
            intent=result.intent,
            duplicate=result.duplicate,
        )

    @api.post(
        "/v1/design-cases/{case_id}:confirm",
        response_model=DesignCaseResponse,
        tags=["design-cases"],
    )
    def confirm_design_case(
        case_id: str,
        body: ConfirmClaimsRequest,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> DesignCaseResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().confirm(case_id, body.answers, context)
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return DesignCaseResponse(
            case=result.case,
            intent=result.intent,
            duplicate=result.duplicate,
        )

    @api.post(
        "/v1/design-cases/{case_id}:generate-candidates",
        response_model=OperationResponse,
        status_code=202,
        tags=["operations"],
    )
    def generate_candidates(
        case_id: str,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> OperationResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().submit_generate_candidates(case_id, context)
        return _operation_response(result.operation, duplicate=result.duplicate)

    @api.get(
        "/v1/design-cases/{case_id}/candidates",
        response_model=CandidateListResponse,
        tags=["design-cases"],
    )
    def list_candidates(
        case_id: str,
        auth: AuthorityDependency,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> CandidateListResponse:
        items = plane().list_candidates(case_id, tenant_id=auth.tenant_id)
        offset = _cursor_offset(cursor)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        return CandidateListResponse(
            items=page,
            next_cursor=_cursor(next_offset) if next_offset < len(items) else None,
        )

    @api.post(
        "/v1/candidates/{candidate_id}:evaluate",
        response_model=OperationResponse,
        status_code=202,
        tags=["operations"],
    )
    def evaluate_candidate(
        candidate_id: str,
        body: EvaluateCandidateRequest,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> OperationResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().submit_evaluate_candidate(body.case_id, candidate_id, context)
        return _operation_response(result.operation, duplicate=result.duplicate)

    @api.post(
        "/v1/design-cases/{case_id}:select-candidate",
        response_model=SelectionResponse,
        tags=["design-cases"],
    )
    def select_candidate(
        case_id: str,
        body: SelectCandidateRequest,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> SelectionResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().select_candidate(
            case_id,
            body.candidate_id,
            body.rationale,
            context,
        )
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return SelectionResponse(
            case=result.case,
            decision=result.decision,
            duplicate=result.duplicate,
        )

    @api.post(
        "/v1/design-cases/{case_id}:create-assurance-plan",
        response_model=AssuranceResponse,
        tags=["design-cases"],
    )
    def create_assurance_plan_endpoint(
        case_id: str,
        body: AssurancePlanRequest,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> AssuranceResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().create_assurance_plan(case_id, body.candidate_id, context)
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return AssuranceResponse(
            case=result.case,
            assurance_plan=result.assurance_plan,
            duplicate=result.duplicate,
        )

    @api.post(
        "/v1/design-cases/{case_id}:compile",
        response_model=OperationResponse,
        status_code=202,
        tags=["operations"],
    )
    def compile_bundle(
        case_id: str,
        body: CompileBundleRequest,
        request: Request,
        idempotency_key: IdempotencyHeader,
        expected: ExpectedVersionHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> OperationResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        result = plane().submit_compile_bundle(
            case_id,
            body.candidate_id,
            body.target,
            context,
        )
        return _operation_response(result.operation, duplicate=result.duplicate)

    @api.get(
        "/v1/operations/{operation_id}",
        response_model=OperationResponse,
        tags=["operations"],
    )
    def get_operation(
        operation_id: str,
        auth: AuthorityDependency,
    ) -> OperationResponse:
        return _operation_response(plane().get_operation(operation_id, tenant_id=auth.tenant_id))

    @api.get(
        "/v1/system/outbox-lag",
        response_model=OutboxLagResponse,
        tags=["system"],
    )
    def outbox_lag(auth: AuthorityDependency) -> OutboxLagResponse:
        lag = plane().outbox_lag(tenant_id=auth.tenant_id)
        return OutboxLagResponse(
            pending_events=lag.pending_events,
            oldest_pending_at=lag.oldest_pending_at,
            latest_sequence=lag.latest_sequence,
            indexed_through=lag.indexed_through,
            sequence_lag=lag.sequence_lag,
        )

    @api.post(
        "/v1/operations/{operation_id}:cancel",
        response_model=OperationResponse,
        tags=["operations"],
    )
    def cancel_operation(
        operation_id: str,
        request: Request,
        idempotency_key: IdempotencyHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> OperationResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=None,
            correlation_id=correlation_id,
        )
        return _operation_response(plane().cancel_operation(operation_id, context=context))

    @api.get(
        "/v1/design-cases/{case_id}/audit",
        response_model=AuditTrailResponse,
        tags=["design-cases"],
    )
    def list_audit_events(
        case_id: str,
        auth: AuthorityDependency,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> AuditTrailResponse:
        items = plane().list_audit_events(case_id, tenant_id=auth.tenant_id)
        offset = _cursor_offset(cursor)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        return AuditTrailResponse(
            items=page,
            next_cursor=_cursor(next_offset) if next_offset < len(items) else None,
        )

    @api.get(
        "/v1/design-cases/{case_id}/artifacts",
        response_model=ArtifactListResponse,
        tags=["artifacts"],
    )
    def list_artifacts(
        case_id: str,
        auth: AuthorityDependency,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ArtifactListResponse:
        items = plane().list_artifacts(case_id, tenant_id=auth.tenant_id)
        offset = _cursor_offset(cursor)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        return ArtifactListResponse(
            items=page,
            next_cursor=_cursor(next_offset) if next_offset < len(items) else None,
        )

    @api.get(
        "/v1/design-cases/{case_id}/artifacts/{artifact_id:path}",
        tags=["artifacts"],
        responses={200: {"content": {"application/octet-stream": {}}}},
    )
    def get_artifact(
        case_id: str,
        artifact_id: str,
        version: Annotated[str, Query(min_length=1, max_length=80)],
        digest: Annotated[str, Query(pattern=r"^sha256:[A-Fa-f0-9]{64}$")],
        auth: AuthorityDependency,
    ) -> Response:
        artifact = plane().read_artifact(
            case_id,
            tenant_id=auth.tenant_id,
            artifact_id=artifact_id,
            version=version,
            digest=digest,
        )
        return Response(
            content=artifact.content,
            media_type=artifact.reference.media_type,
            headers={
                "ETag": f'"{artifact.reference.digest}"',
                "X-OAK-Artifact-Digest": artifact.reference.digest,
                "X-Content-Type-Options": "nosniff",
            },
        )

    @api.get(
        "/v1/design-cases/{case_id}/export",
        response_model=CanonicalExport,
        tags=["artifacts"],
    )
    def export_design_case(
        case_id: str,
        auth: AuthorityDependency,
    ) -> CanonicalExport:
        return CanonicalExport.model_validate(
            plane().export_design_case(case_id, tenant_id=auth.tenant_id)
        )

    @api.post(
        "/v1/design-cases:import",
        response_model=DesignCaseResponse,
        status_code=201,
        tags=["artifacts"],
    )
    def import_design_case(
        body: CanonicalExport,
        response: Response,
        request: Request,
        idempotency_key: IdempotencyHeader,
        auth: AuthorityDependency,
        correlation_id: CorrelationHeader = None,
    ) -> DesignCaseResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=None,
            correlation_id=correlation_id,
        )
        result = plane().import_design_case(body.model_dump(mode="json"), context=context)
        response.headers["ETag"] = _etag(str(result.case["version"]))
        return DesignCaseResponse(
            case=result.case,
            intent=result.intent,
            duplicate=result.duplicate,
        )

    return api


app = create_app()
