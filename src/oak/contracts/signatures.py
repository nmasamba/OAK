# SPDX-License-Identifier: Apache-2.0
"""Signature verification over canonical signed documents."""

from __future__ import annotations

import base64
import binascii
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
