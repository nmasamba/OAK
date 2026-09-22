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


class DesignCaseListResponse(StrictResponse):
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None = None


class AuditTrailResponse(StrictResponse):
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None = None


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


class ModelCredentialRequest(StrictResponse):
    """The one request body in the API that carries a secret.

    ``api_key`` is ``writeOnly`` and rendered as a password field, and the model carries no
    example, so the value cannot appear in the OpenAPI document, in generated clients, or in
    documentation rendered from either. Validation failures on this field are answered with a
    fixed message rather than the usual field echo.
    """

    api_key: str = Field(
        min_length=16,
        max_length=512,
        json_schema_extra={"writeOnly": True, "format": "password"},
    )


class ModelSelectionRequest(StrictResponse):
    """Pin a model for one family: the Online AI pair for `huggingface`, the Local AI model
    for `local`. Clearing it returns that mode to the preferred model."""

    family: str = Field(min_length=2, max_length=40)
    model_id: str = Field(min_length=1, max_length=256)
    provider_route: str | None = Field(default=None, max_length=64)


class ModelCredentialStatus(StrictResponse):
    """A stored credential's backend, fingerprint and the provider's verdict — never its value.

    ``verification`` is what the provider last said about the credential, with the time it
    said it and whether that is now stale; ``null`` until the credential has been checked.
    """

    family: str
    configured: bool
    source: Literal["keychain", "file", "env", "none"]
    fingerprint: str | None = None
    length: int | None = None
    verification: dict[str, Any] | None = None


class ModelFamily(StrictResponse):
    family: str
    display_name: str
    licence_class: str
    credential_required: bool
    environment_variable: str | None
    key_hint: str
    data_use_note: str
    token_help_url: str | None
    default: bool


class ModelDiscoverySummary(StrictResponse):
    fetched_at: str
    source: Literal["live", "pinned"]
    recommended: str | None
    model_count: int
    stale: bool


class ModelStatusResponse(StrictResponse):
    """Everything the workspace needs to render the model settings, and no credential.

    ``modes`` says which of deterministic, online and local can run now and why not
    otherwise; ``selections`` holds the pair pinned per family, or null for the preferred one.
    """

    modes: dict[str, Any]
    selections: dict[str, Any]
    provider_policy: str
    families: tuple[ModelFamily, ...]
    credentials: tuple[ModelCredentialStatus, ...]
    discovery: dict[str, ModelDiscoverySummary]
    stores: dict[str, Any]


class ModelDiscoveryResponse(StrictResponse):
    family: str
    discovery: dict[str, Any]


class ModelCatalogueResponse(StrictResponse):
    """The stored catalogue snapshot for one family — what `discover` last recorded — or null.

    Read from local state only; nothing is contacted. The workspace lists the model and
    provider pairs from it.
    """

    family: str
    discovery: dict[str, Any] | None
