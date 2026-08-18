# SPDX-License-Identifier: Apache-2.0
"""OAK-S4-001 design-case directory listing and audit trail resources."""

import hashlib
import os
from pathlib import Path

import httpx
import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import (
    FileWorkspaceRepository,
    PostgreSQLCaseDirectory,
    PostgreSQLOperationStore,
    PostgreSQLWorkspaceRepository,
    create_postgresql_engine,
)
from oak.adapters.targets import LocalTargetProfile
from oak.application import CommandContext, CommunityControlPlane, OperationService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-18T12:00:00Z"
pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BRIEF = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")
SECOND_BRIEF = BRIEF.replace("id: brief.public-manual-qa", "id: brief.another-case")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _file_control_plane(tmp_path: Path) -> CommunityControlPlane:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    return CommunityControlPlane(
        lambda workspace_id, tenant_id: FileWorkspaceRepository(tmp_path / workspace_id, registry),
        lambda tenant_id: OperationService.__new__(OperationService),
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )


@pytest.fixture
def postgresql_control_plane(tmp_path: Path) -> CommunityControlPlane:
    database_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for PostgreSQL directory tests")
    engine = create_postgresql_engine(database_url)
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    environment_id = f"dir-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]}"

    def repository_factory(workspace_id: str, tenant_id: str) -> PostgreSQLWorkspaceRepository:
        return PostgreSQLWorkspaceRepository(
            engine,
            registry,
            tmp_path / "artifacts",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    def operation_service_factory(tenant_id: str) -> OperationService:
        return OperationService(
            PostgreSQLOperationStore(engine, tenant_id=tenant_id, environment_id=environment_id),
            environment_id=environment_id,
        )

    return CommunityControlPlane(
        repository_factory,
        operation_service_factory,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
        case_directory_factory=lambda tenant_id: PostgreSQLCaseDirectory(
            engine,
            tenant_id=tenant_id,
            environment_id=environment_id,
        ),
    )


def _context(key: str, version: str | None = None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="api",
        occurred_at=NOW,
    )


def _headers(key: str, version: str | None = None) -> dict[str, str]:
    headers = {"Idempotency-Key": key, "X-Correlation-ID": f"correlation-{key}"}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


async def test_directory_lists_ordered_tenant_scoped_case_summaries(
    postgresql_control_plane: CommunityControlPlane,
) -> None:
    control_plane = postgresql_control_plane
    application = create_app(control_plane=control_plane, clock=lambda: NOW)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.get("/v1/design-cases")
        assert empty.status_code == 200
        assert empty.json() == {"items": [], "next_cursor": None}

        for name, content, key in (
            ("public-manual-qa.yaml", BRIEF, "directory-create-first-0001"),
            ("another-case.yaml", SECOND_BRIEF, "directory-create-second-0001"),
        ):
            created = await client.post(
                "/v1/design-cases",
                headers=_headers(key),
                json={"original_name": name, "content": content},
            )
            assert created.status_code == 201, created.text

        listed = await client.get("/v1/design-cases")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert [item["id"] for item in items] == [
            "design-case.another-case",
            "design-case.public-manual-qa",
        ]
        for item in items:
            assert set(item) == {
                "id",
                "workspace_id",
                "version",
                "digest",
                "status",
                "title",
                "updated_at",
            }
            assert item["status"] == "draft"
            assert item["version"] == "0.1.0"
            assert item["updated_at"] == NOW

        first_page = await client.get("/v1/design-cases?limit=1")
        assert len(first_page.json()["items"]) == 1
        assert first_page.json()["items"][0]["id"] == "design-case.another-case"
        cursor = first_page.json()["next_cursor"]
        assert cursor is not None
        second_page = await client.get(f"/v1/design-cases?cursor={cursor}&limit=1")
        assert second_page.json()["items"][0]["id"] == "design-case.public-manual-qa"
        assert second_page.json()["next_cursor"] is None

        invalid = await client.get("/v1/design-cases?cursor=not-a-cursor")
        assert invalid.status_code == 422
        assert invalid.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        assert invalid.json()["code"] == "OAK-CURSOR-INVALID"

    assert control_plane.list_design_cases(tenant_id="local") != ()
    assert control_plane.list_design_cases(tenant_id="tenant-b") == ()


async def test_audit_trail_returns_ordered_events_and_hides_missing_cases(
    postgresql_control_plane: CommunityControlPlane,
) -> None:
    control_plane = postgresql_control_plane
    application = create_app(control_plane=control_plane, clock=lambda: NOW)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/design-cases",
            headers=_headers("directory-audit-create-0001"),
            json={"original_name": "public-manual-qa.yaml", "content": BRIEF},
        )
        assert created.status_code == 201, created.text
        interpreted = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:interpret",
            headers=_headers("directory-audit-interpret-0001", "0.1.0"),
        )
        assert interpreted.status_code == 200, interpreted.text

        trail = await client.get("/v1/design-cases/design-case.public-manual-qa/audit")
        assert trail.status_code == 200
        events = trail.json()["items"]
        assert [event["sequence"] for event in events] == [1, 2]
        assert [event["event_type"] for event in events] == ["case_created", "brief_interpreted"]
        for event in events:
            assert event["case_id"] == "design-case.public-manual-qa"
            assert event["interface_origin"] == "api"
            assert event["actor"] == "local-user"

        first = await client.get("/v1/design-cases/design-case.public-manual-qa/audit?limit=1")
        assert [event["sequence"] for event in first.json()["items"]] == [1]
        cursor = first.json()["next_cursor"]
        assert cursor is not None
        rest = await client.get(
            f"/v1/design-cases/design-case.public-manual-qa/audit?cursor={cursor}"
        )
        assert [event["sequence"] for event in rest.json()["items"]] == [2]

        missing = await client.get("/v1/design-cases/design-case.missing/audit")
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_audit_trail_is_available_from_the_file_repository(tmp_path: Path) -> None:
    control_plane = _file_control_plane(tmp_path)
    created = control_plane.create_design_case(
        original_name="public-manual-qa.yaml",
        content=BRIEF.encode("utf-8"),
        context=_context("file-directory-create-0001"),
    )
    assert created.case["version"] == "0.1.0"
    control_plane.interpret(
        "design-case.public-manual-qa", _context("file-directory-interpret-0001", "0.1.0")
    )
    events = control_plane.list_audit_events("design-case.public-manual-qa", tenant_id="local")
    assert [event["sequence"] for event in events] == [1, 2]
    assert [event["event_type"] for event in events] == ["case_created", "brief_interpreted"]
