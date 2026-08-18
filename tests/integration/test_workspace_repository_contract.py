# SPDX-License-Identifier: Apache-2.0
"""OAK-S3-001/002 shared file/PostgreSQL repository transaction contract."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import (
    FileWorkspaceRepository,
    PostgreSQLOutboxStore,
    PostgreSQLWorkspaceRepository,
    create_postgresql_engine,
)
from oak.application import CommandContext, DesignCaseService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError
from oak.ports import WorkspaceRepository
from tests.integration.workspace_contract_support import NOW, initial_mutation

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class RepositoryHarness:
    backend: str
    repository: WorkspaceRepository
    reopen: Callable[[], WorkspaceRepository]
    failing: Callable[[], WorkspaceRepository]
    engine: Engine | None = None
    workspace_id: str = "workspace.workspace-test"
    environment_id: str = "local"
    artifact_root: Path | None = None


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _design_service(repository: WorkspaceRepository) -> DesignCaseService:
    return DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        _registry(),
    )


def _context(*, key: str, expected_version: str | None, occurred_at: str) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=expected_version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=occurred_at,
    )


@pytest.fixture(params=("file", "postgresql"))
def repository_harness(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[RepositoryHarness]:
    suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
    workspace_id = f"workspace.contract-{suffix}"
    if request.param == "file":
        root = tmp_path / "workspace"

        def reopen() -> WorkspaceRepository:
            return FileWorkspaceRepository(root, _registry())

        repository = reopen()
        repository.initialize(workspace_id=workspace_id, tenant_id="local", created_at=NOW)

        def failing() -> WorkspaceRepository:
            def fail_replace(_source: Path, _destination: Path) -> None:
                raise RuntimeError("injected transaction failure")

            return FileWorkspaceRepository(root, _registry(), replace_file=fail_replace)

        yield RepositoryHarness("file", repository, reopen, failing, workspace_id=workspace_id)
        return

    database_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for PostgreSQL contract tests")
    engine = create_postgresql_engine(database_url)
    artifact_root = tmp_path / "postgres-artifacts"
    environment_id = f"test-{suffix}"

    def reopen_postgresql() -> WorkspaceRepository:
        return PostgreSQLWorkspaceRepository(
            engine,
            _registry(),
            artifact_root,
            workspace_id=workspace_id,
            tenant_id="local",
            environment_id=environment_id,
        )

    repository = reopen_postgresql()
    repository.initialize(workspace_id=workspace_id, tenant_id="local", created_at=NOW)

    def failing_postgresql() -> WorkspaceRepository:
        def fail_before_commit(_connection: Any, _mutation: Any) -> None:
            raise RuntimeError("injected transaction failure")

        return PostgreSQLWorkspaceRepository(
            engine,
            _registry(),
            artifact_root,
            workspace_id=workspace_id,
            tenant_id="local",
            environment_id=environment_id,
            before_commit=fail_before_commit,
        )

    try:
        yield RepositoryHarness(
            "postgresql",
            repository,
            reopen_postgresql,
            failing_postgresql,
            engine=engine,
            workspace_id=workspace_id,
            environment_id=environment_id,
            artifact_root=artifact_root,
        )
    finally:
        engine.dispose()


def test_shared_repository_contract_retry_restart_and_digest_lineage(
    repository_harness: RepositoryHarness,
) -> None:
    mutation = initial_mutation(workspace_id=repository_harness.workspace_id)

    first = repository_harness.repository.commit(mutation)
    retry = repository_harness.repository.commit(mutation)
    restarted = repository_harness.reopen()

    assert first.duplicate is False
    assert retry.duplicate is True
    assert retry.case_document == first.case_document
    assert restarted.current_case() == first.case_document
    assert restarted.read_artifact(mutation.current_case_ref) == mutation.artifacts[-1].content
    manifest = restarted.manifest()
    assert manifest["version"] == 1
    assert manifest["current_case_ref"]["digest"] == mutation.current_case_ref.digest
    assert manifest["audit_events"] == [mutation.event_ref.to_document()]
    assert len(manifest["idempotency_records"]) == 1

    with pytest.raises(OAKError) as reused:
        restarted.commit(
            initial_mutation(
                workspace_id=repository_harness.workspace_id,
                idempotency_key=mutation.idempotency_key,
                input_digest=f"sha256:{'2' * 64}",
            )
        )
    assert reused.value.code == "OAK-IDEMPOTENCY-CONFLICT"

    with pytest.raises(OAKError) as stale:
        restarted.commit(
            initial_mutation(
                workspace_id=repository_harness.workspace_id,
                idempotency_key="design-workspace-test-0002",
                input_digest=f"sha256:{'3' * 64}",
            )
        )
    assert stale.value.code == "OAK-EXPECTED-VERSION"


def test_shared_repository_contract_failed_publication_rolls_back(
    repository_harness: RepositoryHarness,
) -> None:
    before = repository_harness.repository.manifest()

    with pytest.raises(RuntimeError, match="injected transaction failure"):
        repository_harness.failing().commit(
            initial_mutation(workspace_id=repository_harness.workspace_id)
        )

    restarted = repository_harness.reopen()
    assert restarted.manifest() == before
    assert restarted.current_case() is None
    if isinstance(restarted, PostgreSQLWorkspaceRepository):
        assert restarted.transaction_counts() == {
            "artifact_versions": 0,
            "design_case_versions": 0,
            "design_case_heads": 0,
            "transitions": 0,
            "idempotency_records": 0,
            "outbox_events": 0,
        }


def _concurrent_commit(
    repository: WorkspaceRepository, workspace_id: str, key: str, character: str
) -> str:
    try:
        repository.commit(
            initial_mutation(
                workspace_id=workspace_id,
                idempotency_key=key,
                input_digest=f"sha256:{character * 64}",
            )
        )
    except OAKError as error:
        return error.code
    return "committed"


def test_shared_repository_contract_serializes_concurrent_first_writers(
    repository_harness: RepositoryHarness,
) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                _concurrent_commit,
                [repository_harness.reopen(), repository_harness.reopen()],
                [repository_harness.workspace_id, repository_harness.workspace_id],
                ["design-workspace-test-0001", "design-workspace-test-0002"],
                ["1", "2"],
            )
        )

    assert sorted(outcomes) == ["OAK-EXPECTED-VERSION", "committed"]
    manifest = repository_harness.reopen().manifest()
    assert manifest["version"] == 1
    assert len(manifest["audit_events"]) == 1


def test_postgresql_baseline_outbox_atomicity_and_scope(
    repository_harness: RepositoryHarness,
) -> None:
    if repository_harness.backend != "postgresql":
        pytest.skip("PostgreSQL-specific normalized transaction assertion")
    assert repository_harness.engine is not None
    assert repository_harness.artifact_root is not None
    repository = repository_harness.repository
    assert isinstance(repository, PostgreSQLWorkspaceRepository)

    repository.commit(initial_mutation(workspace_id=repository_harness.workspace_id))

    assert repository.transaction_counts() == {
        "artifact_versions": 3,
        "design_case_versions": 1,
        "design_case_heads": 1,
        "transitions": 1,
        "idempotency_records": 1,
        "outbox_events": 1,
    }
    with repository_harness.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0001_sprint3_baseline"
        )
        outbox = (
            connection.execute(
                text(
                    "SELECT event_id, aggregate_sequence, payload_digest, delivery_attempts "
                    "FROM outbox_events WHERE tenant_id = :tenant_id "
                    "AND environment_id = :environment_id AND workspace_id = :workspace_id"
                ),
                {
                    "tenant_id": "local",
                    "environment_id": repository_harness.environment_id,
                    "workspace_id": repository_harness.workspace_id,
                },
            )
            .mappings()
            .one()
        )
    mutation = initial_mutation(workspace_id=repository_harness.workspace_id)
    assert outbox == {
        "event_id": mutation.event.event_id,
        "aggregate_sequence": 1,
        "payload_digest": mutation.event_ref.digest,
        "delivery_attempts": 0,
    }

    other_tenant = PostgreSQLWorkspaceRepository(
        repository_harness.engine,
        _registry(),
        repository_harness.artifact_root,
        workspace_id=repository_harness.workspace_id,
        tenant_id="tenant-b",
        environment_id=repository_harness.environment_id,
    )
    with pytest.raises(OAKError) as denied:
        other_tenant.manifest()
    assert denied.value.code == "OAK-WORKSPACE-NOT-FOUND"

    other_environment = PostgreSQLWorkspaceRepository(
        repository_harness.engine,
        _registry(),
        repository_harness.artifact_root,
        workspace_id=repository_harness.workspace_id,
        tenant_id="local",
        environment_id="environment-b",
    )
    with pytest.raises(OAKError) as environment_denied:
        other_environment.current_case()
    assert environment_denied.value.code == "OAK-WORKSPACE-NOT-FOUND"


def test_postgresql_application_contract_matches_file_digest_lineage(
    repository_harness: RepositoryHarness,
) -> None:
    if repository_harness.backend != "postgresql":
        pytest.skip("PostgreSQL/file application parity assertion")
    assert repository_harness.artifact_root is not None

    file_repository = FileWorkspaceRepository(
        repository_harness.artifact_root.parent / "file-parity", _registry()
    )
    file_repository.initialize(
        workspace_id=repository_harness.workspace_id,
        tenant_id="local",
        created_at=NOW,
    )
    postgres_service = _design_service(repository_harness.repository)
    file_service = _design_service(file_repository)
    design_context = _context(
        key="design-public-manual-qa-0001",
        expected_version=None,
        occurred_at=NOW,
    )
    brief = ROOT / "examples/briefs/public-manual-qa.yaml"

    postgres_design = postgres_service.design(brief, design_context)
    file_design = file_service.design(brief, design_context)

    assert postgres_design.case == file_design.case
    assert postgres_design.intent == file_design.intent
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    confirm_context = _context(
        key="confirm-public-manual-qa-0001",
        expected_version="0.1.1",
        occurred_at="2026-08-17T10:05:00Z",
    )

    postgres_confirm = postgres_service.confirm(answers, confirm_context)
    file_confirm = file_service.confirm(answers, confirm_context)

    assert postgres_confirm.case == file_confirm.case
    assert postgres_confirm.intent == file_confirm.intent
    postgres_manifest = repository_harness.reopen().manifest()
    file_manifest = file_repository.manifest()
    for field in (
        "version",
        "current_case_ref",
        "artifact_index",
        "audit_events",
        "idempotency_records",
    ):
        assert postgres_manifest[field] == file_manifest[field]
    assert len(postgres_manifest["audit_events"]) == 3
    assert repository_harness.reopen().current_case() == file_repository.current_case()


def test_postgresql_outbox_redelivery_deduplication_and_lag(
    repository_harness: RepositoryHarness,
) -> None:
    if repository_harness.backend != "postgresql":
        pytest.skip("PostgreSQL outbox assertion")
    assert repository_harness.engine is not None
    repository_harness.repository.commit(
        initial_mutation(workspace_id=repository_harness.workspace_id)
    )
    store = PostgreSQLOutboxStore(
        repository_harness.engine,
        tenant_id="local",
        environment_id=repository_harness.environment_id,
    )

    initial_lag = store.lag(projection_name="case-index")
    assert initial_lag.pending_events >= 1
    assert initial_lag.latest_sequence == 1
    assert initial_lag.indexed_through == 0
    assert initial_lag.sequence_lag == 1

    first_claim = store.claim(
        consumer_id="outbox-worker-a",
        now="2026-08-17T10:01:00Z",
        lease_expires_at="2026-08-17T10:02:00Z",
        limit=1,
    )
    assert len(first_claim) == 1
    assert first_claim[0].delivery_attempts == 1
    assert (
        store.claim(
            consumer_id="outbox-worker-b",
            now="2026-08-17T10:01:30Z",
            lease_expires_at="2026-08-17T10:02:30Z",
            limit=1,
        )
        == ()
    )

    restarted = PostgreSQLOutboxStore(
        repository_harness.engine,
        tenant_id="local",
        environment_id=repository_harness.environment_id,
    )
    redelivered = restarted.claim(
        consumer_id="outbox-worker-b",
        now="2026-08-17T10:03:00Z",
        lease_expires_at="2026-08-17T10:04:00Z",
        limit=1,
    )
    assert len(redelivered) == 1
    assert redelivered[0].event_id == first_claim[0].event_id
    assert redelivered[0].delivery_attempts == 2
    assert restarted.record_consumed(
        redelivered[0],
        projection_name="case-index",
        processed_at="2026-08-17T10:03:10Z",
    )
    assert not restarted.record_consumed(
        redelivered[0],
        projection_name="case-index",
        processed_at="2026-08-17T10:03:11Z",
    )
    restarted.mark_delivered(
        redelivered[0],
        consumer_id="outbox-worker-b",
        delivered_at="2026-08-17T10:03:12Z",
    )

    final_lag = restarted.lag(projection_name="case-index")
    assert final_lag.pending_events == 0
    assert final_lag.oldest_pending_at is None
    assert final_lag.latest_sequence == 1
    assert final_lag.indexed_through == 1
    assert final_lag.sequence_lag == 0


def test_postgresql_export_restores_to_file_and_fresh_postgresql_scope(
    repository_harness: RepositoryHarness,
) -> None:
    if repository_harness.backend != "postgresql":
        pytest.skip("PostgreSQL portability assertion")
    assert repository_harness.engine is not None
    assert repository_harness.artifact_root is not None
    service = _design_service(repository_harness.repository)
    service.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(
            key="export-restore-public-manual-qa-0001",
            expected_version=None,
            occurred_at=NOW,
        ),
    )
    export = repository_harness.artifact_root.parent / "postgres-export"

    repository_harness.repository.export_to(export)

    file_repository = FileWorkspaceRepository(
        repository_harness.artifact_root.parent / "restored-file", _registry()
    )
    file_repository.import_from(export)
    source_manifest = repository_harness.repository.manifest()
    assert file_repository.manifest() == source_manifest

    restored_environment = f"{repository_harness.environment_id}-restored"
    restored_repository = PostgreSQLWorkspaceRepository(
        repository_harness.engine,
        _registry(),
        repository_harness.artifact_root.parent / "restored-postgres-objects",
        workspace_id=repository_harness.workspace_id,
        tenant_id="local",
        environment_id=restored_environment,
    )
    restored_repository.import_from(export)
    assert restored_repository.manifest() == source_manifest
    assert restored_repository.current_case() == repository_harness.repository.current_case()
    assert restored_repository.transaction_counts() == {
        "artifact_versions": 7,
        "design_case_versions": 2,
        "design_case_heads": 1,
        "transitions": 2,
        "idempotency_records": 2,
        "outbox_events": 2,
    }

    source_outbox = PostgreSQLOutboxStore(
        repository_harness.engine,
        tenant_id="local",
        environment_id=repository_harness.environment_id,
    )
    restored_outbox = PostgreSQLOutboxStore(
        repository_harness.engine,
        tenant_id="local",
        environment_id=restored_environment,
    )
    source_events = source_outbox.claim(
        consumer_id="source-export-check",
        now="2026-08-17T10:01:00Z",
        lease_expires_at="2026-08-17T10:02:00Z",
        limit=100,
    )
    restored_events = restored_outbox.claim(
        consumer_id="restored-export-check",
        now="2026-08-17T10:01:00Z",
        lease_expires_at="2026-08-17T10:02:00Z",
        limit=100,
    )
    assert [event.event_id for event in restored_events] == [
        event.event_id for event in source_events
    ]
