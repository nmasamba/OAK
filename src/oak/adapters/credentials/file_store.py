# SPDX-License-Identifier: Apache-2.0
"""Owner-only file backend for provider keys, with a salted fingerprint."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path

from oak.adapters.credentials._files import (
    read_private_file,
    remove_private_file,
    write_private_file,
)
from oak.domain import SecretValue

PERMISSIONS_CODE = "OAK-MODEL-KEY-PERMISSIONS"
MAXIMUM_KEY_BYTES = 512
SALT_FILE_NAME = "fingerprint.salt"
_SALT_BYTES = 32


class FileCredentialStore:
    """`<family>.key` files under the credentials directory, created `0600` in a `0700` dir."""

    source = "file"

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def location(self) -> str:
        return str(self._directory)

    def set(self, family: str, secret: SecretValue) -> None:
        write_private_file(
            self._directory / f"{family}.key",
            secret.reveal().encode("utf-8"),
            code=PERMISSIONS_CODE,
        )

    def get(self, family: str) -> SecretValue | None:
        content = read_private_file(
            self._directory / f"{family}.key",
            code=PERMISSIONS_CODE,
            maximum_bytes=MAXIMUM_KEY_BYTES,
        )
        if content is None:
            return None
        return SecretValue(content.decode("utf-8").strip())

    def delete(self, family: str) -> bool:
        return remove_private_file(self._directory / f"{family}.key", code=PERMISSIONS_CODE)

    def fingerprint(self, secret: SecretValue) -> str:
        """Eight hex characters of an HMAC keyed by a per-install random salt.

        A plain hash of the key would let anyone with a candidate key confirm it from the
        fingerprint alone; the salt lives beside the keys, so it is no weaker than they are.
        """

        salt = read_private_file(
            self._directory / SALT_FILE_NAME, code=PERMISSIONS_CODE, maximum_bytes=64
        )
        if salt is None:
            salt = secrets.token_bytes(_SALT_BYTES)
            write_private_file(self._directory / SALT_FILE_NAME, salt, code=PERMISSIONS_CODE)
        return hmac.new(salt, secret.reveal().encode("utf-8"), hashlib.sha256).hexdigest()[:8]
