# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-032 (RR-030): the per-process verification cache skips only the work the
manifest's bytes are the input to, and never stands in for trust.

The first read of a manifest in a process verifies it in full: the manifest's own checks
and the audit-lineage walk. A later read of byte-identical content skips both. A changed
byte, a mutation, an export and an object read never rely on it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.persistence import FileWorkspaceRepository, clear_verification_cache
from oak.adapters.persistence import file_workspace as adapter
from oak.application.context import CommandContext
from oak.bootstrap import create_design_case_service
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def compiled(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_compiled_case(tmp_path_factory.mktemp("compiled")).workspace


@pytest.fixture
def workspace(compiled: Path, tmp_path: Path) -> Path:
    clear_verification_cache()
    destination = tmp_path / "workspace"
    shutil.copytree(compiled, destination)
    return destination


@pytest.fixture
def walks(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts every full lineage walk the adapter performs."""

    count = [0]
    original = FileWorkspaceRepository._validate_workspace_lineage

    def counted(self: FileWorkspaceRepository, manifest: dict[str, Any]) -> None:
        count[0] += 1
        original(self, manifest)

    monkeypatch.setattr(FileWorkspaceRepository, "_validate_workspace_lineage", counted)
    return count


def _repository(workspace: Path) -> FileWorkspaceRepository:
    return FileWorkspaceRepository(workspace, SchemaRegistry.from_directory(ROOT / "schemas"))


def test_the_first_read_verifies_in_full_and_a_later_read_of_the_same_bytes_does_not(
    workspace: Path, walks: list[int]
) -> None:
    repository = _repository(workspace)
    repository.manifest()
    assert walks[0] == 1
    repository.manifest()
    repository.current_case()
    assert walks[0] == 1
    # Per process, not per instance: another repository on the same bytes skips too.
    _repository(workspace).manifest()
    assert walks[0] == 1


def test_a_changed_byte_verifies_again_and_a_broken_lineage_is_refused(
    workspace: Path, walks: list[int]
) -> None:
    repository = _repository(workspace)
    repository.manifest()
    manifest_path = workspace / ".oak" / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
    repository.manifest()
    assert walks[0] == 2, "the same document in other bytes must verify again"

    manifest = json.loads(manifest_path.read_bytes())
    manifest["audit_events"] = manifest["audit_events"][:-1]
    manifest["idempotency_records"] = manifest["idempotency_records"][:-1]
    manifest["version"] -= 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OAKError) as refusal:
        repository.manifest()
    assert refusal.value.code == "OAK-WORKSPACE-CORRUPT"


def test_a_mutation_verifies_in_full_whatever_the_cache_holds(
    workspace: Path, walks: list[int]
) -> None:
    service = create_design_case_service(workspace)
    service.current()
    service.current()
    before = walks[0]
    assert before == 1
    service.record_recreation(
        {"workspace_id": "workspace.elsewhere", "case_id": "design-case.public-manual-qa"},
        CommandContext(
            actor="local-user",
            tenant_id="local",
            idempotency_key="cache-test-recreation-0001",
            expected_version="0.1.7",
            correlation_id="correlation-cache-test",
            interface_origin="cli",
            occurred_at="2026-10-29T12:00:00Z",
        ),
    )
    assert walks[0] == before + 1, "the commit walked the lineage although the read was cached"
    # The commit changed the bytes, so the next read verifies the new history in full.
    service.current()
    assert walks[0] == before + 2


def test_an_export_verifies_in_full_whatever_the_cache_holds(
    workspace: Path, walks: list[int], tmp_path: Path
) -> None:
    repository = _repository(workspace)
    repository.manifest()
    assert walks[0] == 1
    repository.export_to(tmp_path / "export")
    assert walks[0] == 2


def test_object_reads_keep_verifying_their_digests_after_a_cached_read(workspace: Path) -> None:
    repository = _repository(workspace)
    manifest = repository.manifest()
    reference = manifest["current_case_ref"]
    victim = workspace / ".oak" / "objects" / "sha256" / reference["digest"].removeprefix("sha256:")
    victim.write_bytes(victim.read_bytes() + b" ")
    with pytest.raises(OAKError) as refusal:
        repository.current_case()
    assert refusal.value.code == "OAK-WORKSPACE-CORRUPT"


def test_the_cache_is_bounded(tmp_path: Path, walks: list[int]) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repositories: list[FileWorkspaceRepository] = []
    for index in range(adapter.VERIFICATION_CACHE_SIZE + 1):
        repository = FileWorkspaceRepository(tmp_path / f"w{index}", registry)
        repository.initialize(
            workspace_id=f"workspace.w{index}", tenant_id="local", created_at="2026-10-29T00:00:00Z"
        )
        repository.manifest()
        repositories.append(repository)
    assert walks[0] == adapter.VERIFICATION_CACHE_SIZE + 1
    repositories[-1].manifest()
    assert walks[0] == adapter.VERIFICATION_CACHE_SIZE + 1, "the newest entry was evicted"
    repositories[0].manifest()
    assert walks[0] == adapter.VERIFICATION_CACHE_SIZE + 2, "the oldest entry survived"
