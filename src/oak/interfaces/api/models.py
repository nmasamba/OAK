# SPDX-License-Identifier: Apache-2.0
"""HTTP response models only; no domain policy lives here."""

from typing import Literal

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
