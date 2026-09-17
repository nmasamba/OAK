# SPDX-License-Identifier: Apache-2.0
"""Owner-only file primitives shared by the credential stores.

The rules mirror the signing-key store (`oak.adapters.signing.local_ed25519`): directories
are created `0700` and re-chmodded because `mkdir(mode=)` is subject to the umask and is a
no-op for an existing directory; files are created with `O_EXCL | O_NOFOLLOW` at `0600`,
written through a temporary name and renamed atomically; reads refuse symlinks, non-regular
files, group or world permission bits, and files owned by another user. A refusal is an
`OAKError` with a fixed message so no path fragment or content reaches a diagnostic.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from oak.domain import OAKError

_PRIVATE_DIRECTORY = 0o700
_PRIVATE_FILE = 0o600


def ensure_private_directory(directory: Path, *, code: str) -> None:
    """Create or accept an owner-only directory; refuse anything else."""

    if directory.is_symlink():
        raise OAKError(code, "the credential directory must not be a symbolic link")
    if not directory.exists():
        directory.mkdir(parents=True, mode=_PRIVATE_DIRECTORY)
    details = os.lstat(directory)
    if not stat.S_ISDIR(details.st_mode):
        raise OAKError(code, "the credential directory path is not a directory")
    if details.st_uid != os.getuid():
        raise OAKError(
            code,
            "the credential directory is owned by another user; under Compose this is the "
            "api service's model-state volume, which the image creates for uid 10001",
        )
    if details.st_mode & 0o077:
        # We own it, so tightening is safe and is what a fresh mkdir under a permissive
        # umask needs. An existing 0700 directory (a mounted volume) is accepted untouched.
        os.chmod(directory, _PRIVATE_DIRECTORY)


def write_private_file(path: Path, content: bytes, *, code: str) -> None:
    """Write ``content`` to ``path`` atomically as an owner-only regular file."""

    ensure_private_directory(path.parent, code=code)
    if path.is_symlink():
        raise OAKError(code, "the credential file must not be a symbolic link")
    scratch = path.with_name(path.name + ".tmp")
    scratch.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(scratch, flags, _PRIVATE_FILE)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def read_private_file(path: Path, *, code: str, maximum_bytes: int) -> bytes | None:
    """Return the file's bytes, ``None`` when absent, or refuse an unsafe file."""

    try:
        details = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(details.st_mode):
        raise OAKError(code, "the credential file must be a regular file, not a link or device")
    if details.st_uid != os.getuid():
        raise OAKError(code, "the credential file is owned by another user")
    if details.st_mode & 0o077:
        raise OAKError(code, "the credential file must not be group or world accessible")
    if details.st_size > maximum_bytes:
        raise OAKError(code, "the credential file is larger than a credential can be")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read(maximum_bytes + 1)


def remove_private_file(path: Path, *, code: str) -> bool:
    """Delete the file if present; ``True`` when something was removed."""

    if path.is_symlink():
        raise OAKError(code, "the credential file must not be a symbolic link")
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
