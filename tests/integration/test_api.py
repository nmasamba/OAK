# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-006 ASGI interface integration tests."""

import httpx
import pytest

from oak.application import SystemInformationService
from oak.domain import SystemInformation
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-HTTP-ERROR"
    assert "FailingProbe" not in response.text


async def test_unknown_route_is_a_structured_problem() -> None:
    transport = httpx.ASGITransport(app=create_app(_service()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-NOT-FOUND"
    assert "traceback" not in response.text.lower()


async def test_unexpected_error_is_structured_and_payload_safe() -> None:
    information = SystemInformation("OAK Community", "1.2.3", "abc123", ("0.4.0",))
    service = SystemInformationService(information, readiness_probes=(ExplodingProbe(),))
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["code"] == "OAK-INTERNAL"
    assert "sensitive dependency detail" not in response.text
