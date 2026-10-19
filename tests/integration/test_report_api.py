# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-004: `POST /v1/design-cases/{case_id}:record-report` and the files it records.

The command takes an idempotency key and `If-Match` like every other command, maps a case
that is not ready to 409 with the step that is missing, and demands the capability token
exactly when a model would be called. The PDF and the document are read back through the
existing artifact route, and their bytes hash to the digest the server names.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.models.fake_narrator import FakeReportNarrator
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.report import PdfReportRenderer
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    CandidatePlanningService,
    CommandContext,
    CommunityControlPlane,
    DesignCaseService,
    OperationService,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-16T12:00:00Z"
WORKSPACE = "workspace.public-manual-qa"
CASE = "design-case.public-manual-qa"
ROUTE = f"/v1/design-cases/{CASE}:record-report"
TOKEN = "report-model-token-0123456789"
pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _context(key: str, version: str | None = None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


def _build(tmp_path: Path, *, select: bool) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(tmp_path / WORKSPACE, registry)
    design = DesignCaseService(
        repository, LocalBriefIntake(), DeterministicBriefInterpreter(), registry
    )
    planning = CandidatePlanningService(
        repository,
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )
    design.initialize(workspace_id=WORKSPACE, tenant_id="local", created_at=NOW)
    design.design(ROOT / "examples/briefs/public-manual-qa.yaml", _context("report-design-0001"))
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context("report-confirm-00001", "0.1.1"))
    planning.candidates(_context("report-generate-0001", "0.1.2"))
    if select:
        planning.evaluate("candidate-03", _context("report-evaluate-0001", "0.1.3"))
        planning.select("candidate-03", "balanced", _context("report-select-000001", "0.1.4"))


def _client(tmp_path: Path, *, narrator: Any = None) -> httpx.AsyncClient:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    plane = CommunityControlPlane(
        lambda workspace_id, tenant_id: FileWorkspaceRepository(tmp_path / workspace_id, registry),
        lambda tenant_id: OperationService.__new__(OperationService),
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
        report_renderer=PdfReportRenderer(),
        report_narrator_factory=(lambda mode: narrator) if narrator is not None else None,
        oak_version="0.9.0",
    )
    application = create_app(control_plane=plane, clock=lambda: NOW, model_token=TOKEN)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    )


def _headers(key: str, version: str, **extra: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "If-Match": f'"{version}"', **extra}


async def test_recording_returns_the_report_and_its_files_read_back_by_digest(
    tmp_path: Path,
) -> None:
    _build(tmp_path, select=True)
    async with _client(tmp_path) as client:
        recorded = await client.post(ROUTE, headers=_headers("report-api-record-001", "0.1.5"))
        assert recorded.status_code == 200, recorded.text
        assert recorded.headers["etag"] == '"0.1.6"'
        body = recorded.json()
        assert body["duplicate"] is False
        assert body["case"]["status"] == "candidate_selected"
        assert body["document"]["case_ref"]["version"] == "0.1.5"
        for field, media_type in (
            ("pdf_ref", "application/pdf"),
            ("document_ref", "application/vnd.oak.architecture-report+json"),
        ):
            reference = body["report"][field]
            fetched = await client.get(
                f"/v1/design-cases/{CASE}/artifacts/{reference['id']}",
                params={"version": reference["version"], "digest": reference["digest"]},
            )
            assert fetched.status_code == 200
            assert fetched.headers["content-type"].startswith(media_type)
            assert fetched.headers["x-oak-artifact-digest"] == reference["digest"]
            assert f"sha256:{hashlib.sha256(fetched.content).hexdigest()}" == reference["digest"]

        retried = await client.post(ROUTE, headers=_headers("report-api-record-001", "0.1.5"))
        assert retried.status_code == 200
        assert retried.json()["duplicate"] is True
        assert retried.json()["report"] == body["report"]


async def test_a_stale_if_match_is_a_conflict(tmp_path: Path) -> None:
    _build(tmp_path, select=True)
    async with _client(tmp_path) as client:
        stale = await client.post(ROUTE, headers=_headers("report-api-stale-0001", "0.1.4"))
    assert stale.status_code == 409
    assert stale.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert stale.json()["code"] == "OAK-EXPECTED-VERSION"


async def test_a_case_without_a_selection_is_a_conflict_naming_the_step(tmp_path: Path) -> None:
    _build(tmp_path, select=False)
    async with _client(tmp_path) as client:
        early = await client.post(ROUTE, headers=_headers("report-api-early-0001", "0.1.3"))
    assert early.status_code == 409
    assert early.json()["code"] == "OAK-REPORT-STATE"
    assert "select a candidate" in early.json()["detail"]


async def test_an_unknown_case_is_not_found(tmp_path: Path) -> None:
    _build(tmp_path, select=True)
    async with _client(tmp_path) as client:
        missing = await client.post(
            "/v1/design-cases/design-case.nobody-here:record-report",
            headers=_headers("report-api-missing-01", "0.1.5"),
        )
    assert missing.status_code == 404
    # The file adapter finds no workspace; the PostgreSQL one finds no case. Both are 404.
    assert missing.json()["code"] in {"OAK-CASE-NOT-FOUND", "OAK-WORKSPACE-NOT-FOUND"}


async def test_a_model_mode_needs_the_capability_token_before_anything_runs(
    tmp_path: Path,
) -> None:
    _build(tmp_path, select=True)
    narrator = FakeReportNarrator(
        [{"section": "7", "text": "The owner chose Balanced over three alternatives."}]
    )
    async with _client(tmp_path, narrator=narrator) as client:
        refused = await client.post(
            ROUTE,
            params={"narrative": "online"},
            headers=_headers("report-api-model-0001", "0.1.5"),
        )
        assert refused.status_code == 403
        assert refused.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"
        assert narrator.calls == []
        accepted = await client.post(
            ROUTE,
            params={"narrative": "online"},
            headers=_headers("report-api-model-0001", "0.1.5", **{"X-OAK-Model-Token": TOKEN}),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["report"]["narrative_mode"] == "online"
        assert accepted.json()["report"]["narrative_ref"]["id"].startswith("narrative.")
        assert len(narrator.calls) == 1


async def test_a_model_mode_with_nothing_configured_records_nothing(tmp_path: Path) -> None:
    _build(tmp_path, select=True)
    async with _client(tmp_path) as client:
        refused = await client.post(
            ROUTE,
            params={"narrative": "local"},
            headers=_headers("report-api-model-0002", "0.1.5", **{"X-OAK-Model-Token": TOKEN}),
        )
        assert refused.json()["code"] == "OAK-MODEL-NOT-CONFIGURED"
        assert "--narrative deterministic" in refused.json()["detail"]
        case = await client.get(f"/v1/design-cases/{CASE}")
    assert case.json()["case"]["version"] == "0.1.5"


async def test_an_unknown_narrative_mode_is_refused_by_the_contract(tmp_path: Path) -> None:
    _build(tmp_path, select=True)
    async with _client(tmp_path) as client:
        refused = await client.post(
            ROUTE,
            params={"narrative": "cloud"},
            headers=_headers("report-api-model-0003", "0.1.5"),
        )
    assert refused.status_code == 422
