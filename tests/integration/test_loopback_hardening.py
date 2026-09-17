# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-002: a page from another origin, or a rebound name, cannot drive the local API.

The API binds a local actor from headers and has no authentication. Before Sprint 9 the only
thing keeping a hostile web page from issuing requests was that every mutation needed custom
headers a simple cross-origin request cannot carry — an accident, not a control, and no help
against DNS rebinding. These tests pin the deliberate control: a `Host` allowlist, an
`Origin` and `Sec-Fetch-Site` guard, and stricter rules on the credential routes.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from oak.application import SystemInformationService
from oak.domain import OAKError, SystemInformation
from oak.interfaces.api.app import (
    PROBLEM_MEDIA_TYPE,
    _LoopbackGuardMiddleware,
    create_app,
    is_credential_route,
    parse_allowed_hosts,
    verify_model_token,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _service() -> SystemInformationService:
    return SystemInformationService(
        SystemInformation(
            name="OAK Community", version="9.9.9", commit="test", schema_versions=("0.4.0",)
        ),
        readiness_probes=(),
    )


def _client(**options: Any) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(_service(), **options))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


async def test_a_non_loopback_host_is_refused_before_routing_without_echoing_it() -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Host": "evil.example:8080"})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "OAK-HOST-DENIED"
    assert "evil" not in response.text


@pytest.mark.parametrize(
    "host", ["attacker.localhost:5173", "127.0.0.1.evil.example", "10.0.0.5:8080", "[::2]:8080"]
)
async def test_lookalike_and_private_hosts_are_not_loopback(host: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Host": host})

    assert response.status_code == 400
    assert response.json()["code"] == "OAK-HOST-DENIED"


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.1:8080", "localhost:5173", "LOCALHOST", "[::1]:8080"]
)
async def test_loopback_hosts_on_any_port_are_served(host: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Host": host})

    assert response.status_code == 200


async def test_health_probes_do_not_require_a_loopback_host() -> None:
    async with _client() as client:
        health = await client.get("/healthz", headers={"Host": "orchestrator.internal"})
        version = await client.get("/version", headers={"Host": "orchestrator.internal"})

    assert health.status_code == 200
    assert version.status_code == 400


async def test_allowed_hosts_extends_the_allowlist_with_exact_names_only() -> None:
    hosts = parse_allowed_hosts(" api.internal, *.wild.example ,LAN.Example:8080 ")
    assert hosts == frozenset({"api.internal", "lan.example"})

    async with _client(allowed_hosts=hosts) as client:
        exact = await client.get("/version", headers={"Host": "api.internal:8080"})
        subdomain = await client.get("/version", headers={"Host": "sub.api.internal"})
        credential = await client.put(
            "/v1/models/credentials/openai", headers={"Host": "api.internal"}, json={}
        )

    assert exact.status_code == 200
    assert subdomain.status_code == 400
    # Credential routes require a loopback Host whatever the allowlist says.
    assert credential.status_code == 400
    assert credential.json()["code"] == "OAK-HOST-DENIED"


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
async def test_cross_site_and_same_site_fetch_metadata_are_refused(site: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Sec-Fetch-Site": site})

    assert response.status_code == 403
    assert response.json()["code"] == "OAK-ORIGIN-DENIED"


@pytest.mark.parametrize("site", ["same-origin", "none"])
async def test_same_origin_and_user_initiated_fetch_metadata_pass(site: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Sec-Fetch-Site": site})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "null", "http://attacker.localhost:5173", "file://", "chrome"],
)
async def test_non_loopback_and_null_origins_are_refused(origin: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Origin": origin})

    assert response.status_code == 403
    assert response.json()["code"] == "OAK-ORIGIN-DENIED"
    assert "evil" not in response.text


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173"])
async def test_loopback_origins_pass(origin: str) -> None:
    async with _client() as client:
        response = await client.get("/version", headers={"Origin": origin})

    assert response.status_code == 200


async def test_the_dns_rebinding_shape_is_refused_by_the_host_rule() -> None:
    # The attacker's page is same-origin with the rebound name, so fetch metadata and Origin
    # look innocent; only the Host header gives it away.
    async with _client() as client:
        response = await client.get(
            "/version",
            headers={
                "Host": "evil.example:5173",
                "Origin": "http://evil.example:5173",
                "Sec-Fetch-Site": "same-origin",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "OAK-HOST-DENIED"


async def test_credential_routes_require_a_same_origin_browser_or_a_non_browser_client() -> None:
    headers = {"Host": "127.0.0.1"}
    async with _client() as client:
        browser_same_site = await client.put(
            "/v1/models/credentials/openai",
            headers={**headers, "Origin": "http://localhost:5173"},
            json={},
        )
        browser_same_origin = await client.put(
            "/v1/models/credentials/openai",
            headers={
                **headers,
                "Origin": "http://127.0.0.1:5173",
                "Sec-Fetch-Site": "same-origin",
            },
            json={},
        )
        non_browser = await client.post("/v1/models/openai:discover", headers=headers)

    assert browser_same_site.status_code == 403
    assert browser_same_site.json()["code"] == "OAK-ORIGIN-DENIED"
    # Past the guard, the route answers for itself. Since OAK-S9-006 these routes exist, so
    # what the guard lets through is now handled by the capability-token check and the
    # request model rather than by a 404. What matters here is that neither is refused by
    # the guard: the code is never the guard's own.
    for allowed in (browser_same_origin, non_browser):
        assert allowed.status_code in {403, 422}
        assert allowed.json()["code"] != "OAK-ORIGIN-DENIED"
        assert allowed.json()["code"] != "OAK-HOST-DENIED"
    assert browser_same_origin.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"
    assert non_browser.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"


def test_credential_route_recognition_is_exact() -> None:
    assert is_credential_route("/v1/models/credentials/openai")
    assert is_credential_route("/v1/models/selection")
    assert is_credential_route("/v1/models/huggingface:discover")
    assert not is_credential_route("/v1/models")
    assert not is_credential_route("/v1/design-cases")


async def test_a_missing_host_header_is_refused() -> None:
    captured: list[dict[str, Any]] = []

    async def downstream(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        raise AssertionError("the guard must not forward a request without a Host")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        captured.append(message)

    guard = _LoopbackGuardMiddleware(downstream, allowed_hosts=frozenset())
    await guard({"type": "http", "path": "/version", "headers": []}, receive, send)

    assert captured[0]["status"] == 400


async def test_the_guard_adds_nothing_to_the_openapi_contract() -> None:
    application = create_app(_service())
    document = application.openapi()
    parameters = {
        parameter["name"].lower()
        for path in document["paths"].values()
        for operation in path.values()
        for parameter in operation.get("parameters", [])
    }
    assert not {"host", "origin", "sec-fetch-site"} & parameters


def test_the_model_token_check_is_constant_time_and_never_vacuous() -> None:
    verify_model_token("a" * 32, "a" * 32)
    for presented, expected in ((None, "a" * 32), ("a" * 32, None), ("b" * 32, "a" * 32), ("", "")):
        with pytest.raises(OAKError) as refusal:
            verify_model_token(presented, expected)
        assert refusal.value.code == "OAK-MODEL-TOKEN-REQUIRED"
        assert refusal.value.retriable is False
