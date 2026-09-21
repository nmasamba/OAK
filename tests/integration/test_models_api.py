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

from oak.application import ModelConfigurationService, validate_key_input
from oak.bootstrap import create_model_configuration_service
from oak.domain import OAKError
from oak.interfaces.api.app import create_app
from tests.mcp_support import build_file_control_plane

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


def _put_key(client: TestClient, family: str = "huggingface", key: str = KEY) -> Any:
    return client.put(f"/v1/models/credentials/{family}", json={"api_key": key}, headers=_headers())


def test_the_status_resource_shows_every_family_and_no_credential(client: TestClient) -> None:
    assert _put_key(client).status_code == 204

    response = client.get("/v1/models", headers=_headers())

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    document = response.json()
    assert KEY not in response.text
    families = {family["family"] for family in document["families"]}
    assert families == {"huggingface", "local"}
    openai = next(row for row in document["credentials"] if row["family"] == "huggingface")
    assert openai["configured"] is True
    assert openai["source"] in {"keychain", "file"}
    assert openai["fingerprint"] and len(openai["fingerprint"]) == 8
    assert openai["length"] == len(KEY)
    assert "api_key" not in json.dumps(document)
    assert document["modes"]["online"]["available"] is False, "a key alone is nothing to call"
    assert "oak models discover" in document["modes"]["online"]["reason"]
    assert document["modes"]["deterministic"]["available"] is True


def test_a_key_is_never_echoed_by_any_response_or_stored_outside_its_directory(
    client: TestClient, tmp_path: Path
) -> None:
    assert _put_key(client).status_code == 204
    client.put(
        "/v1/models/selection",
        json={"family": "huggingface", "model_id": "openai/gpt-oss-120b"},
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
    assert [path.name for path in holders] == ["huggingface.key"], holders
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
        response = client.put("/v1/models/credentials/huggingface", json=body, headers=_headers())
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
        ("PUT", "/v1/models/credentials/huggingface", {"api_key": KEY}),
        ("DELETE", "/v1/models/credentials/huggingface", None),
        (
            "PUT",
            "/v1/models/selection",
            {"family": "huggingface", "model_id": "openai/gpt-oss-120b"},
        ),
        ("DELETE", "/v1/models/selection/huggingface", None),
        ("POST", "/v1/models/huggingface:discover", None),
        ("POST", "/v1/models/huggingface:verify", None),
    )
    for method, path, body in calls:
        for token in (None, "wrong-token-that-is-long-enough-01"):
            response = client.request(method, path, json=body, headers=_headers(token))
            assert response.status_code == 403, (method, path, token)
            assert response.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"

    status = client.get("/v1/models", headers=_headers()).json()
    assert all(row["configured"] is False for row in status["credentials"])
    assert status["selections"] == {"huggingface": None, "local": None}


def test_deleting_a_credential_is_idempotent_and_clears_the_status(client: TestClient) -> None:
    assert _put_key(client).status_code == 204
    route = "/v1/models/credentials/huggingface"
    assert client.delete(route, headers=_headers()).status_code == 204
    assert client.delete(route, headers=_headers()).status_code == 204

    status = client.get("/v1/models", headers=_headers()).json()
    openai = next(row for row in status["credentials"] if row["family"] == "huggingface")
    assert openai["configured"] is False
    assert openai["source"] == "none"
    assert openai["fingerprint"] is None


def test_a_selection_needs_a_key_and_is_readable_back(client: TestClient) -> None:
    refused = client.put(
        "/v1/models/selection",
        json={"family": "huggingface", "model_id": "openai/gpt-oss-120b"},
        headers=_headers(),
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "OAK-MODEL-KEY-MISSING"

    _put_key(client)
    accepted = client.put(
        "/v1/models/selection",
        json={"family": "huggingface", "model_id": "openai/gpt-oss-120b"},
        headers=_headers(),
    )
    assert accepted.status_code == 200
    assert accepted.headers["Cache-Control"] == "no-store"
    document = accepted.json()
    assert document["modes"]["online"]["available"] is True
    assert document["modes"]["online"]["pair"]["source"] == "pinned"
    assert document["selections"]["huggingface"]["model_id"] == "openai/gpt-oss-120b"
    assert document["selections"]["local"] is None

    cleared = client.delete("/v1/models/selection/huggingface", headers=_headers())
    assert cleared.status_code == 200 and cleared.json()["selections"]["huggingface"] is None
    assert cleared.json()["modes"]["online"]["available"] is False


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
        response = bare.post("/v1/models/huggingface:discover", headers=_headers())
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
        response = rate_limited.post("/v1/models/huggingface:discover", headers=_headers())
    assert response.status_code == 429
    assert response.json()["code"] == "OAK-MODEL-RATE-LIMITED"
    assert response.json()["retriable"] is True


# ----- regressions found by the Sprint 9 closing audit ------------------------------


def test_an_unchanged_client_keeps_working_after_a_model_is_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`auto` is what a client written before the model path existed sends.

    Once a model was selected, `auto` resolved to the model, which needs the capability
    token — so a caller that had never heard of the token started getting 403 on a call that
    had always worked. With no token, `auto` now means what it always meant.
    """

    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    service = create_model_configuration_service()
    service.set_key("huggingface", validate_key_input(KEY), source="file")
    service.select("huggingface", "openai/gpt-oss-120b")

    plane, _ = build_file_control_plane(tmp_path / "plane")
    app = create_app(
        control_plane=plane,
        model_token=TOKEN,
        model_configuration=create_model_configuration_service,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post(
            "/v1/design-cases",
            headers={"Idempotency-Key": "compat-create-0001"},
            json={"original_name": "brief.md", "content": "A support desk wants drafts."},
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case"]["id"]

        # No interpreter, no token: exactly what the previous client sent.
        answered = client.post(
            f"/v1/design-cases/{case_id}:interpret",
            headers={"Idempotency-Key": "compat-interpret-0001", "If-Match": '"0.1.0"'},
        )

    assert answered.status_code == 200, answered.text
    assert (
        "oak.community/interpretation_proposal_ref" not in answered.json()["intent"]["extensions"]
    )


def test_asking_for_the_model_by_name_still_requires_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    plane, _ = build_file_control_plane(tmp_path / "plane")
    app = create_app(
        control_plane=plane,
        model_token=TOKEN,
        model_configuration=create_model_configuration_service,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post(
            "/v1/design-cases",
            headers={"Idempotency-Key": "explicit-create-0001"},
            json={"original_name": "brief.md", "content": "A support desk wants drafts."},
        )
        case_id = created.json()["case"]["id"]
        refused = client.post(
            f"/v1/design-cases/{case_id}:interpret?interpreter=online",
            headers={"Idempotency-Key": "explicit-interpret-0001", "If-Match": '"0.1.0"'},
        )
    assert refused.status_code == 403
    assert refused.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"


def test_the_document_declares_the_token_required_where_the_server_requires_it(
    client: TestClient,
) -> None:
    """Describing a header as optional while always refusing without it is a false contract."""

    document = client.app.openapi()  # type: ignore[attr-defined]
    for path, method in (
        ("/v1/models", "get"),
        ("/v1/models/credentials/{family}", "put"),
        ("/v1/models/credentials/{family}", "delete"),
        ("/v1/models/selection", "put"),
        ("/v1/models/selection/{family}", "delete"),
        ("/v1/models/{family}:discover", "post"),
        ("/v1/models/{family}:verify", "post"),
    ):
        parameters = document["paths"][path][method]["parameters"]
        token = next(p for p in parameters if p["name"] == "X-OAK-Model-Token")
        assert token["required"] is True, (path, method)


def test_the_status_resource_is_on_the_same_loopback_footing_as_the_rest(
    client: TestClient,
) -> None:
    """It names the store paths and every stored key's fingerprint."""

    from oak.interfaces.api.app import is_credential_route

    assert is_credential_route("/v1/models")
    assert is_credential_route("/v1/models/selection")
    assert is_credential_route("/v1/models/credentials/huggingface")
    assert is_credential_route("/v1/models/huggingface:discover")
    assert not is_credential_route("/v1/design-cases")

    refused = client.get("/v1/models", headers={**_headers(), "Origin": "https://evil.example"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "OAK-ORIGIN-DENIED"


# ----- OAK-S10-004: the verdict on the wire -------------------------------------------------


def test_verification_records_a_verdict_with_its_time_and_never_the_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from oak import bootstrap

    asked: list[str] = []

    def verifier(family: str, *, deadline_seconds: float | None = None) -> dict[str, Any]:
        asked.append(family)
        return {
            "verdict": "accepted",
            "method": "hub_whoami_v2",
            "token_role": "read",
            "inference_permission": True,
            "can_pay": False,
            "is_pro": False,
            "reason": None,
            "email": "sentinel.address.MUST-NOT-BE-STORED@example.invalid",
        }

    monkeypatch.setattr(bootstrap, "model_verifier", verifier)

    refused = client.post("/v1/models/huggingface:verify", headers=_headers())
    assert refused.status_code == 422 and refused.json()["code"] == "OAK-MODEL-KEY-MISSING"
    assert asked == []

    assert _put_key(client).status_code == 204
    verified = client.post("/v1/models/huggingface:verify", headers=_headers())
    assert verified.status_code == 200, verified.text
    assert verified.headers["Cache-Control"] == "no-store"
    assert asked == ["huggingface"]
    assert KEY not in verified.text and "MUST-NOT-BE-STORED" not in verified.text
    row = next(row for row in verified.json()["credentials"] if row["family"] == "huggingface")
    assert row["verification"]["verdict"] == "accepted"
    assert row["verification"]["token_role"] == "read"
    assert row["verification"]["stale"] is False
    assert row["verification"]["checked_at"]
    assert verified.json()["modes"]["online"]["verification"]["verdict"] == "accepted"

    # Storing a key again forgets the verdict: the new key has not been checked.
    assert _put_key(client, key=KEY + "x").status_code == 204
    status = client.get("/v1/models", headers=_headers()).json()
    row = next(row for row in status["credentials"] if row["family"] == "huggingface")
    assert row["verification"] is None
