# SPDX-License-Identifier: Apache-2.0
"""Signature verification over canonical signed documents."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _canonical_json_bytes(document: dict[str, Any]) -> bytes:
    """Mirror oak.domain.canonical_json_bytes; contracts is a leaf package.

    tests/contract/test_boundaries.py asserts both serializers agree byte-for-byte.
    """

    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


SUPPORTED_ALGORITHMS = frozenset({"ed25519"})


def verify_signature(
    *,
    algorithm: str,
    public_key_base64: str,
    message: bytes,
    signature_base64: str,
) -> bool:
    if algorithm not in SUPPORTED_ALGORITHMS:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_base64, validate=True)
        )
        public_key.verify(base64.b64decode(signature_base64, validate=True), message)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


def signed_payload_bytes(document: dict[str, Any]) -> bytes:
    """Canonical bytes of a signed document with its signature block removed."""

    payload = {key: value for key, value in document.items() if key != "signature"}
    return _canonical_json_bytes(payload)


def verify_pinned_signature(
    document: dict[str, Any], anchors: dict[str, str], *, role: str
) -> str | None:
    """Verify a document's signature block against a pinned anchor, never its own key.

    ``anchors`` maps a key identifier to the public key the operator pinned for it. The
    block's key must be pinned, must equal the pinned key, must derive its identifier
    from that key and the role, and must verify over the document's payload. Returns
    None when it does, otherwise a short reason code. One scheme for every signed pack
    (the extension verifier and the catalogue feed share it).
    """

    signature = document.get("signature")
    if not isinstance(signature, dict):
        return "unsigned"
    if str(signature.get("role")) != role:
        return "wrong-role"
    key_id = str(signature.get("key_id"))
    pinned = anchors.get(key_id)
    if pinned is None:
        return "unpinned-key"
    if str(signature.get("public_key_base64")) != pinned:
        return "key-mismatch"
    derived = (
        "sha256:"
        + hashlib.sha256(
            _canonical_json_bytes(
                {"algorithm": "ed25519", "public_key_base64": pinned, "role": role}
            )
        ).hexdigest()
    )
    if derived != key_id:
        return "key-id-mismatch"
    try:
        base64.b64decode(pinned, validate=True)
    except (ValueError, binascii.Error):
        return "unreadable-anchor"
    verified = verify_signature(
        algorithm=str(signature.get("algorithm")),
        public_key_base64=pinned,
        message=signed_payload_bytes(document),
        signature_base64=str(signature.get("signature_base64")),
    )
    return None if verified else "invalid-signature"


def verify_signed_document(document: dict[str, Any]) -> bool:
    """Verify a canonical document whose ``signature`` block signs the remainder."""

    signature = document.get("signature")
    if not isinstance(signature, dict):
        return False
    algorithm = signature.get("algorithm")
    public_key = signature.get("public_key_base64")
    value = signature.get("signature_base64")
    if (
        not isinstance(algorithm, str)
        or not isinstance(public_key, str)
        or not isinstance(value, str)
    ):
        return False
    return verify_signature(
        algorithm=algorithm,
        public_key_base64=public_key,
        message=signed_payload_bytes(document),
        signature_base64=value,
    )
