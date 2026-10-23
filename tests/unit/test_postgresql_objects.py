# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-016: the PostgreSQL store writes each artifact object whole.

Objects are written before the transaction by every writer holding the bytes, so two first
writers of one case write the same objects at once. Once CI ran the PostgreSQL suites, the
shared contract's concurrent-first-writers test failed in three runs of five: the object was
created in place and then filled, the second writer read it half-written, and reported
`OAK-ARTIFACT-COLLISION` instead of losing the race with `OAK-EXPECTED-VERSION`.

No database is needed: objects live on disk, and the engine is never connected.
"""

from __future__ import annotations

import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from oak.adapters.persistence.postgresql import PostgreSQLWorkspaceRepository
from oak.bootstrap import canonical_schema_directory
from oak.contracts import SchemaRegistry
from oak.domain import Artifact, OAKError, json_artifact


def _repository(root: Path) -> PostgreSQLWorkspaceRepository:
    return PostgreSQLWorkspaceRepository(
        create_engine("postgresql+psycopg://oak@127.0.0.1:9/never-connected"),
        SchemaRegistry.from_directory(canonical_schema_directory()),
        root,
        workspace_id="workspace.objects",
        tenant_id="local",
    )


def _artifact() -> Artifact:
    return json_artifact(
        artifact_id="object.example",
        version="0.1.0",
        kind="source_record",
        media_type="application/json",
        document={"text": "x" * 20_000, "note": "large enough to be written in pieces"},
    )


def _object(root: Path, artifact: Artifact) -> Path:
    return root / "sha256" / artifact.digest.removeprefix("sha256:")


def test_a_half_written_object_is_completed_not_called_a_collision(tmp_path: Path) -> None:
    artifact = _artifact()
    path = _object(tmp_path, artifact)
    path.parent.mkdir(parents=True, mode=0o700)
    # What a reader saw while another writer was still filling the object in place, and
    # what an interrupted write used to leave behind.
    path.write_bytes(artifact.content[: len(artifact.content) // 2])

    _repository(tmp_path)._write_object(artifact)

    assert path.read_bytes() == artifact.content
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_writers_of_one_object_at_once_never_collide_or_leave_a_temporary(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    repositories = [_repository(tmp_path) for _ in range(16)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        for future in [pool.submit(each._write_object, artifact) for each in repositories]:
            future.result()

    assert _object(tmp_path, artifact).read_bytes() == artifact.content
    assert [entry.name for entry in (tmp_path / "sha256").iterdir()] == [
        artifact.digest.removeprefix("sha256:")
    ]


def test_a_symlink_in_place_of_an_object_is_refused(tmp_path: Path) -> None:
    artifact = _artifact()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_bytes(artifact.content)
    path = _object(tmp_path, artifact)
    path.parent.mkdir(parents=True, mode=0o700)
    path.symlink_to(elsewhere)

    with pytest.raises(OAKError) as refused:
        _repository(tmp_path)._write_object(artifact)
    assert refused.value.code == "OAK-ARTIFACT-COLLISION"
