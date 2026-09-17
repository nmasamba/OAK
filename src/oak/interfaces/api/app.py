# SPDX-License-Identifier: Apache-2.0
"""FastAPI transport mapping for shared OAK application services."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from oak.application import (
    CommandContext,
    CommunityControlPlane,
    ModelConfigurationService,
    SystemInformationService,
    validate_key_input,
)
from oak.bootstrap import (
    create_model_configuration_service,
    create_persistent_control_plane,
    create_system_information_service,
    read_model_token,
)
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
    ModelCredentialRequest,
    ModelCredentialStatus,
    ModelDiscoveryResponse,
    ModelDiscoverySummary,
    ModelFamily,
    ModelSelectionRequest,
    ModelStatusResponse,
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
MODEL_TOKEN_HEADER = "X-OAK-Model-Token"
ModelTokenHeader = Annotated[
    str | None, Header(alias="X-OAK-Model-Token", min_length=16, max_length=256)
]

# The loopback names the API answers to by construction. `OAK_ALLOWED_HOSTS` may add exact
# hostnames for an acknowledged non-loopback bind; nothing ever disables the check, and
# `*.localhost` names are deliberately not loopback (a page at `attacker.localhost` is
# same-site with a page at `localhost`).
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Routes that store, remove, discover, or select model-provider credentials: loopback `Host`
# only, whatever the allowlist says, and a browser must be same-origin, not merely same-site.
HOST_CHECK_EXEMPT_PATHS = frozenset({"/healthz", "/readyz"})


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


def _require_model_token(
    request: Request,
    presented: Annotated[
        str | None, Header(alias=MODEL_TOKEN_HEADER, min_length=16, max_length=256)
    ] = None,
) -> None:
    """Refuse before the body is read.

    FastAPI resolves dependencies before it parses or validates a request body, so a caller
    without the capability token never has its body examined and is never told what was
    wrong with a request it was not entitled to make.

    The header is declared optional here on purpose: a missing token is an authorisation
    failure, and answering it with the stable `OAK-MODEL-TOKEN-REQUIRED` is more useful than
    a generic "field required". The published document marks it required, which is the
    truthful description of the contract; `create_app` corrects it there.
    """

    provider: Callable[[], str | None] = request.app.state.model_token_provider
    verify_model_token(presented, provider())


ModelTokenDependency = Annotated[None, Depends(_require_model_token)]


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


def _hostname(authority: str) -> str | None:
    """Return the lower-cased hostname of a `Host` or `Origin` authority, port removed."""

    value = authority.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] or None if end != -1 else None
    if value.count(":") > 1:
        return None
    if ":" in value:
        value = value.rsplit(":", 1)[0]
    return value or None


def _origin_hostname(origin: str) -> str | None:
    parsed = urllib.parse.urlsplit(origin.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return _hostname(parsed.netloc)


def is_credential_route(path: str) -> bool:
    """Whether a path is part of the model-configuration surface.

    Every `/v1/models` path qualifies, reads included: the status resource names the store
    locations and the salted fingerprint of each stored key, which is not something a page
    on another origin should be able to read even though it cannot change anything.
    """

    return path == "/v1/models" or path.startswith("/v1/models/")


def parse_allowed_hosts(value: str) -> frozenset[str]:
    """Split `OAK_ALLOWED_HOSTS`: exact lower-cased hostnames, no wildcards, no ports."""

    hosts: set[str] = set()
    for item in value.split(","):
        candidate = item.strip().lower()
        if not candidate or "*" in candidate:
            continue
        hostname = _hostname(candidate)
        if hostname is not None:
            hosts.add(hostname)
    return frozenset(hosts)


class _LoopbackGuardMiddleware:
    """Refuse requests a same-machine browser page or a rebound name could forge.

    The API has no authentication; the local actor is a header claim. What keeps a page
    served from any other origin from driving it is that browsers always send `Origin` and
    `Sec-Fetch-Site` on cross-site requests and cannot forge `Host`. So: the `Host` must be a
    loopback name (or an exact `OAK_ALLOWED_HOSTS` entry), an `Origin`, when present, must be
    loopback too and never `null`, and fetch metadata must say `same-origin` or `none`. The
    checks run before routing, add no parameter to the OpenAPI contract, and never echo the
    offending header value.
    """

    def __init__(self, app: ASGIApp, *, allowed_hosts: frozenset[str]) -> None:
        self._app = app
        self._allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        problem = self._refusal(scope.get("path", ""), headers)
        if problem is not None:
            await _problem_response(problem)(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _refusal(self, path: str, headers: dict[str, str]) -> Problem | None:
        credential_route = is_credential_route(path)
        permitted = LOOPBACK_HOSTS | self._allowed_hosts
        if path not in HOST_CHECK_EXEMPT_PATHS:
            host = headers.get("host")
            hostname = _hostname(host) if host else None
            if hostname is None or hostname not in permitted:
                return self._host_problem()
            if credential_route and hostname not in LOOPBACK_HOSTS:
                return self._host_problem()
        origin = headers.get("origin")
        if origin is not None:
            origin_hostname = _origin_hostname(origin)
            if origin_hostname is None or origin_hostname not in permitted:
                return self._origin_problem()
        site = headers.get("sec-fetch-site")
        if site is not None and site.strip().lower() not in {"same-origin", "none"}:
            return self._origin_problem()
        same_origin = (site or "").strip().lower() == "same-origin"
        if credential_route and origin is not None and not same_origin:
            return self._origin_problem()
        return None

    @staticmethod
    def _host_problem() -> Problem:
        return Problem(
            title="Host not permitted",
            status=400,
            code="OAK-HOST-DENIED",
            detail=(
                "The request named a host this local API does not answer to. Use a loopback "
                "name, or list the host in OAK_ALLOWED_HOSTS."
            ),
        )

    @staticmethod
    def _origin_problem() -> Problem:
        return Problem(
            title="Cross-origin request refused",
            status=403,
            code="OAK-ORIGIN-DENIED",
            detail=(
                "Requests from another origin are refused; this local API serves its own "
                "loopback workspace only."
            ),
        )


class InterpreterMode(StrEnum):
    AUTO = "auto"
    MODEL = "model"
    DETERMINISTIC = "deterministic"


InterpreterQuery = Annotated[
    InterpreterMode | None,
    Query(
        description=(
            "auto (the default) uses the configured model for a prose brief and the "
            "deterministic interpreter otherwise; model requires a configured model and the "
            "X-OAK-Model-Token header; deterministic never calls a provider."
        ),
    ),
]


def verify_model_token(presented: str | None, expected: str | None) -> None:
    """Refuse unless the presented capability token equals the one this process minted."""

    if not expected or presented is None:
        raise OAKError(
            "OAK-MODEL-TOKEN-REQUIRED",
            "this operation requires the X-OAK-Model-Token header; run `oak models token` "
            "to read the token this server minted",
        )
    if not secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise OAKError(
            "OAK-MODEL-TOKEN-REQUIRED",
            "the X-OAK-Model-Token header does not match the token this server minted; run "
            "`oak models token` to read the current one",
        )


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
    if error.code in {"OAK-ACTOR-DENIED", "OAK-ORIGIN-DENIED", "OAK-MODEL-TOKEN-REQUIRED"}:
        return 403
    if error.code == "OAK-HOST-DENIED":
        return 400
    if error.code == "OAK-MODEL-RATE-LIMITED":
        return 429
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
    allowed_hosts: frozenset[str] | None = None,
    model_token: str | Callable[[], str | None] | None = None,
    model_configuration: Callable[[], ModelConfigurationService] | None = None,
) -> FastAPI:
    """Build the API.

    ``allowed_hosts`` defaults to the exact names in ``OAK_ALLOWED_HOSTS`` (loopback names are
    always accepted). ``model_token`` is the capability token guarding model configuration:
    a fixed string for tests, or a callable read per request; by default the token file the
    serving process minted is read, so a server restart rotates it without a reload.
    ``model_configuration`` builds the service the `/v1/models` routes act on; it is called
    per request so a key stored from the CLI is visible to the API without a restart.
    """

    application_service = service or create_system_information_service()
    persistent_service = control_plane
    information = application_service.get_information()
    permitted_hosts = (
        allowed_hosts
        if allowed_hosts is not None
        else parse_allowed_hosts(os.getenv("OAK_ALLOWED_HOSTS", ""))
    )
    if model_token is None:
        token_provider: Callable[[], str | None] = read_model_token
    elif isinstance(model_token, str):
        fixed_token = model_token

        def token_provider() -> str | None:
            return fixed_token

    else:
        token_provider = model_token
    model_configuration_factory = model_configuration or create_model_configuration_service
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
    # Added last so it runs first: nothing is buffered or routed for a refused host/origin.
    api.add_middleware(_LoopbackGuardMiddleware, allowed_hosts=permitted_hosts)

    api.state.model_token_provider = token_provider

    generated_openapi = api.openapi

    def openapi() -> dict[str, Any]:
        """The generated document, corrected on one point.

        FastAPI derives `required` from the dependency's signature, where the token is
        optional so that a missing one gets a stable refusal rather than a validation error.
        On the model routes the server refuses every request without it, so leaving the
        document saying "optional" would describe a contract the server does not honour and
        would give generated clients an optional argument that never works.
        """

        document = generated_openapi()
        for route, operations in document.get("paths", {}).items():
            if not is_credential_route(route):
                continue
            for operation in operations.values():
                for parameter in operation.get("parameters", []):
                    if parameter.get("name") == MODEL_TOKEN_HEADER:
                        parameter["required"] = True
        api.openapi_schema = document
        return document

    api.openapi = openapi  # type: ignore[method-assign]

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
        interpreter: InterpreterQuery = None,
        model_token: ModelTokenHeader = None,
    ) -> DesignCaseResponse:
        context = command_context(
            request,
            auth,
            idempotency_key=idempotency_key,
            expected_version=_expected_version(expected),
            correlation_id=correlation_id,
        )
        # Resolve first so the capability token is demanded exactly when the operator's
        # stored credential would be spent, and nothing is committed without it.
        requested = (interpreter or InterpreterMode.AUTO).value
        mode = plane().resolve_interpreter(
            case_id, tenant_id=context.tenant_id, interpreter=requested
        )
        if mode == "model":
            if requested == InterpreterMode.AUTO.value and model_token is None:
                # `auto` is what a client written before the model path existed sends. It
                # must keep meaning what it meant then rather than becoming a 403 the moment
                # somebody configures a model, so with no token it stays deterministic.
                # Asking for the model by name still requires the token.
                mode = InterpreterMode.DETERMINISTIC.value
            else:
                verify_model_token(model_token, token_provider())
        result = plane().interpret(case_id, context, interpreter=mode)
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

    def configuration() -> ModelConfigurationService:
        return model_configuration_factory()

    def _no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    def _status_document(service: ModelConfigurationService) -> ModelStatusResponse:
        status = service.status()
        discovery = {
            family: ModelDiscoverySummary(
                fetched_at=str(summary["fetched_at"]),
                source=str(summary["source"]),  # type: ignore[arg-type]
                recommended=summary["recommended"],
                model_count=int(summary["model_count"]),
                stale=bool(summary["stale"]),
            )
            for family, summary in status["discovery"].items()
        }
        return ModelStatusResponse(
            configured=bool(status["configured"]),
            selection=status["selection"],
            provider_policy=str(status["provider_policy"]),
            families=tuple(ModelFamily(**family) for family in service.families()),
            credentials=tuple(
                # The domain says `None` for "no backend holds this"; the wire contract says
                # `"none"`, the spelling `model-configuration.schema.json` already uses, which
                # keeps the response free of a nullable enum.
                ModelCredentialStatus(**{**credential, "source": credential["source"] or "none"})
                for credential in status["credentials"].values()
            ),
            discovery=discovery,
            stores=status["stores"],
        )

    @api.get("/v1/models", response_model=ModelStatusResponse, tags=["models"])
    def get_models(
        response: Response,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> ModelStatusResponse:
        del auth, _token
        _no_store(response)
        return _status_document(configuration())

    @api.put(
        "/v1/models/credentials/{family}",
        status_code=204,
        response_class=Response,
        tags=["models"],
    )
    def put_model_credential(
        family: str,
        body: ModelCredentialRequest,
        response: Response,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> Response:
        del auth, _token
        service = configuration()
        secret = validate_key_input(body.api_key)
        try:
            service.set_key(family, secret, source="keychain")
        except OAKError as error:
            if not error.code.startswith("OAK-MODEL-KEYCHAIN-"):
                raise
            # Never a silent downgrade: the store the key landed in is in the status the
            # caller reads back, and the workspace shows it.
            service.set_key(family, secret, source="file")
        headers = {"Cache-Control": "no-store"}
        del secret
        return Response(status_code=204, headers=headers)

    @api.delete(
        "/v1/models/credentials/{family}",
        status_code=204,
        response_class=Response,
        tags=["models"],
    )
    def delete_model_credential(
        family: str,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> Response:
        del auth, _token
        configuration().remove_key(family)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @api.put("/v1/models/selection", response_model=ModelStatusResponse, tags=["models"])
    def put_model_selection(
        body: ModelSelectionRequest,
        response: Response,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> ModelStatusResponse:
        del auth, _token
        service = configuration()
        service.select(
            body.family,
            body.model_id,
            provider_route=body.provider_route,
            default_interpreter=body.default_interpreter,
            acknowledge_data_use=body.acknowledge_data_use,
        )
        _no_store(response)
        return _status_document(service)

    @api.delete("/v1/models/selection", response_model=ModelStatusResponse, tags=["models"])
    def clear_model_selection(
        response: Response,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> ModelStatusResponse:
        del auth, _token
        service = configuration()
        service.clear_selection()
        _no_store(response)
        return _status_document(service)

    @api.post(
        "/v1/models/{family}:discover",
        response_model=ModelDiscoveryResponse,
        tags=["models"],
    )
    def discover_models_for_family(
        family: str,
        response: Response,
        auth: AuthorityDependency,
        _token: ModelTokenDependency = None,
    ) -> ModelDiscoveryResponse:
        """Contact that family's catalogue. The only route here that reaches a network."""

        del auth, _token
        snapshot = configuration().discover(family)
        _no_store(response)
        return ModelDiscoveryResponse(family=family, discovery=snapshot)

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
