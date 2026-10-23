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
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.ports.signing import SignerIdentity

ALGORITHM = "ed25519"
TRUST_LEVEL = "development"
SIGNING_ROLES = ("plan-signer", "approver", "extension-steward")
# One file per enrolled runner, named by its key id: an operator may run several runners
# (one per target, one per machine), and ingest believes each one enrolled here.
RUNNER_IDENTITY_DIRECTORY = "runners"


def runner_identity_document(document: Any) -> dict[str, str]:
    """The public identity of a runner, checked: an Ed25519 key and the id derived from it."""

    if not isinstance(document, dict):
        raise OAKError("OAK-KEYS-RUNNER-IDENTITY", "a runner identity must be a JSON object")
    public_key = document.get("public_key_base64")
    try:
        raw = base64.b64decode(str(public_key), validate=True)
    except (ValueError, TypeError) as error:
        raise OAKError("OAK-KEYS-RUNNER-IDENTITY", "the runner public key is not base64") from error
    identity = {
        "role": "runner",
        "algorithm": ALGORITHM,
        "public_key_base64": str(public_key),
        "key_id": content_digest(
            canonical_json_bytes(
                {"algorithm": ALGORITHM, "public_key_base64": str(public_key), "role": "runner"}
            )
        ),
    }
    if (
        len(raw) != 32
        or document.get("role") != "runner"
        or document.get("algorithm") != ALGORITHM
        or document.get("key_id") != identity["key_id"]
    ):
        raise OAKError(
            "OAK-KEYS-RUNNER-IDENTITY",
            "this is not a runner identity: print one with `oak-runner identity`",
        )
    return identity


def enroll_runner(trust_directory: Path, document: Any) -> dict[str, str]:
    """Pin a runner whose signed messages `oak ingest` will believe; idempotent.

    Only the operator enrolls, from the identity `oak-runner identity` printed; nothing a
    runner sends through the mailbox can enroll a key.
    """

    identity = runner_identity_document(document)
    directory = trust_directory / RUNNER_IDENTITY_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{identity['key_id'].removeprefix('sha256:')}.json"
    if path.exists() or path.is_symlink():
        if _read_runner_identity(path) == identity:
            return identity
        raise OAKError(
            "OAK-KEYS-RUNNER-IDENTITY", "an enrolled runner identity file has been altered"
        )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    return identity


def load_runner_identities(trust_directory: Path) -> tuple[dict[str, str], ...]:
    """Every enrolled runner's public identity, by key id; empty when none is enrolled."""

    directory = trust_directory / RUNNER_IDENTITY_DIRECTORY
    if not directory.is_dir() or directory.is_symlink():
        return ()
    identities = []
    for path in sorted(directory.glob("*.json")):
        identity = _read_runner_identity(path)
        if path.stem != identity["key_id"].removeprefix("sha256:"):
            raise OAKError(
                "OAK-KEYS-RUNNER-IDENTITY", "an enrolled runner identity file has been altered"
            )
        identities.append(identity)
    return tuple(identities)


def _read_runner_identity(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise OAKError("OAK-KEYS-RUNNER-IDENTITY", "an enrolled runner identity is not a file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OAKError(
            "OAK-KEYS-RUNNER-IDENTITY", "an enrolled runner identity is unreadable"
        ) from error
    return runner_identity_document(document)


def read_trust_directory(trust_directory: Path) -> tuple[SignerIdentity, ...]:
    """Every role identity, read without creating anything.

    `oak keys show` used to create the directory and three private keys as a side effect,
    so it recreated exactly what an uninstall had just deleted (RR-018). Reading refuses
    when no key exists; one missing key among the three is `OAK-SIGNING-KEY-MISSING`.
    """

    if not any(os.path.lexists(trust_directory / f"{role}.key") for role in SIGNING_ROLES):
        raise OAKError(
            "OAK-KEYS-UNINITIALIZED", "no signing keys exist yet; run oak keys init to create them"
        )
    return tuple(
        LocalEd25519Signer.load(trust_directory, role).identity() for role in SIGNING_ROLES
    )


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
