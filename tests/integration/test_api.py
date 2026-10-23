# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-006 ASGI interface integration tests."""

from importlib import import_module

import httpx
import pytest

from oak.application import SystemInformationService
from oak.domain import SystemInformation
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app
from oak.ports import OutboxLag

api_module = import_module("oak.interfaces.api.app")

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FailingProbe:
    def is_ready(self) -> bool:
        return False


class ExplodingProbe:
    def is_ready(self) -> bool:
        raise RuntimeError("sensitive dependency detail")


class LagControlPlane:
    def outbox_lag(self, *, tenant_id: str) -> OutboxLag:
        assert tenant_id == "local"
        return OutboxLag(
            pending_events=3,
            oldest_pending_at="2026-08-17T12:00:00Z",
            latest_sequence=8,
            indexed_through=5,
        )


def _service(*, ready: bool = True) -> SystemInformationService:
    information = SystemInformation(
        name="OAK Community",
        version="1.2.3",
        commit="abc123",
        schema_versions=("0.3.0", "0.4.0"),
    )
    probes = () if ready else (FailingProbe(),)
    return SystemInformationService(information, readiness_probes=probes)


async def test_health_readiness_and_version_use_shared_service() -> None:
    transport = httpx.ASGITransport(app=create_app(_service()))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        health = await client.get("/healthz")
        readiness = await client.get("/readyz")
        version = await client.get("/version")

    assert health.json() == {"status": "ok"}
    assert readiness.json() == {"status": "ready"}
    assert version.json() == {
        "name": "OAK Community",
        "version": "1.2.3",
        "commit": "abc123",
        "schema_versions": ["0.3.0", "0.4.0"],
    }


async def test_not_ready_is_a_safe_problem_without_dependency_details() -> None:
    transport = httpx.ASGITransport(
        app=create_app(_service(ready=False)), raise_app_exceptions=False
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-HTTP-ERROR"
    assert "FailingProbe" not in response.text


async def test_unknown_route_is_a_structured_problem() -> None:
    transport = httpx.ASGITransport(app=create_app(_service()))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-NOT-FOUND"
    assert "traceback" not in response.text.lower()


async def test_unexpected_error_is_structured_and_payload_safe() -> None:
    information = SystemInformation("OAK Community", "1.2.3", "abc123", ("0.4.0",))
    service = SystemInformationService(information, readiness_probes=(ExplodingProbe(),))
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/readyz")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-INTERNAL"
    assert "sensitive dependency detail" not in response.text


async def test_outbox_lag_is_observable_without_exposing_event_payloads() -> None:
    application = create_app(
        _service(),
        LagControlPlane(),  # type: ignore[arg-type]
    )
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/v1/system/outbox-lag")

    assert response.json() == {
        "pending_events": 3,
        "oldest_pending_at": "2026-08-17T12:00:00Z",
        "latest_sequence": 8,
        "indexed_through": 5,
        "sequence_lag": 3,
    }
    assert "payload" not in response.text


async def test_chunked_or_sized_request_body_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_module, "MAXIMUM_REQUEST_BYTES", 8)
    transport = httpx.ASGITransport(app=create_app(_service()))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/v1/design-cases",
            content=b"123456789",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["code"] == "OAK-REQUEST-SIZE"


async def test_a_server_without_a_database_refuses_design_cases_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAK-V1-005 (walkthrough V-1): `oak serve` or `oak-api` started without
    OAK_DATABASE_URL answers the routes that need no database, and refuses every
    design-case route with a stable 503 rather than a 500 and a traceback."""

    monkeypatch.delenv("OAK_DATABASE_URL", raising=False)
    transport = httpx.ASGITransport(app=create_app(_service()), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        version = await client.get("/version")
        listed = await client.get("/v1/design-cases")
        created = await client.post(
            "/v1/design-cases",
            headers={"Idempotency-Key": "no-database-create-0001"},
            json={"original_name": "brief.md", "content": "A brief."},
        )

    assert version.status_code == 200
    for response in (listed, created):
        assert response.status_code == 503
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        body = response.json()
        assert body["code"] == "OAK-DATABASE-UNCONFIGURED"
        assert "OAK_DATABASE_URL" in body["detail"]
        assert "traceback" not in response.text.lower()


def test_the_interactive_docs_that_load_third_party_scripts_are_off() -> None:
    """F2-9: /docs and /redoc loaded unpinned CDN JavaScript into the API's origin."""

    from fastapi.testclient import TestClient

    from oak.interfaces.api.app import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 200
