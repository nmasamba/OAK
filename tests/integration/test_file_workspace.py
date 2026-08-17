# SPDX-License-Identifier: Apache-2.0
"""OAK-S1-001 atomic file workspace integration tests."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    DesignCase,
    DesignCaseStatus,
    OAKError,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.ports import WorkspaceMutation

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-17T10:00:00Z"


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _initial_mutation(
    *,
    idempotency_key: str = "design-workspace-test-0001",
    input_digest: str = f"sha256:{'1' * 64}",
) -> WorkspaceMutation:
    brief = Artifact(
        id="brief.workspace-test",
        version="0.1.0",
        kind="brief_source",
        media_type="text/plain",
        content=b"safe synthetic brief\n",
    )
    event_document = audit_event_document(
        sequence=1,
        previous_event_digest=None,
        case_id="design-case.workspace-test",
        case_version="0.1.0",
        event_type="brief_interpreted",
        actor="local-user",
        tenant_id="local",
        interface_origin="cli",
        correlation_id="correlation-workspace-test",
        idempotency_key=idempotency_key,
        input_digest=input_digest,
        occurred_at=NOW,
        intent_ref=None,
        source_record_ref=None,
    )
    event = json_artifact(
        artifact_id=str(event_document["id"]),
        version="1",
        kind="audit_event",
        media_type="application/vnd.oak.audit-event+json",
        document=event_document,
    )
    case = DesignCase(
        id="design-case.workspace-test",
        version="0.1.0",
        status=DesignCaseStatus.DRAFT,
        title="Workspace test",
        tenant_id="local",
        created_at=NOW,
        updated_at=NOW,
        interface_origin="cli",
        brief_refs=(brief.reference,),
        audit_head=event.digest,
    )
    case_artifact = json_artifact(
        artifact_id=case.id,
        version=case.version,
        kind="design_case",
        media_type="application/vnd.oak.design-case+json",
        document=case.to_document(),
    )
    return WorkspaceMutation(
        expected_case_version=None,
        idempotency_key=idempotency_key,
        input_digest=input_digest,
        artifacts=(brief, event, case_artifact),
        current_case_ref=case_artifact.reference,
        event_ref=event.reference,
        updated_at=NOW,
    )


def _repository(path: Path) -> FileWorkspaceRepository:
    return FileWorkspaceRepository(path, _registry())


def _concurrent_commit(workspace: str, key: str, digest_character: str) -> str:
    repository = _repository(Path(workspace))
    try:
        repository.commit(
            _initial_mutation(
                idempotency_key=key,
                input_digest=f"sha256:{digest_character * 64}",
            )
        )
    except OAKError as error:
        return error.code
    return "committed"


def test_initialization_and_commit_are_schema_valid_and_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "workspace")
    repository.initialize(
        workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW
    )
    mutation = _initial_mutation()

    first = repository.commit(mutation)
    retry = repository.commit(mutation)

    assert first.duplicate is False
    assert retry.duplicate is True
    assert retry.case_document == first.case_document
    manifest = repository.manifest()
    assert manifest["version"] == 1
    assert len(manifest["audit_events"]) == 1
    assert len(manifest["idempotency_records"]) == 1
    _registry().validate("design-case.schema.json", first.case_document)


def test_expected_version_and_idempotency_conflicts_fail_closed(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "workspace")
    repository.initialize(
        workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW
    )
    repository.commit(_initial_mutation())

    with pytest.raises(OAKError) as stale:
        repository.commit(
            replace(
                _initial_mutation(idempotency_key="design-workspace-test-0002"),
                expected_case_version=None,
            )
        )
    assert stale.value.code == "OAK-EXPECTED-VERSION"

    with pytest.raises(OAKError) as reused:
        repository.commit(
            _initial_mutation(
                idempotency_key="design-workspace-test-0001",
                input_digest=f"sha256:{'2' * 64}",
            )
        )
    assert reused.value.code == "OAK-IDEMPOTENCY-CONFLICT"


def test_failed_manifest_replace_leaves_previous_manifest_valid(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repository = _repository(workspace)
    repository.initialize(
        workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW
    )
    before = repository.manifest()

    def fail_replace(_source: str | bytes | Path, _destination: str | bytes | Path) -> NoReturn:
        raise OSError("injected manifest replacement failure")

    failing = FileWorkspaceRepository(workspace, _registry(), replace_file=fail_replace)
    with pytest.raises(OSError, match="injected"):
        failing.commit(_initial_mutation())

    assert repository.manifest() == before
    assert repository.current_case() is None


def test_corrupted_content_addressed_object_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "workspace")
    repository.initialize(
        workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW
    )
    committed = repository.commit(_initial_mutation())
    reference = ArtifactReference.from_document(repository.manifest()["current_case_ref"])
    object_path = repository.objects / reference.digest.removeprefix("sha256:")
    object_path.write_bytes(b"corrupt")

    with pytest.raises(OAKError) as captured:
        repository.current_case()
    assert captured.value.code == "OAK-WORKSPACE-CORRUPT"
    assert committed.case_document["id"] == "design-case.workspace-test"


def test_export_import_round_trip_preserves_manifest_objects_and_current_case(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path / "source")
    source.initialize(workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW)
    source.commit(_initial_mutation())
    export = tmp_path / "portable-export"
    source.export_to(export)

    imported = _repository(tmp_path / "imported")
    imported.import_from(export)

    assert imported.manifest() == source.manifest()
    assert imported.current_case() == source.current_case()
    assert {path.name: path.read_bytes() for path in imported.objects.iterdir()} == {
        path.name: path.read_bytes() for path in source.objects.iterdir()
    }


def test_import_rejects_metadata_identity_tampering_without_publishing_workspace(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path / "source")
    source.initialize(workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW)
    source.commit(_initial_mutation())
    export = tmp_path / "portable-export"
    source.export_to(export)
    manifest_path = export / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["current_case_ref"]["id"] = "design-case.tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    imported = _repository(tmp_path / "imported")

    with pytest.raises(OAKError) as captured:
        imported.import_from(export)

    assert captured.value.code == "OAK-IMPORT-INVALID"
    assert not imported.control.exists()


def test_import_rejects_audit_idempotency_tampering_and_symlinked_store(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path / "source")
    source.initialize(workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW)
    source.commit(_initial_mutation())
    export = tmp_path / "portable-export"
    source.export_to(export)
    manifest_path = export / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["idempotency_records"][0]["input_digest"] = f"sha256:{'2' * 64}"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    imported = _repository(tmp_path / "imported")

    with pytest.raises(OAKError) as lineage_error:
        imported.import_from(export)
    assert lineage_error.value.code == "OAK-AUDIT-LINEAGE"
    assert not imported.control.exists()

    safe_store = export / "objects"
    renamed_store = export / "objects-real"
    safe_store.rename(renamed_store)
    safe_store.symlink_to(renamed_store, target_is_directory=True)
    with pytest.raises(OAKError) as symlink_error:
        _repository(tmp_path / "symlink-import").import_from(export)
    assert symlink_error.value.code == "OAK-IMPORT-UNSAFE-PATH"


def test_concurrent_first_commits_serialize_and_only_one_wins(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repository = _repository(workspace)
    repository.initialize(
        workspace_id="workspace.workspace-test", tenant_id="local", created_at=NOW
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                _concurrent_commit,
                [str(workspace), str(workspace)],
                ["design-workspace-test-0001", "design-workspace-test-0002"],
                ["1", "2"],
            )
        )

    assert sorted(outcomes) == ["OAK-EXPECTED-VERSION", "committed"]
    assert repository.manifest()["version"] == 1
    assert len(repository.manifest()["audit_events"]) == 1
