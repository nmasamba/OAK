# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-002: backup, restore and upgrade limits, proven rather than asserted.

The documented recovery posture is restore-forward: never downgrade, restore a backup
into a clean database and migrate up. Two things about it were previously only prose.

First, the refusal itself. `downgrade()` raising is the whole mechanism preventing a
destructive rollback, and nothing pinned it, so deleting the raise would have been a
silent, passing change.

Second, and more consequential: artifact bytes are read **only** from the artifact root.
The JSONB copy in `artifact_versions.canonical_document` is never read back at runtime.
A restore that follows the old `migrations/README.md` — which documented `pg_dump` and
nothing else — therefore produces a database indexing artifacts that are not on disk,
and every read fails later at use time rather than at restore time. These tests
reproduce that exact half-restore and require it to be detected.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.contracts import SchemaRegistry
from oak.domain import OAKError

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify_deployment.py"
BASELINE_REVISION = "0001_sprint3_baseline"

EXIT_OK = 0
EXIT_CORRUPT = 2
EXIT_UNREADABLE = 3

pytestmark = pytest.mark.integration


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _verify(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A file workspace holding one real compiled reference case."""

    from tests.runner_support import build_compiled_case

    harness = build_compiled_case(tmp_path)
    return harness.workspace


def test_a_healthy_workspace_verifies(workspace: Path) -> None:
    result = _verify("--workspace", str(workspace))

    assert result.returncode == EXIT_OK, result.stderr
    assert "every object present" in result.stdout


def test_a_missing_artifact_object_is_detected(workspace: Path) -> None:
    """The failure mode a partial restore actually produces."""

    objects = sorted((workspace / ".oak" / "objects" / "sha256").iterdir())
    objects[0].unlink()

    result = _verify("--workspace", str(workspace))

    assert result.returncode == EXIT_CORRUPT
    assert "object missing from the store" in result.stderr


def test_a_silently_altered_artifact_object_is_detected(workspace: Path) -> None:
    """Same length, different bytes: only a digest check catches this."""

    objects = sorted((workspace / ".oak" / "objects" / "sha256").iterdir())
    target = objects[0]
    original = target.read_bytes()
    target.write_bytes(b"X" + original[1:])

    result = _verify("--workspace", str(workspace))

    assert result.returncode == EXIT_CORRUPT
    assert "digest is" in result.stderr


def test_a_truncated_artifact_object_is_detected(workspace: Path) -> None:
    objects = sorted((workspace / ".oak" / "objects" / "sha256").iterdir())
    target = objects[0]
    target.write_bytes(target.read_bytes()[:-1])

    result = _verify("--workspace", str(workspace))

    assert result.returncode == EXIT_CORRUPT
    assert "size is" in result.stderr


def test_an_unreadable_deployment_reports_rather_than_tracebacks(tmp_path: Path) -> None:
    result = _verify("--workspace", str(tmp_path / "not-a-workspace"))

    assert result.returncode == EXIT_UNREADABLE
    assert "could not read the deployment" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_database_without_its_artifact_root_is_refused(tmp_path: Path) -> None:
    """`--database-url` alone is not a deployment, and the tool says so."""

    result = _verify("--database-url", "postgresql+psycopg://x/y")

    assert result.returncode != EXIT_OK
    assert "not a deployment" in (result.stderr + result.stdout)


def test_export_and_reimport_reconstructs_a_verifiable_workspace(
    workspace: Path, tmp_path: Path
) -> None:
    """Canonical export is the portability path; prove a round trip is intact.

    This is the documented way to move a workspace between machines and across a
    format change, so the restored copy must verify on its own terms.
    """

    registry = _registry()
    source = FileWorkspaceRepository(workspace, registry)
    export_root = tmp_path / "export"
    source.export_to(export_root)

    restored_root = tmp_path / "restored"
    restored = FileWorkspaceRepository(restored_root, registry)
    restored.import_from(export_root)

    result = _verify("--workspace", str(restored_root))
    assert result.returncode == EXIT_OK, result.stderr

    original_manifest = json.loads(
        (workspace / ".oak" / "manifest.json").read_text(encoding="utf-8")
    )
    restored_manifest = json.loads(
        (restored_root / ".oak" / "manifest.json").read_text(encoding="utf-8")
    )
    assert restored_manifest["artifact_index"] == original_manifest["artifact_index"]
    assert restored_manifest["current_case_ref"] == original_manifest["current_case_ref"]


def test_a_workspace_written_by_an_unknown_format_fails_closed(
    workspace: Path,
) -> None:
    """The upgrade rule for file mode, made explicit.

    There is no file-workspace format migration. A manifest carrying a
    `schema_version` this build does not know is refused — and, importantly, it is
    refused on *export* too, so a workspace cannot be rescued after the fact. That is
    why the operator documentation says export before upgrading, and why it is a
    documented limitation rather than a silent one.
    """

    manifest_path = workspace / ".oak" / "manifest.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "9.9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    repository = FileWorkspaceRepository(workspace, _registry())
    with pytest.raises(OAKError) as refusal:
        repository.manifest()

    assert refusal.value.code == "OAK-WORKSPACE-CORRUPT"


def test_the_alembic_baseline_refuses_to_downgrade() -> None:
    """Restore-forward is enforced by this raise and nothing else.

    Nothing pinned it, so removing the raise and issuing destructive DDL instead
    would have been a silent, passing change.
    """

    module_path = ROOT / "migrations" / "versions" / f"{BASELINE_REVISION}.py"
    specification = importlib.util.spec_from_file_location(
        "oak_test_baseline_migration", module_path
    )
    assert specification is not None and specification.loader is not None
    migration = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(migration)

    assert migration.down_revision is None, "the baseline must have no prior revision"

    with pytest.raises(RuntimeError) as refusal:
        migration.downgrade()

    assert "forward-only" in str(refusal.value)


@pytest.fixture
def restored_database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A clean, migrated database, which is what restore-forward actually starts from.

    The documented recovery path is "create a clean database, restore the backup into
    it, then run `oak-db-migrate`". Rehearsing against the shared development database
    would prove something weaker and would leave rows behind, so this creates and drops
    a scratch database per test.
    """

    admin_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for PostgreSQL restore tests")

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from oak.interfaces.migrations import canonical_migration_directory

    name = f"oak_restore_rehearsal_{uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    scratch_url = admin_url.rsplit("/", 1)[0] + f"/{name}"

    configuration = Config()
    configuration.set_main_option("script_location", str(canonical_migration_directory()))
    configuration.set_main_option("sqlalchemy.url", scratch_url.replace("%", "%%"))
    # `migrations/env.py` reads OAK_DATABASE_URL directly and ignores the config option
    # that `oak-db-migrate` sets, so the environment is what actually selects the target.
    monkeypatch.setenv("OAK_DATABASE_URL", scratch_url)
    command.upgrade(configuration, "head")

    try:
        yield scratch_url
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def test_a_clean_database_migrates_to_head_and_verifies_empty(
    restored_database_url: str, tmp_path: Path
) -> None:
    """The first half of restore-forward: migrations apply to an empty database."""

    from sqlalchemy import create_engine, text

    engine = create_engine(restored_database_url)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert revision == BASELINE_REVISION

    empty_root = tmp_path / "artifacts"
    empty_root.mkdir()
    result = _verify("--database-url", restored_database_url, "--artifact-root", str(empty_root))

    assert result.returncode == EXIT_OK, result.stderr
    assert "no indexed artifacts" in result.stdout


def test_a_postgresql_deployment_restored_without_its_artifact_root_is_detected(
    restored_database_url: str, tmp_path: Path
) -> None:
    """The half-restore the previous documentation would have produced.

    Written state goes into both the database and the artifact root. Restoring only
    the database — which is what a `pg_dump`-only procedure gives you — leaves every
    indexed artifact unreadable, and this must be detected at restore time.
    """

    from oak.adapters.persistence import PostgreSQLWorkspaceRepository, create_postgresql_engine
    from tests.integration.workspace_contract_support import NOW, initial_mutation

    engine = create_postgresql_engine(restored_database_url)
    registry = _registry()
    artifact_root = tmp_path / "artifacts"
    environment_id = "test-restore-rehearsal"
    workspace_id = "workspace.restore-rehearsal"

    repository = PostgreSQLWorkspaceRepository(
        engine,
        registry,
        artifact_root,
        workspace_id=workspace_id,
        tenant_id="local",
        environment_id=environment_id,
    )
    repository.initialize(workspace_id=workspace_id, tenant_id="local", created_at=NOW)
    repository.commit(initial_mutation(workspace_id=workspace_id))

    intact = _verify("--database-url", restored_database_url, "--artifact-root", str(artifact_root))
    assert intact.returncode == EXIT_OK, intact.stderr

    # Simulate restoring the database into a host whose artifact root was not restored.
    empty_root = tmp_path / "artifacts-not-restored"
    empty_root.mkdir()
    half = _verify("--database-url", restored_database_url, "--artifact-root", str(empty_root))

    assert half.returncode == EXIT_CORRUPT
    assert "object missing from the store" in half.stderr
    assert "not from the same backup" in half.stderr


def test_the_artifact_root_alone_detects_bit_rot(
    restored_database_url: str, tmp_path: Path
) -> None:
    """A restored object that is present but wrong must not pass as intact."""

    from oak.adapters.persistence import PostgreSQLWorkspaceRepository, create_postgresql_engine
    from tests.integration.workspace_contract_support import NOW, initial_mutation

    engine = create_postgresql_engine(restored_database_url)
    artifact_root = tmp_path / "artifacts"
    environment_id = "test-restore-bitrot"
    workspace_id = "workspace.restore-bitrot"

    repository = PostgreSQLWorkspaceRepository(
        engine,
        _registry(),
        artifact_root,
        workspace_id=workspace_id,
        tenant_id="local",
        environment_id=environment_id,
    )
    repository.initialize(workspace_id=workspace_id, tenant_id="local", created_at=NOW)
    repository.commit(initial_mutation(workspace_id=workspace_id))

    objects = sorted((artifact_root / "sha256").iterdir())
    assert objects, "the rehearsal wrote no artifact objects"
    corrupted = objects[0]
    payload = corrupted.read_bytes()
    corrupted.write_bytes(b"X" + payload[1:])

    result = _verify("--database-url", restored_database_url, "--artifact-root", str(artifact_root))

    assert result.returncode == EXIT_CORRUPT
    assert hashlib.sha256(payload).hexdigest() in result.stderr
