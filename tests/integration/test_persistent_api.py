# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-005/006 persistent REST and durable worker integration journey."""

import hashlib
import os
from pathlib import Path

import httpx
import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import (
    FileWorkspaceRepository,
    PostgreSQLOperationStore,
    PostgreSQLOutboxStore,
    PostgreSQLWorkspaceRepository,
    create_postgresql_engine,
)
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    CandidatePlanningService,
    CommandContext,
    CommunityControlPlane,
    DesignCaseService,
    OperationService,
    OperationWorker,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import canonical_json_bytes, content_digest
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-17T12:00:00Z"
pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def persistent_control_plane(
    tmp_path: Path,
) -> tuple[CommunityControlPlane, PostgreSQLOperationStore]:
    database_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for persistent API tests")
    engine = create_postgresql_engine(database_url)
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    environment_id = f"api-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]}"
    artifact_root = tmp_path / "artifacts"

    def repository_factory(workspace_id: str, tenant_id: str) -> PostgreSQLWorkspaceRepository:
        return PostgreSQLWorkspaceRepository(
            engine,
            registry,
            artifact_root,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    stores: dict[str, PostgreSQLOperationStore] = {}

    def operation_service_factory(tenant_id: str) -> OperationService:
        store = stores.setdefault(
            tenant_id,
            PostgreSQLOperationStore(
                engine,
                tenant_id=tenant_id,
                environment_id=environment_id,
            ),
        )
        return OperationService(store, environment_id=environment_id)

    control_plane = CommunityControlPlane(
        repository_factory,
        operation_service_factory,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
        lambda tenant_id: PostgreSQLOutboxStore(
            engine,
            tenant_id=tenant_id,
            environment_id=environment_id,
        ),
    )
    store = operation_service_factory("local")._store  # type: ignore[attr-defined]
    assert isinstance(store, PostgreSQLOperationStore)
    yield control_plane, store
    engine.dispose()


def _headers(key: str, version: str | None = None) -> dict[str, str]:
    headers = {
        "Idempotency-Key": key,
        "X-Correlation-ID": f"correlation-{key}",
    }
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


def _context(key: str, version: str | None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


def _file_semantic_journey(tmp_path: Path) -> tuple[dict[str, object], str, str, str]:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(tmp_path / "file-parity", registry)
    design = DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        registry,
    )
    planning = CandidatePlanningService(
        repository,
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )
    design.initialize(
        workspace_id="workspace.public-manual-qa",
        tenant_id="local",
        created_at=NOW,
    )
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context("file-design-public-manual-qa-0001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context("file-confirm-public-manual-qa-0001", "0.1.1"))
    candidates = planning.candidates(_context("file-generate-public-manual-qa-0001", "0.1.2"))
    candidate = next(item for item in candidates.candidates if item["id"] == "candidate-03")
    planning.evaluate("candidate-03", _context("file-evaluate-public-manual-qa-0001", "0.1.3"))
    planning.select(
        "candidate-03",
        "Select the balanced fixture for the bounded REST parity test.",
        _context("file-select-public-manual-qa-0001", "0.1.4"),
    )
    planning.assure("candidate-03", _context("file-assure-public-manual-qa-0001", "0.1.5"))
    planned = planning.plan(
        "candidate-03",
        ROOT / "examples/targets/local-fixture.yaml",
        _context("file-compile-public-manual-qa-0001", "0.1.6"),
    )
    semantic_case = {
        key: planned.case[key]
        for key in (
            "id",
            "version",
            "status",
            "intent_ref",
            "candidate_refs",
            "selected_candidate_ref",
            "assurance_plan_ref",
            "deployment_bundle_ref",
        )
    }
    return (
        semantic_case,
        content_digest(canonical_json_bytes(candidate)),
        content_digest(canonical_json_bytes(planned.deployment_bundle)),
        content_digest(canonical_json_bytes(planned.semantic_manifest)),
    )


async def test_rest_worker_reference_journey_is_durable_idempotent_and_tenant_safe(
    persistent_control_plane: tuple[CommunityControlPlane, PostgreSQLOperationStore],
    tmp_path: Path,
) -> None:
    control_plane, operation_store = persistent_control_plane
    application = create_app(control_plane=control_plane, clock=lambda: NOW)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    target = load_yaml_document(
        (ROOT / "examples/targets/local-fixture.yaml").read_text(encoding="utf-8")
    )
    worker = OperationWorker(
        operation_store,
        {
            "generate_candidates": control_plane.execute_operation,
            "evaluate_candidate": control_plane.execute_operation,
            "compile_bundle": control_plane.execute_operation,
        },
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/design-cases",
            headers=_headers("api-create-public-manual-qa-0001"),
            json={"original_name": "public-manual-qa.yaml", "content": brief},
        )
        assert created.status_code == 201, created.text
        assert created.json()["case"]["status"] == "draft"
        assert created.headers["etag"] == '"0.1.0"'
        duplicate_create = await client.post(
            "/v1/design-cases",
            headers=_headers("api-create-public-manual-qa-0001"),
            json={"original_name": "public-manual-qa.yaml", "content": brief},
        )
        assert duplicate_create.json()["duplicate"] is True

        interpreted = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:interpret",
            headers=_headers("api-interpret-public-manual-qa-0001", "0.1.0"),
        )
        assert interpreted.status_code == 200, interpreted.text
        assert interpreted.json()["case"]["version"] == "0.1.1"
        assert interpreted.json()["intent"]["id"] == "intent.public-manual-qa"

        stale = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:confirm",
            headers=_headers("api-confirm-stale-public-qa-0001", "0.1.0"),
            json={"answers": answers},
        )
        assert stale.status_code == 409
        assert stale.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        assert stale.json()["code"] == "OAK-EXPECTED-VERSION"
        assert stale.json()["correlation_id"] == "correlation-api-confirm-stale-public-qa-0001"

        confirmed = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:confirm",
            headers=_headers("api-confirm-public-manual-qa-0001", "0.1.1"),
            json={"answers": answers},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["case"]["status"] == "ready_for_candidates"

        generated = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:generate-candidates",
            headers=_headers("api-generate-public-manual-qa-0001", "0.1.2"),
        )
        assert generated.status_code == 202, generated.text
        generated_operation = generated.json()["operation_id"]
        generated_retry = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:generate-candidates",
            headers=_headers("api-generate-public-manual-qa-0001", "0.1.2"),
        )
        assert generated_retry.json()["operation_id"] == generated_operation
        assert generated_retry.json()["duplicate"] is True
        completed = worker.run_once(
            worker_id="api-worker-a",
            now="2026-08-17T12:00:01Z",
            lease_expires_at="2026-08-17T12:01:01Z",
        )
        assert completed is not None and completed.state == "succeeded"
        operation_status = await client.get(f"/v1/operations/{generated_operation}")
        assert operation_status.json()["state"] == "succeeded"
        completed_retry_headers = _headers("api-generate-public-manual-qa-0001", "0.1.2")
        completed_retry_headers["X-Correlation-ID"] = "correlation-completed-retry-0001"
        completed_retry = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:generate-candidates",
            headers=completed_retry_headers,
        )
        assert completed_retry.status_code == 202
        assert completed_retry.json()["operation_id"] == generated_operation
        assert completed_retry.json()["duplicate"] is True
        candidates = await client.get(
            "/v1/design-cases/design-case.public-manual-qa/candidates?limit=2"
        )
        assert candidates.status_code == 200
        assert len(candidates.json()["items"]) == 2
        assert candidates.json()["next_cursor"] is not None

        evaluation = await client.post(
            "/v1/candidates/candidate-03:evaluate",
            headers=_headers("api-evaluate-public-manual-qa-0001", "0.1.3"),
            json={"case_id": "design-case.public-manual-qa"},
        )
        assert evaluation.status_code == 202, evaluation.text
        evaluated = worker.run_once(
            worker_id="api-worker-b",
            now="2026-08-17T12:00:02Z",
            lease_expires_at="2026-08-17T12:01:02Z",
        )
        assert evaluated is not None and evaluated.state == "succeeded"

        selected = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:select-candidate",
            headers=_headers("api-select-public-manual-qa-0001", "0.1.4"),
            json={
                "candidate_id": "candidate-03",
                "rationale": "Select the balanced fixture for the bounded REST parity test.",
            },
        )
        assert selected.status_code == 200, selected.text
        assured = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:create-assurance-plan",
            headers=_headers("api-assure-public-manual-qa-0001", "0.1.5"),
            json={"candidate_id": "candidate-03"},
        )
        assert assured.status_code == 200, assured.text
        compiled = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:compile",
            headers=_headers("api-compile-public-manual-qa-0001", "0.1.6"),
            json={"candidate_id": "candidate-03", "target": target},
        )
        assert compiled.status_code == 202, compiled.text
        planned = worker.run_once(
            worker_id="api-worker-c",
            now="2026-08-17T12:00:03Z",
            lease_expires_at="2026-08-17T12:01:03Z",
        )
        assert planned is not None and planned.state == "succeeded"

        final_case = await client.get("/v1/design-cases/design-case.public-manual-qa")
        assert final_case.status_code == 200
        assert final_case.json()["case"]["status"] == "bundle_compiled"
        assert final_case.headers["etag"] == '"0.1.7"'
        outbox_lag = await client.get("/v1/system/outbox-lag")
        assert outbox_lag.status_code == 200
        assert outbox_lag.json()["pending_events"] == 8
        assert outbox_lag.json()["sequence_lag"] == 8
        local_case, local_candidate_digest, local_bundle_digest, local_semantic_digest = (
            _file_semantic_journey(tmp_path)
        )
        rest_case = final_case.json()["case"]
        rest_semantic_case = {key: rest_case[key] for key in local_case}
        assert rest_semantic_case == local_case
        rest_candidates = (
            await client.get("/v1/design-cases/design-case.public-manual-qa/candidates?limit=100")
        ).json()["items"]
        rest_candidate = next(item for item in rest_candidates if item["id"] == "candidate-03")
        assert content_digest(canonical_json_bytes(rest_candidate)) == local_candidate_digest
        assert rest_case["deployment_bundle_ref"]["digest"] == local_bundle_digest
        assert (
            rest_case["extensions"]["oak.community/semantic_manifest_ref"]["digest"]
            == local_semantic_digest
        )
        artifacts = await client.get(
            "/v1/design-cases/design-case.public-manual-qa/artifacts?limit=100"
        )
        assert artifacts.status_code == 200
        assert len(artifacts.json()["items"]) > 20
        artifact_entry = artifacts.json()["items"][0]
        artifact_content = await client.get(
            "/v1/design-cases/design-case.public-manual-qa/artifacts/" + artifact_entry["id"],
            params={
                "version": artifact_entry["version"],
                "digest": artifact_entry["digest"],
            },
        )
        assert artifact_content.status_code == 200
        assert artifact_content.headers["x-oak-artifact-digest"] == artifact_entry["digest"]

        exported = await client.get("/v1/design-cases/design-case.public-manual-qa/export")
        assert exported.status_code == 200, exported.text
        imported_retry = await client.post(
            "/v1/design-cases:import",
            headers=_headers("api-import-public-manual-qa-0001"),
            json=exported.json(),
        )
        assert imported_retry.status_code == 201, imported_retry.text
        assert imported_retry.json()["duplicate"] is True
        assert imported_retry.json()["case"] == final_case.json()["case"]

        tampered_export = exported.json()
        tampered_export["objects"][0]["content_base64"] = "AAAA"
        tampered = await client.post(
            "/v1/design-cases:import",
            headers=_headers("api-import-tampered-public-qa-0001"),
            json=tampered_export,
        )
        assert tampered.status_code == 422
        assert tampered.json()["code"] == "OAK-IMPORT-DIGEST"

        denied = await client.get(
            "/v1/design-cases/design-case.public-manual-qa",
            headers={"X-OAK-Tenant": "different-tenant"},
        )
        missing = await client.get("/v1/design-cases/design-case.missing")
        assert denied.status_code == missing.status_code == 404
        assert denied.json()["detail"] == missing.json()["detail"]


async def test_rest_cancellation_records_full_command_context(
    persistent_control_plane: tuple[CommunityControlPlane, PostgreSQLOperationStore],
) -> None:
    control_plane, operation_store = persistent_control_plane
    application = create_app(control_plane=control_plane, clock=lambda: NOW)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/design-cases",
            headers=_headers("api-cancel-create-public-qa-0001"),
            json={"original_name": "public-manual-qa.yaml", "content": brief},
        )
        await client.post(
            "/v1/design-cases/design-case.public-manual-qa:interpret",
            headers=_headers("api-cancel-interpret-public-qa-0001", "0.1.0"),
        )
        submitted = await client.post(
            "/v1/design-cases/design-case.public-manual-qa:generate-candidates",
            headers=_headers("api-cancel-generate-public-qa-0001", "0.1.1"),
        )
        operation_id = submitted.json()["operation_id"]
        cancelled = await client.post(
            f"/v1/operations/{operation_id}:cancel",
            headers=_headers("api-cancel-operation-public-qa-0001"),
        )

    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    record = operation_store.get(operation_id)
    assert record.cancel_requested_by == "local-user"
    assert record.cancel_idempotency_key == "api-cancel-operation-public-qa-0001"
    assert record.cancel_correlation_id == "correlation-api-cancel-operation-public-qa-0001"
    assert record.cancel_requested_at == NOW
