# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005: refusals the REST surface used to answer wrongly.

A schema-invalid input answered 500 with a traceback (F2-3); a brief id the server could
never read back created an unreachable case (F2-5); creating a case that already exists
read as a stale view to retry (F2-10); and a stale record-report reached the model before
the version was checked (F2-6, pinned in the report service test). Each is a stable
refusal now, with nothing stored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.report import PdfReportRenderer
from oak.adapters.targets import LocalTargetProfile
from oak.application import CommunityControlPlane, OperationService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-23T12:00:00Z"
TOKEN = "refusals-model-token-0123456789"
BRIEF = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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


async def _create(client: httpx.AsyncClient, content: str, key: str) -> httpx.Response:
    return await client.post(
        "/v1/design-cases",
        headers={"Idempotency-Key": key},
        json={"original_name": "brief.yaml", "content": content},
    )


def _problem(response: httpx.Response) -> dict[str, Any]:
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE), response.text
    return dict(response.json())


async def test_a_brief_id_the_server_cannot_read_back_is_refused_before_anything_is_stored(
    tmp_path: Path,
) -> None:
    async with _client(tmp_path) as client:
        for brief_id in ("brief.F2-Upper-Case", "brief.f2:colon-case"):
            refused = await _create(
                client,
                BRIEF.replace("id: brief.public-manual-qa", f"id: {brief_id}"),
                f"create-{brief_id.removeprefix('brief.').lower().replace(':', '-')}-0001",
            )
            assert refused.status_code == 422, refused.text
            assert _problem(refused)["code"] == "OAK-INTAKE-IDENTITY"
    assert list(tmp_path.iterdir()) == []


async def test_creating_a_case_that_exists_is_a_named_refusal_not_a_retry(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        assert (await _create(client, BRIEF, "create-original-000001")).status_code == 201
        edited = BRIEF.replace("title:", "title: Edited", 1)
        again = await _create(client, edited, "create-edited-0000001")
    problem = _problem(again)
    assert again.status_code == 409
    assert problem["code"] == "OAK-CASE-EXISTS" and problem["retriable"] is False
    assert "design-case.public-manual-qa" in problem["detail"]


async def test_schema_invalid_input_is_a_422_with_a_stable_code(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        imported = await client.post(
            "/v1/design-cases:import",
            headers={"Idempotency-Key": "import-invalid-000001"},
            json={"export_version": "0.1.0", "manifest": {}, "objects": []},
        )
        assert (await _create(client, BRIEF, "create-confirmable-001")).status_code == 201
        confirmed = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:confirm",
            headers={"Idempotency-Key": "confirm-invalid-00001", "If-Match": '"0.1.0"'},
            json={"answers": {"foo": "bar"}},
        )
    for response in (imported, confirmed):
        assert response.status_code == 422, response.text
        assert _problem(response)["code"] in {"OAK-CONTRACT-INVALID", "OAK-REQUEST-INVALID"}
    assert _problem(imported)["code"] == "OAK-CONTRACT-INVALID"
