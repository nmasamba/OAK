# SPDX-License-Identifier: Apache-2.0
"""Typed HTTP request and response mapping; no domain policy lives here."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(StrictResponse):
    status: Literal["ok"] = "ok"


class ReadinessResponse(StrictResponse):
    status: Literal["ready", "not_ready"]


class VersionResponse(StrictResponse):
    name: str
    version: str
    commit: str
    schema_versions: tuple[str, ...]


class FieldProblem(StrictResponse):
    path: str
    message: str


class Problem(StrictResponse):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str
    correlation_id: str | None = None
    retriable: bool = False
    errors: tuple[FieldProblem, ...] = Field(default_factory=tuple)


class CreateDesignCaseRequest(StrictResponse):
    original_name: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=262_144)


class ConfirmClaimsRequest(StrictResponse):
    answers: dict[str, Any]


class EvaluateCandidateRequest(StrictResponse):
    case_id: str = Field(min_length=3, max_length=160)


class SelectCandidateRequest(StrictResponse):
    candidate_id: str = Field(min_length=3, max_length=160)
    rationale: str = Field(min_length=1, max_length=12_000)


class AssurancePlanRequest(StrictResponse):
    candidate_id: str = Field(min_length=3, max_length=160)


class CompileBundleRequest(StrictResponse):
    candidate_id: str = Field(min_length=3, max_length=160)
    target: dict[str, Any]


class DesignCaseResponse(StrictResponse):
    case: dict[str, Any]
    intent: dict[str, Any] | None = None
    duplicate: bool


class CandidateListResponse(StrictResponse):
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None = None


class ArtifactListResponse(StrictResponse):
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None = None


class SelectionResponse(StrictResponse):
    case: dict[str, Any]
    decision: dict[str, Any]
    duplicate: bool


class AssuranceResponse(StrictResponse):
    case: dict[str, Any]
    assurance_plan: dict[str, Any]
    duplicate: bool


class OperationResponse(StrictResponse):
    operation_id: str
    workspace_id: str
    case_id: str
    kind: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelling", "cancelled"]
    version: int
    result: dict[str, Any] | None
    problem: dict[str, Any] | None
    correlation_id: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: str
    lease_expires_at: str | None
    cancel_requested: bool
    checkpoint: dict[str, Any] | None
    created_at: str
    updated_at: str
    completed_at: str | None
    duplicate: bool = False


class ExportObject(StrictResponse):
    digest: str = Field(pattern=r"^sha256:[A-Fa-f0-9]{64}$")
    content_base64: str = Field(min_length=1, max_length=11_184_812)


class CanonicalExport(StrictResponse):
    export_version: Literal["0.1.0"]
    manifest: dict[str, Any]
    objects: tuple[ExportObject, ...] = Field(max_length=10_000)


class OutboxLagResponse(StrictResponse):
    pending_events: int
    oldest_pending_at: str | None
    latest_sequence: int
    indexed_through: int
    sequence_lag: int
