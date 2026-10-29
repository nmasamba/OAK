# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-034 (RR-024): the API's per-address and per-tenant request limits, the `429`
answers the application raises, and what the contract and the access log say about them."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import httpx
import pytest

from oak.application import SystemInformationService
from oak.domain import OAKError, SystemInformation
from oak.interfaces.api.app import OPERATION_QUOTA_RETRY_SECONDS, PROBLEM_MEDIA_TYPE, create_app
from oak.interfaces.api.limits import RequestLimits
from oak.interfaces.logs import configure_logging

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    monkeypatch.setenv("OAK_LOG_LEVEL", "DEBUG")
    stream = io.StringIO()
    configure_logging("oak-api", stream=stream)
    yield stream
    root.handlers[:], level = saved
    root.setLevel(level)
    logging.captureWarnings(False)


class _Clock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


def _service() -> SystemInformationService:
    return SystemInformationService(
        SystemInformation(
            name="OAK Community",
            version="1.2.3",
            commit="abc123",
            schema_versions=("0.3.0", "0.4.0"),
        )
    )


def _client(application: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


async def test_the_address_limit_answers_429_with_retry_after_then_admits_again() -> None:
    clock = _Clock()
    application = create_app(
        _service(), request_limits=RequestLimits(per_address=3, per_tenant=100, clock=clock)
    )
    async with _client(application) as client:
        for _ in range(3):
            assert (await client.get("/version")).status_code == 200
        refused = await client.get("/version")
        assert refused.status_code == 429
        assert refused.headers["content-type"] == PROBLEM_MEDIA_TYPE
        assert int(refused.headers["retry-after"]) >= 1
        body = refused.json()
        assert body["code"] == "OAK-RATE-LIMIT-ADDRESS"
        assert body["status"] == 429 and body["retriable"] is True
        assert "127.0.0.1" not in refused.text, "the address is not echoed"
        # The probes are exempt, so a healthcheck is never refused with its machine.
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/readyz")).status_code == 200
        assert (await client.get("/version")).status_code == 429
        clock.now += 60
        assert (await client.get("/version")).status_code == 200


async def test_the_tenant_limit_is_keyed_on_the_tenant_the_request_claims() -> None:
    application = create_app(
        _service(), request_limits=RequestLimits(per_address=100, per_tenant=2, clock=_Clock())
    )
    async with _client(application) as client:
        assert (await client.get("/version")).status_code == 200
        assert (await client.get("/version")).status_code == 200
        refused = await client.get("/version")
        assert refused.status_code == 429
        assert refused.json()["code"] == "OAK-RATE-LIMIT-TENANT"
        assert int(refused.headers["retry-after"]) >= 1
        # Another tenant's claim is another bucket; what the claim is worth is for the
        # authority check, not the limiter.
        other = await client.get("/version", headers={"X-OAK-Tenant": "other"})
        assert other.status_code == 200


async def test_zero_switches_a_limit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAK_REQUESTS_PER_MINUTE_PER_ADDRESS", "0")
    monkeypatch.setenv("OAK_REQUESTS_PER_MINUTE_PER_TENANT", "0")
    async with _client(create_app(_service())) as client:
        for _ in range(50):
            assert (await client.get("/version")).status_code == 200


def test_a_bad_environment_value_refuses_to_build_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAK_REQUESTS_PER_MINUTE_PER_ADDRESS", "plenty")
    with pytest.raises(OAKError) as refusal:
        create_app(_service())
    assert refusal.value.code == "OAK-LIMIT-CONFIG"


async def test_the_access_line_names_the_limit_by_its_code_and_never_the_address(
    captured: io.StringIO,
) -> None:
    application = create_app(
        _service(), request_limits=RequestLimits(per_address=1, per_tenant=100, clock=_Clock())
    )
    async with _client(application) as client:
        assert (await client.get("/version")).status_code == 200
        assert (await client.get("/version")).status_code == 429
    lines = [json.loads(line) for line in captured.getvalue().splitlines()]
    refused = [line for line in lines if line.get("status") == 429]
    assert len(refused) == 1
    assert refused[0]["code"] == "OAK-RATE-LIMIT-ADDRESS"
    assert refused[0]["route"] == "unmatched", "a refused request is not routed"
    assert "127.0.0.1" not in captured.getvalue()


async def test_the_application_s_own_429s_carry_retry_after() -> None:
    application = create_app(_service())

    @application.get("/limit-test/{code}")
    async def raise_code(code: str) -> None:
        raise OAKError(code, "refused for the test", retriable=True)

    async with _client(application) as client:
        quota = await client.get("/limit-test/OAK-OPERATION-QUOTA")
        assert quota.status_code == 429
        assert quota.headers["retry-after"] == str(OPERATION_QUOTA_RETRY_SECONDS)
        assert quota.json()["retriable"] is True
        budget = await client.get("/limit-test/OAK-MODEL-BUDGET")
        assert budget.status_code == 429
        assert 1 <= int(budget.headers["retry-after"]) <= 86_400, "until the next UTC day"
        other = await client.get("/limit-test/OAK-INTERPRET-STATE")
        assert other.status_code == 409 and "retry-after" not in other.headers


def test_the_contract_documents_429_with_retry_after_on_every_operation() -> None:
    document = create_app(_service()).openapi()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            response = operation["responses"]["429"]
            assert response["headers"]["Retry-After"]["schema"]["type"] == "integer", (method, path)
            assert PROBLEM_MEDIA_TYPE in response["content"], (method, path)
