# SPDX-License-Identifier: Apache-2.0
"""Runner identity: a local Ed25519 key that signs outbound protocol messages."""

from __future__ import annotations

import base64
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oak.domain import OAKError, canonical_json_bytes, content_digest


class RunnerIdentity:
    def __init__(self, private_key: Ed25519PrivateKey, runner_id: str) -> None:
        self._private_key = private_key
        self.runner_id = runner_id
        self.public_key_base64 = base64.b64encode(
            private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        self.key_id = content_digest(
            canonical_json_bytes(
                {
                    "algorithm": "ed25519",
                    "public_key_base64": self.public_key_base64,
                    "role": "runner",
                }
            )
        )

    @classmethod
    def load_or_create(cls, home: Path, runner_id: str) -> RunnerIdentity:
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_path = home / "runner.key"
        if not key_path.exists():
            private_key = Ed25519PrivateKey.generate()
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(private_key.private_bytes_raw())
        mode = os.lstat(key_path)
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077:
            raise OAKError("OAK-RUNNER-KEY", "runner key must be a private regular file")
        raw = key_path.read_bytes()
        if len(raw) != 32:
            raise OAKError("OAK-RUNNER-KEY", "runner key length is invalid")
        return cls(Ed25519PrivateKey.from_private_bytes(raw), runner_id)

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self._private_key.sign(message)).decode("ascii")

    def signature_block(self, message: bytes) -> dict[str, str]:
        return {
            "role": "runner",
            "key_id": self.key_id,
            "algorithm": "ed25519",
            "public_key_base64": self.public_key_base64,
            "trust_level": "development",
            "signature_base64": self.sign(message),
        }
