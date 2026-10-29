# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-029 (RR-017): a file workspace at an older format is refused, exported as it
is, imported as it is, and carried forward only by `oak workspace migrate`, once.

The chain the package ships holds no step, so these tests install the synthetic
format 0.3.9 from `tests/workspace_format_support.py` into every bootstrap factory.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.context import CommandContext
from oak.application.workspace_format import WorkspaceFormatService
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from oak.domain.workspace_format import (
    CURRENT_MANIFEST_FORMAT,
    MIGRATION_EXTENSION,
    FormatChain,
    FormatStep,
    StepResult,
)
from oak.interfaces.cli.main import app as cli_app
from tests.workspace_format_support import (
    LABEL_KEY,
    LEGACY_FORMAT,
    MIGRATED_FROM_KEY,
    STEP_NAME,
    SYNTHETIC_CHAIN,
    install_synthetic_chain,
    write_legacy_workspace,
)

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()

pytestmark = pytest.mark.integration


def _output(result) -> str:  # type: ignore[no-untyped-def]
    return str(result.output) + str(result.stderr or "")


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _manifest(workspace: Path) -> dict[str, Any]:
    return json.loads((workspace / ".oak" / "manifest.json").read_bytes())


def _objects(workspace: Path) -> dict[str, bytes]:
    objects = workspace / ".oak" / "objects" / "sha256"
    return {path.name: path.read_bytes() for path in sorted(objects.iterdir())}


def _oak(*arguments: str, cwd: Path) -> Any:
    previous = Path.cwd()
    os.chdir(cwd)
    try:
        return runner.invoke(cli_app, list(arguments))
    finally:
        os.chdir(previous)


def _context(stamp: str = "2026-10-29T12:00:00Z") -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key="",
        expected_version=None,
        correlation_id="",
        interface_origin="cli",
        occurred_at=stamp,
    )


@pytest.fixture(scope="module")
def compiled(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real compiled reference case, copied per test."""

    from tests.runner_support import build_compiled_case

    return build_compiled_case(tmp_path_factory.mktemp("compiled")).workspace


@pytest.fixture
def current(compiled: Path, tmp_path: Path) -> Path:
    workspace = tmp_path / "current"
    shutil.copytree(compiled, workspace)
    return workspace


@pytest.fixture
def legacy(compiled: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "legacy"
    shutil.copytree(compiled, workspace)
    write_legacy_workspace(workspace)
    install_synthetic_chain(monkeypatch)
    monkeypatch.delenv("OAK_SERVER", raising=False)
    return workspace


def test_a_current_workspace_reports_so_and_migrates_as_a_no_op(
    current: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    before = (current / ".oak" / "manifest.json").read_bytes()

    status = _oak("workspace", "status", "--output", "json", cwd=current)
    assert status.exit_code == 0, _output(status)
    report = json.loads(status.stdout)
    assert report["format"] == CURRENT_MANIFEST_FORMAT
    assert report["current"] is True and report["known"] is True
    assert report["migration_steps"] == []
    assert report["known_formats"] == [CURRENT_MANIFEST_FORMAT]

    migrated = _oak("workspace", "migrate", "--output", "json", cwd=current)
    assert migrated.exit_code == 0, _output(migrated)
    assert json.loads(migrated.stdout)["changed"] is False
    assert (current / ".oak" / "manifest.json").read_bytes() == before


def test_an_older_format_is_refused_on_every_command_but_status_and_export(
    legacy: Path, tmp_path: Path
) -> None:
    repository = FileWorkspaceRepository(legacy, _registry(), chain=SYNTHETIC_CHAIN)
    for read in (repository.manifest, repository.current_case):
        with pytest.raises(OAKError) as refusal:
            read()
        assert refusal.value.code == "OAK-WORKSPACE-MIGRATE"
    for command in (["questions"], ["architecture"], ["candidates"]):
        refused = _oak(*command, cwd=legacy)
        assert refused.exit_code == 2, _output(refused)
        assert "OAK-WORKSPACE-MIGRATE" in _output(refused)
        assert "oak workspace migrate" in _output(refused)

    status = _oak("workspace", "status", "--output", "json", cwd=legacy)
    assert status.exit_code == 0, _output(status)
    report = json.loads(status.stdout)
    assert report["format"] == LEGACY_FORMAT and report["current"] is False
    assert report["known"] is True and report["migration_steps"] == [STEP_NAME]

    # Export copies the workspace as it is: the manifest byte for byte, every object.
    export = tmp_path / "export"
    exported = _oak("export", "--output", str(export), cwd=legacy)
    assert exported.exit_code == 0, _output(exported)
    assert (export / "manifest.json").read_bytes() == (
        legacy / ".oak" / "manifest.json"
    ).read_bytes()
    assert {p.name for p in (export / "objects" / "sha256").iterdir()} == set(_objects(legacy))
    assert _manifest(legacy)["schema_version"] == LEGACY_FORMAT, "export migrated the workspace"

    validated = _oak("validate", "export", str(export), "--output", "json", cwd=tmp_path)
    assert validated.exit_code == 0, _output(validated)
    verdict = json.loads(validated.stdout)
    assert verdict["valid"] is True and verdict["migration_needed"] is True
    assert verdict["format"] == LEGACY_FORMAT


def test_an_older_export_imports_as_it_is_and_migrates_once(legacy: Path, tmp_path: Path) -> None:
    export = tmp_path / "export"
    assert _oak("export", "--output", str(export), cwd=legacy).exit_code == 0
    imported_root = tmp_path / "imported"
    imported = _oak(
        "import", str(export), "--directory", str(imported_root), "--output", "json", cwd=tmp_path
    )
    assert imported.exit_code == 0, _output(imported)
    assert json.loads(imported.stdout)["migration_needed"] is True
    assert _manifest(imported_root)["schema_version"] == LEGACY_FORMAT
    objects_before = _objects(imported_root)
    case_before = _manifest(imported_root)["current_case_ref"]
    events_before = len(_manifest(imported_root)["audit_events"])

    migrated = _oak("workspace", "migrate", "--output", "json", cwd=imported_root)
    assert migrated.exit_code == 0, _output(migrated)
    result = json.loads(migrated.stdout)
    assert result["changed"] is True
    assert (result["from_format"], result["to_format"]) == (LEGACY_FORMAT, CURRENT_MANIFEST_FORMAT)
    assert result["migration_steps"] == [STEP_NAME]
    assert [ref["id"] for ref in result["new_artifact_refs"]] == ["intent.public-manual-qa"]
    assert result["case_ref"]["id"] == case_before["id"]
    assert result["case_ref"]["version"] != case_before["version"]

    manifest = _manifest(imported_root)
    assert manifest["schema_version"] == CURRENT_MANIFEST_FORMAT
    assert "oak.community/legacy_label" not in manifest["extensions"]
    assert len(manifest["audit_events"]) == events_before + 1
    assert manifest["current_case_ref"] == result["case_ref"]
    # Every object the workspace held is still there, unchanged; only new ones were added.
    objects_after = _objects(imported_root)
    assert all(objects_after[name] == content for name, content in objects_before.items())
    assert len(objects_after) == len(objects_before) + 3  # the intent, the event, the case

    repository = FileWorkspaceRepository(imported_root, _registry())
    case = repository.current_case()
    assert case is not None
    assert case["extensions"][LABEL_KEY] == "legacy"
    origin = case["extensions"][MIGRATION_EXTENSION]
    assert origin["from_format"] == LEGACY_FORMAT and origin["steps"] == [STEP_NAME]
    assert origin["new_artifact_refs"] == result["new_artifact_refs"]
    intent = repository.read_json_artifact(
        __import__("oak.domain", fromlist=["ArtifactReference"]).ArtifactReference.from_document(
            case["intent_ref"]
        )
    )
    assert intent["extensions"][MIGRATED_FROM_KEY] == LEGACY_FORMAT
    last_event = repository.read_json_artifact(
        __import__("oak.domain", fromlist=["ArtifactReference"]).ArtifactReference.from_document(
            manifest["audit_events"][-1]
        )
    )
    assert last_event["event_type"] == "workspace_migrated"
    assert last_event["extensions"][MIGRATION_EXTENSION] == origin
    assert last_event["result"]["intent_ref"] == case["intent_ref"]
    assert last_event["case_version"] == case["version"]

    # Twice is a no-op: nothing on disk changes.
    bytes_after = (imported_root / ".oak" / "manifest.json").read_bytes()
    again = _oak("workspace", "migrate", "--output", "json", cwd=imported_root)
    assert again.exit_code == 0, _output(again)
    assert json.loads(again.stdout)["changed"] is False
    assert (imported_root / ".oak" / "manifest.json").read_bytes() == bytes_after
    assert _objects(imported_root) == objects_after

    # And every command works again.
    for command in (["questions", "--output", "json"], ["architecture"]):
        worked = _oak(*command, cwd=imported_root)
        assert worked.exit_code == 0, _output(worked)
    re_export = tmp_path / "re-export"
    assert _oak("export", "--output", str(re_export), cwd=imported_root).exit_code == 0
    validated = _oak("validate", "export", str(re_export), "--output", "json", cwd=tmp_path)
    assert validated.exit_code == 0, _output(validated)
    assert json.loads(validated.stdout)["migration_needed"] is False


def test_a_migration_is_byte_identical_across_interpreters(legacy: Path, tmp_path: Path) -> None:
    results: list[tuple[bytes, dict[str, bytes]]] = []
    for seed in ("1", "4242"):
        workspace = tmp_path / f"seed-{seed}"
        shutil.copytree(legacy, workspace)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; "
                "from tests.workspace_format_support import migrate_with_synthetic_chain; "
                "migrate_with_synthetic_chain(Path(sys.argv[1]), occurred_at=sys.argv[2])",
                str(workspace),
                "2026-10-29T12:00:00Z",
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        results.append(((workspace / ".oak" / "manifest.json").read_bytes(), _objects(workspace)))
    assert results[0] == results[1]
    assert json.loads(results[0][0])["schema_version"] == CURRENT_MANIFEST_FORMAT


def test_an_unknown_format_is_refused_on_every_command_export_included(
    current: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    manifest = _manifest(current)
    manifest["schema_version"] = "9.9.9"
    (current / ".oak" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    status = _oak("workspace", "status", "--output", "json", cwd=current)
    assert status.exit_code == 0, _output(status)
    report = json.loads(status.stdout)
    assert report["known"] is False and report["current"] is False
    for command in (
        ["questions"],
        ["export", "--output", str(tmp_path / "export")],
        ["workspace", "migrate"],
    ):
        refused = _oak(*command, cwd=current)
        assert refused.exit_code == 2, _output(refused)
        assert "OAK-WORKSPACE-FORMAT" in _output(refused)
    assert not (tmp_path / "export").exists()

    export = tmp_path / "unknown-export"
    export.mkdir()
    shutil.copytree(current / ".oak" / "objects", export / "objects")
    shutil.copy(current / ".oak" / "manifest.json", export / "manifest.json")
    imported = _oak("import", str(export), "--directory", str(tmp_path / "new"), cwd=tmp_path)
    assert imported.exit_code == 2, _output(imported)
    assert "OAK-IMPORT-FORMAT" in _output(imported)
    assert not (tmp_path / "new" / ".oak").exists()


def test_a_corrupt_object_stops_the_export_of_an_older_workspace(
    legacy: Path, tmp_path: Path
) -> None:
    objects = legacy / ".oak" / "objects" / "sha256"
    victim = sorted(objects.iterdir())[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    refused = _oak("export", "--output", str(tmp_path / "export"), cwd=legacy)
    assert refused.exit_code == 2, _output(refused)
    assert "OAK-WORKSPACE-CORRUPT" in _output(refused)
    assert not (tmp_path / "export").exists()


def test_a_workspace_that_changed_after_the_plan_is_refused(legacy: Path) -> None:
    repository = FileWorkspaceRepository(legacy, _registry(), chain=SYNTHETIC_CHAIN)
    outcome = repository.migration_outcome()
    manifest_path = legacy / ".oak" / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
    with pytest.raises(OAKError) as refusal:
        repository.commit_migration(outcome, None)
    assert refusal.value.code == "OAK-WORKSPACE-MIGRATION"
    assert refusal.value.retriable
    assert json.loads(manifest_path.read_bytes())["schema_version"] == LEGACY_FORMAT


def test_a_migration_that_adds_objects_to_an_empty_workspace_is_refused(tmp_path: Path) -> None:
    from oak.domain import Artifact

    added = Artifact(
        id="note.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=b"n"
    )

    def apply(manifest: dict[str, Any], read: Any) -> StepResult:
        manifest["schema_version"] = CURRENT_MANIFEST_FORMAT
        manifest["artifact_index"].append(added.index_document())
        return StepResult(manifest=manifest, new_artifacts=(added,))

    chain = FormatChain((FormatStep("0.3.9", CURRENT_MANIFEST_FORMAT, "add-note", apply),))
    workspace = tmp_path / "empty"
    repository = FileWorkspaceRepository(workspace, _registry(), chain=chain)
    repository.initialize(
        workspace_id="workspace.empty", tenant_id="local", created_at="2026-10-29T00:00:00Z"
    )
    manifest = _manifest(workspace)
    manifest["schema_version"] = "0.3.9"
    (workspace / ".oak" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OAKError) as refusal:
        WorkspaceFormatService(repository, _registry()).migrate(_context())
    assert refusal.value.code == "OAK-WORKSPACE-MIGRATION"
    assert _manifest(workspace)["schema_version"] == "0.3.9"


def test_a_migration_that_only_changes_the_manifest_records_nothing(tmp_path: Path) -> None:
    def apply(manifest: dict[str, Any], read: Any) -> StepResult:
        manifest["schema_version"] = CURRENT_MANIFEST_FORMAT
        return StepResult(manifest=manifest)

    chain = FormatChain((FormatStep("0.3.9", CURRENT_MANIFEST_FORMAT, "relabel", apply),))
    workspace = tmp_path / "empty"
    repository = FileWorkspaceRepository(workspace, _registry(), chain=chain)
    repository.initialize(
        workspace_id="workspace.empty", tenant_id="local", created_at="2026-10-29T00:00:00Z"
    )
    manifest = _manifest(workspace)
    manifest["schema_version"] = "0.3.9"
    (workspace / ".oak" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = WorkspaceFormatService(repository, _registry()).migrate(_context())
    assert result.changed and result.event_ref is None and result.case_ref is None
    assert _manifest(workspace)["schema_version"] == CURRENT_MANIFEST_FORMAT
    assert _manifest(workspace)["audit_events"] == []
    assert repository.manifest()["version"] == 0


def test_the_format_commands_are_local_only(current: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    for command in (["workspace", "status"], ["workspace", "migrate"]):
        refused = _oak("--server", "http://127.0.0.1:9", *command, cwd=current)
        assert refused.exit_code == 2, _output(refused)
        assert "OAK-REMOTE-UNSUPPORTED" in _output(refused)
