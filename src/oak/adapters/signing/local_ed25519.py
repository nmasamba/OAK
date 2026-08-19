# SPDX-License-Identifier: Apache-2.0
"""Local Ed25519 signing with a per-role key lifecycle.

Keys live outside every workspace in a private trust directory. Community local
mode labels every identity ``development``; nothing here claims production
assurance, and losing the directory only invalidates re-signable envelopes.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.ports.signing import SignerIdentity

ALGORITHM = "ed25519"
TRUST_LEVEL = "development"
SIGNING_ROLES = ("plan-signer", "approver", "extension-steward")


def initialize_trust_directory(trust_directory: Path) -> tuple[SignerIdentity, ...]:
    """Create missing role keys and return every role identity."""

    trust_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(trust_directory, 0o700)
    return tuple(
        LocalEd25519Signer.initialize(trust_directory, role).identity() for role in SIGNING_ROLES
    )


class LocalEd25519Signer:
    """Sign canonical bytes for exactly one role identity."""

    def __init__(self, private_key: Ed25519PrivateKey, identity: SignerIdentity) -> None:
        self._private_key = private_key
        self._identity = identity

    @classmethod
    def initialize(cls, trust_directory: Path, role: str) -> LocalEd25519Signer:
        cls._check_role(role)
        key_path = trust_directory / f"{role}.key"
        if not key_path.exists():
            trust_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_key = Ed25519PrivateKey.generate()
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(private_key.private_bytes_raw())
            identity = cls._identity_for(private_key, role)
            identity_path = trust_directory / f"{role}.identity.json"
            identity_path.write_text(
                json.dumps(identity.to_document(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return cls.load(trust_directory, role)

    @classmethod
    def load(cls, trust_directory: Path, role: str) -> LocalEd25519Signer:
        cls._check_role(role)
        key_path = trust_directory / f"{role}.key"
        try:
            mode = os.lstat(key_path)
        except FileNotFoundError as error:
            raise OAKError(
                "OAK-SIGNING-KEY-MISSING",
                "signing key does not exist; run oak keys init",
            ) from error
        if not stat.S_ISREG(mode.st_mode):
            raise OAKError("OAK-SIGNING-KEY-INVALID", "signing key must be a regular file")
        if mode.st_mode & 0o077:
            raise OAKError(
                "OAK-SIGNING-KEY-PERMISSIONS",
                "signing key must not be group or world accessible",
            )
        raw = key_path.read_bytes()
        if len(raw) != 32:
            raise OAKError("OAK-SIGNING-KEY-INVALID", "signing key length is invalid")
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
        identity_path = trust_directory / f"{role}.identity.json"
        created_at = _identity_created_at(identity_path)
        identity = cls._identity_for(private_key, role, created_at=created_at)
        return cls(private_key, identity)

    def identity(self) -> SignerIdentity:
        return self._identity

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self._private_key.sign(message)).decode("ascii")

    @staticmethod
    def _check_role(role: str) -> None:
        if role not in SIGNING_ROLES:
            raise OAKError("OAK-SIGNING-ROLE", "signing role is not recognized")

    @staticmethod
    def _identity_for(
        private_key: Ed25519PrivateKey,
        role: str,
        *,
        created_at: str | None = None,
    ) -> SignerIdentity:
        public_bytes = private_key.public_key().public_bytes_raw()
        return SignerIdentity(
            role=role,
            key_id=content_digest(
                canonical_json_bytes(
                    {
                        "algorithm": ALGORITHM,
                        "public_key_base64": base64.b64encode(public_bytes).decode("ascii"),
                        "role": role,
                    }
                )
            ),
            algorithm=ALGORITHM,
            public_key_base64=base64.b64encode(public_bytes).decode("ascii"),
            trust_level=TRUST_LEVEL,
            created_at=created_at
            or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )


def _identity_created_at(identity_path: Path) -> str | None:
    try:
        document = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    created_at = document.get("created_at")
    return created_at if isinstance(created_at, str) else None
