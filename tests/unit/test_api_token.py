# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-002: the per-process capability token is minted owner-only and read fail-closed."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from oak.adapters.credentials import TOKEN_FILE_NAME, read_api_token, write_api_token
from oak.adapters.credentials._files import (
    read_private_file,
    remove_private_file,
    write_private_file,
)
from oak.domain import OAKError


def test_a_minted_token_is_random_owner_only_and_readable_back(tmp_path: Path) -> None:
    directory = tmp_path / "credentials"

    first = write_api_token(directory)
    second = write_api_token(directory)

    assert first != second and len(second) >= 40
    assert stat.S_IMODE(os.lstat(directory).st_mode) == 0o700
    assert stat.S_IMODE(os.lstat(directory / TOKEN_FILE_NAME).st_mode) == 0o600
    assert read_api_token(directory) == second
    assert not (directory / (TOKEN_FILE_NAME + ".tmp")).exists()


def test_no_token_reads_as_none(tmp_path: Path) -> None:
    assert read_api_token(tmp_path / "never-created") is None


def test_a_group_readable_token_file_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "credentials"
    write_api_token(directory)
    os.chmod(directory / TOKEN_FILE_NAME, 0o640)

    with pytest.raises(OAKError) as refusal:
        read_api_token(directory)
    assert refusal.value.code == "OAK-MODEL-TOKEN-FILE"


def test_a_symlinked_token_file_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "credentials"
    directory.mkdir(mode=0o700)
    target = tmp_path / "elsewhere"
    target.write_text("stolen")
    (directory / TOKEN_FILE_NAME).symlink_to(target)

    with pytest.raises(OAKError) as refusal:
        read_api_token(directory)
    assert refusal.value.code == "OAK-MODEL-TOKEN-FILE"
    with pytest.raises(OAKError):
        write_api_token(directory)


def test_a_symlinked_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real)

    with pytest.raises(OAKError) as refusal:
        write_api_token(link)
    assert refusal.value.code == "OAK-MODEL-TOKEN-FILE"


def test_an_existing_private_directory_is_accepted_and_a_loose_one_is_tightened(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "loose"
    directory.mkdir(mode=0o755)
    write_private_file(directory / "value", b"x" * 16, code="OAK-TEST")
    assert stat.S_IMODE(os.lstat(directory).st_mode) == 0o700

    already = tmp_path / "tight"
    already.mkdir(mode=0o700)
    write_private_file(already / "value", b"y" * 16, code="OAK-TEST")
    assert read_private_file(already / "value", code="OAK-TEST", maximum_bytes=64) == b"y" * 16


def test_a_directory_owned_by_another_user_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "foreign"
    directory.mkdir(mode=0o700)
    real_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)

    with pytest.raises(OAKError) as refusal:
        write_private_file(directory / "value", b"z" * 16, code="OAK-TEST")
    assert refusal.value.code == "OAK-TEST"
    assert "another user" in refusal.value.message


def test_a_failed_write_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "credentials"

    def explode(*_: object, **__: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError):
        write_private_file(directory / "value", b"w" * 16, code="OAK-TEST")
    assert sorted(path.name for path in directory.iterdir()) == []


def test_oversized_and_removed_files_behave(tmp_path: Path) -> None:
    directory = tmp_path / "credentials"
    write_private_file(directory / "value", b"v" * 64, code="OAK-TEST")
    with pytest.raises(OAKError):
        read_private_file(directory / "value", code="OAK-TEST", maximum_bytes=16)
    assert remove_private_file(directory / "value", code="OAK-TEST") is True
    assert remove_private_file(directory / "value", code="OAK-TEST") is False
