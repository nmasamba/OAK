# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-004 signing key lifecycle and signature verification."""

import os
import stat
from pathlib import Path

import pytest

from oak.adapters.signing import LocalEd25519Signer, initialize_trust_directory
from oak.contracts.signatures import (
    signed_payload_bytes,
    verify_signature,
    verify_signed_document,
)
from oak.domain import OAKError, canonical_json_bytes


def test_initialize_creates_role_keys_with_private_permissions(tmp_path: Path) -> None:
    identities = initialize_trust_directory(tmp_path)
    assert {identity.role for identity in identities} == {"plan-signer", "approver"}
    for identity in identities:
        assert identity.trust_level == "development"
        assert identity.algorithm == "ed25519"
        key_path = tmp_path / f"{identity.role}.key"
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_signature_round_trips_and_rejects_a_flipped_byte(tmp_path: Path) -> None:
    initialize_trust_directory(tmp_path)
    signer = LocalEd25519Signer.load(tmp_path, "plan-signer")
    identity = signer.identity()
    message = canonical_json_bytes({"claim": "release"})
    signature = signer.sign(message)
    assert verify_signature(
        algorithm=identity.algorithm,
        public_key_base64=identity.public_key_base64,
        message=message,
        signature_base64=signature,
    )
    assert not verify_signature(
        algorithm=identity.algorithm,
        public_key_base64=identity.public_key_base64,
        message=canonical_json_bytes({"claim": "tampered"}),
        signature_base64=signature,
    )


def test_signed_document_helper_signs_the_payload_minus_signature(tmp_path: Path) -> None:
    initialize_trust_directory(tmp_path)
    signer = LocalEd25519Signer.load(tmp_path, "approver")
    identity = signer.identity()
    document = {"id": "approval.example", "action": "dry_run"}
    document["signature"] = {
        "role": identity.role,
        "key_id": identity.key_id,
        "algorithm": identity.algorithm,
        "public_key_base64": identity.public_key_base64,
        "trust_level": identity.trust_level,
        "signature_base64": signer.sign(signed_payload_bytes(document)),
    }
    assert verify_signed_document(document)
    document["action"] = "apply"
    assert not verify_signed_document(document)


def test_group_readable_key_is_rejected(tmp_path: Path) -> None:
    initialize_trust_directory(tmp_path)
    os.chmod(tmp_path / "plan-signer.key", 0o640)
    with pytest.raises(OAKError, match="group or world accessible"):
        LocalEd25519Signer.load(tmp_path, "plan-signer")


def test_unknown_role_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(OAKError, match="signing role is not recognized"):
        LocalEd25519Signer.load(tmp_path, "root")


def test_missing_key_reports_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(OAKError, match="signing key does not exist"):
        LocalEd25519Signer.load(tmp_path, "plan-signer")
