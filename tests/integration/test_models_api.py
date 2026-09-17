# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-006: the model-configuration REST resources never hand back a credential.

These routes are the only ones in the API that accept a secret, so they are also the only
ones that could leak one. Each test here is about that: the key is write-only in the schema
and in the responses, a validation failure echoes nothing, the capability token is required
before anything changes, and after a successful PUT the key is absent from every response,
from the OpenAPI document, from the database, and from the artifact root.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak.application import ModelConfigurationService
from oak.bootstrap import create_model_configuration_service
from oak.domain import OAKError
from oak.interfaces.api.app import create_app

pytestmark = pytest.mark.integration

TOKEN = "models-api-capability-token-0123456789"
KEY = "oak-test-key-openai-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    app = create_app(model_token=TOKEN, model_configuration=create_model_configuration_service)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def _headers(token: str | None = TOKEN) -> dict[str, str]:
    return {"X-OAK-Model-Token": token} if token is not None else {}


def _put_key(client: TestClient, family: str = "openai", key: str = KEY) -> Any:
    return client.put(f"/v1/models/credentials/{family}", json={"api_key": key}, headers=_headers())


def test_the_status_resource_shows_every_family_and_no_credential(client: TestClient) -> None:
    assert _put_key(client).status_code == 204

    response = client.get("/v1/models", headers=_headers())

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    document = response.json()
    assert KEY not in response.text
    families = {family["family"] for family in document["families"]}
    assert families == {"huggingface", "openai", "anthropic", "gemini", "meta", "xai", "local"}
    openai = next(row for row in document["credentials"] if row["family"] == "openai")
    assert openai["configured"] is True
    assert openai["source"] in {"keychain", "file"}
    assert openai["fingerprint"] and len(openai["fingerprint"]) == 8
    assert openai["length"] == len(KEY)
    assert "api_key" not in json.dumps(document)
    assert document["configured"] is False, "a key alone is not a selection"


def test_a_key_is_never_echoed_by_any_response_or_stored_outside_its_directory(
    client: TestClient, tmp_path: Path
) -> None:
    assert _put_key(client).status_code == 204
    client.put(
        "/v1/models/selection",
        json={"family": "openai", "model_id": "gpt-6-astra"},
        headers=_headers(),
    )

    for path in ("/v1/models", "/version", "/healthz"):
        assert KEY not in client.get(path, headers=_headers()).text, path
    assert KEY not in json.dumps(client.app.openapi())  # type: ignore[attr-defined]

    holders = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and KEY in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert [path.name for path in holders] == ["openai.key"], holders
    assert KEY not in (tmp_path / "models" / "model-configuration.json").read_text("utf-8")


def test_the_openapi_document_marks_the_key_write_only_and_carries_no_example(
    client: TestClient,
) -> None:
    document = client.app.openapi()  # type: ignore[attr-defined]
    schema = document["components"]["schemas"]["ModelCredentialRequest"]["properties"]["api_key"]
    assert schema["writeOnly"] is True
    assert schema["format"] == "password"
    assert "example" not in schema and "examples" not in schema
    for name, component in document["components"]["schemas"].items():
        if name == "ModelCredentialRequest":
            continue
        forbidden = {"api_key", "key", "secret", "token"} & set(component.get("properties", {}))
        assert not forbidden, (name, forbidden)


def test_a_malformed_key_body_is_refused_without_echoing_what_was_sent(
    client: TestClient,
) -> None:
    for body in ({"api_key": "short"}, {"api_key": "x" * 600}, {"api_key": 7}, {}):
        response = client.put("/v1/models/credentials/openai", json=body, headers=_headers())
        assert response.status_code == 422, body
        rendered = response.text
        assert "short" not in rendered and "x" * 40 not in rendered
        problem = response.json()
        assert problem["code"] in {"OAK-REQUEST-INVALID", "OAK-MODEL-KEY-INPUT"}
        for entry in problem.get("errors", []):
            assert "api_key" not in entry["message"] or "value" not in entry["message"].lower()


def test_every_model_route_requires_the_capability_token(client: TestClient) -> None:
    calls = (
        ("GET", "/v1/models", None),
        ("PUT", "/v1/models/credentials/openai", {"api_key": KEY}),
        ("DELETE", "/v1/models/credentials/openai", None),
        ("PUT", "/v1/models/selection", {"family": "openai", "model_id": "gpt-6-astra"}),
        ("DELETE", "/v1/models/selection", None),
        ("POST", "/v1/models/openai:discover", None),
    )
    for method, path, body in calls:
        for token in (None, "wrong-token-that-is-long-enough-01"):
            response = client.request(method, path, json=body, headers=_headers(token))
            assert response.status_code == 403, (method, path, token)
            assert response.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"

    status = client.get("/v1/models", headers=_headers()).json()
    assert all(row["configured"] is False for row in status["credentials"])
    assert status["selection"] is None


def test_deleting_a_credential_is_idempotent_and_clears_the_status(client: TestClient) -> None:
    assert _put_key(client).status_code == 204
    assert client.delete("/v1/models/credentials/openai", headers=_headers()).status_code == 204
    assert client.delete("/v1/models/credentials/openai", headers=_headers()).status_code == 204

    status = client.get("/v1/models", headers=_headers()).json()
    openai = next(row for row in status["credentials"] if row["family"] == "openai")
    assert openai["configured"] is False
    assert openai["source"] == "none"
    assert openai["fingerprint"] is None


def test_a_selection_needs_a_key_and_is_readable_back(client: TestClient) -> None:
    refused = client.put(
        "/v1/models/selection",
        json={"family": "openai", "model_id": "gpt-6-astra"},
        headers=_headers(),
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "OAK-MODEL-KEY-MISSING"

    _put_key(client)
    accepted = client.put(
        "/v1/models/selection",
        json={"family": "openai", "model_id": "gpt-6-astra"},
        headers=_headers(),
    )
    assert accepted.status_code == 200
    assert accepted.headers["Cache-Control"] == "no-store"
    document = accepted.json()
    assert document["configured"] is True
    assert document["selection"]["model_id"] == "gpt-6-astra"
    assert document["selection"]["default_interpreter"] == "model"

    cleared = client.delete("/v1/models/selection", headers=_headers())
    assert cleared.status_code == 200 and cleared.json()["selection"] is None


def test_an_unknown_family_is_refused_with_the_shared_code(client: TestClient) -> None:
    response = client.put(
        "/v1/models/credentials/deepmind", json={"api_key": KEY}, headers=_headers()
    )
    assert response.status_code == 422
    assert response.json()["code"] == "OAK-MODEL-FAMILY-UNKNOWN"


def test_discovery_reports_its_snapshot_and_marks_staleness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    monkeypatch.setenv("OAK_MODEL_DISCOVERY_CACHE_SECONDS", "60")
    snapshot = {
        "fetched_at": "2026-09-17T11:00:00Z",
        "source": "live",
        "recommended": "openai/gpt-oss-120b",
        "filtered_out_count": 3,
        "models": [
            {
                "id": "openai/gpt-oss-120b",
                "display_name": "openai/gpt-oss-120b",
                "created": None,
                "licence": "apache-2.0",
                "data_use": "unknown",
                "providers": [
                    {
                        "provider": "deepinfra",
                        "supports_structured_output": True,
                        "output_price_per_million": 0.17,
                    }
                ],
            }
        ],
    }

    def service() -> ModelConfigurationService:
        return create_model_configuration_service_with(lambda family, previous: snapshot)

    def create_model_configuration_service_with(discoverer: Any) -> ModelConfigurationService:
        built = create_model_configuration_service()
        built._discoverer = discoverer
        return built

    app = create_app(model_token=TOKEN, model_configuration=service)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/v1/models/huggingface:discover", headers=_headers())
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["discovery"]["recommended"] == "openai/gpt-oss-120b"

        # The clock the app was built with is "now", so an hour-old snapshot is stale at 60s.
        status = client.get("/v1/models", headers=_headers()).json()
        assert status["discovery"]["huggingface"]["stale"] is True
        assert status["discovery"]["huggingface"]["model_count"] == 1


def test_discovery_without_a_discoverer_is_an_explicit_refusal(client: TestClient) -> None:
    app = create_app(
        model_token=TOKEN,
        model_configuration=lambda: _service_without_discovery(),
    )
    with TestClient(app, base_url="http://127.0.0.1") as bare:
        response = bare.post("/v1/models/openai:discover", headers=_headers())
    assert response.status_code == 422
    assert response.json()["code"] == "OAK-MODEL-DISCOVERY-UNAVAILABLE"


def _service_without_discovery() -> ModelConfigurationService:
    service = create_model_configuration_service()
    service._discoverer = None
    return service


def test_the_mcp_surface_gains_no_model_configuration_tool() -> None:
    from oak.interfaces.mcp.tools import TOOL_NAMES

    assert not any("model" in name or "credential" in name or "key" in name for name in TOOL_NAMES)
    assert len(TOOL_NAMES) == 11


def test_a_provider_failure_during_discovery_keeps_its_code(client: TestClient) -> None:
    def failing() -> ModelConfigurationService:
        service = create_model_configuration_service()

        def refuse(family: str, previous: Any) -> dict[str, Any]:
            raise OAKError(
                "OAK-MODEL-RATE-LIMITED", "the provider is rate limiting", retriable=True
            )

        service._discoverer = refuse
        return service

    app = create_app(model_token=TOKEN, model_configuration=failing)
    with TestClient(app, base_url="http://127.0.0.1") as rate_limited:
        response = rate_limited.post("/v1/models/openai:discover", headers=_headers())
    assert response.status_code == 429
    assert response.json()["code"] == "OAK-MODEL-RATE-LIMITED"
    assert response.json()["retriable"] is True
