# SPDX-License-Identifier: Apache-2.0
"""FastAPI mapping for shared read-only application queries."""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from oak.application import SystemInformationService
from oak.bootstrap import create_system_information_service
from oak.domain import OAKError
from oak.interfaces.api.models import (
    FieldProblem,
    HealthResponse,
    Problem,
    ReadinessResponse,
    VersionResponse,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _field_problems(errors: Sequence[dict[str, Any]]) -> tuple[FieldProblem, ...]:
    result: list[FieldProblem] = []
    for error in errors:
        location = "/" + "/".join(str(part) for part in error.get("loc", ()))
        result.append(FieldProblem(path=location, message=str(error.get("msg", "invalid value"))))
    return tuple(result)


def create_app(service: SystemInformationService | None = None) -> FastAPI:
    application_service = service or create_system_information_service()
    information = application_service.get_information()
    api = FastAPI(
        title="OAK Community API",
        summary="Read-only Community serving harness",
        description=(
            "A non-production control-plane skeleton. It exposes process metadata only and has "
            "no target mutation path."
        ),
        version=information.version,
        openapi_version="3.1.0",
    )

    @api.exception_handler(OAKError)
    async def oak_error_handler(_request: Request, error: OAKError) -> JSONResponse:
        return _problem_response(
            Problem(
                title="OAK request failed",
                status=400,
                code=error.code,
                detail=error.message,
                retriable=error.retriable,
            )
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Request validation failed",
                status=422,
                code="OAK-REQUEST-INVALID",
                detail="The request did not match the API contract.",
                errors=_field_problems(error.errors()),
            )
        )

    @api.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, error: StarletteHTTPException) -> JSONResponse:
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
            )
        )

    @api.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _error: Exception) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Internal error",
                status=500,
                code="OAK-INTERNAL",
                detail="The request could not be completed safely.",
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

    return api


app = create_app()
