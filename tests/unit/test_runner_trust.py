# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-002/004 trust-anchor binding regressions found by the Sprint 5 audit."""

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oak.contracts.signatures import signed_payload_bytes
from oak.domain import OAKError
from oak.runner.adapters import CommandResult, ContainerFixtureAdapter
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    _verify_against_anchor,
    derive_key_id,
)


def _identity(role: str, tmp_path: Path) -> tuple[Ed25519PrivateKey, str, str]:
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    key_id = derive_key_id(role, public)
    (tmp_path / f"{role}.identity.json").write_text(
        json.dumps(
            {
                "role": role,
                "key_id": key_id,
                "algorithm": "ed25519",
                "public_key_base64": public,
                "trust_level": "development",
                "created_at": "2026-08-18T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return key, public, key_id


def _sign(document: dict, key: Ed25519PrivateKey, role: str, public: str, key_id: str) -> dict:
    document = dict(document)
    document["signature"] = {
        "role": role,
        "key_id": key_id,
        "algorithm": "ed25519",
        "public_key_base64": public,
        "trust_level": "development",
        "signature_base64": base64.b64encode(key.sign(signed_payload_bytes(document))).decode(
            "ascii"
        ),
    }
    return document


def test_forged_signature_claiming_a_trusted_key_id_is_denied(tmp_path: Path) -> None:
    """An attacker may not sign with their own key while claiming a pinned key_id."""

    _, trusted_public, trusted_key_id = _identity("plan-signer", tmp_path)
    anchors = TrustAnchors.from_directory(tmp_path)
    attacker = Ed25519PrivateKey.generate()
    attacker_public = base64.b64encode(attacker.public_key().public_bytes_raw()).decode("ascii")
    forged = _sign(
        {"id": "dispatch.evil", "requested_kinds": ["destroy"]},
        attacker,
        "plan-signer",
        attacker_public,
        trusted_key_id,
    )
    with pytest.raises(RunnerDenialError) as caught:
        _verify_against_anchor(forged, anchors, "plan-signer", "dispatch envelope")
    assert caught.value.code == "OAK-RUNNER-TRUST"
    assert trusted_public != attacker_public


def test_genuine_signature_from_a_pinned_key_is_accepted(tmp_path: Path) -> None:
    key, public, key_id = _identity("plan-signer", tmp_path)
    anchors = TrustAnchors.from_directory(tmp_path)
    document = _sign({"id": "dispatch.good"}, key, "plan-signer", public, key_id)
    _verify_against_anchor(document, anchors, "plan-signer", "dispatch envelope")


def test_approver_key_may_not_sign_in_the_plan_signer_role(tmp_path: Path) -> None:
    key, public, key_id = _identity("approver", tmp_path)
    _identity("plan-signer", tmp_path)
    anchors = TrustAnchors.from_directory(tmp_path)
    document = _sign({"id": "dispatch.crossrole"}, key, "approver", public, key_id)
    with pytest.raises(RunnerDenialError) as caught:
        _verify_against_anchor(document, anchors, "plan-signer", "dispatch envelope")
    assert caught.value.code == "OAK-RUNNER-TRUST"


def test_empty_trust_directory_denies_everything(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    anchors = TrustAnchors.from_directory(tmp_path)
    document = _sign(
        {"id": "dispatch.unanchored"},
        key,
        "plan-signer",
        public,
        derive_key_id("plan-signer", public),
    )
    with pytest.raises(RunnerDenialError):
        _verify_against_anchor(document, anchors, "plan-signer", "dispatch envelope")


def test_anchor_with_a_mismatched_key_id_is_not_loaded(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    (tmp_path / "plan-signer.identity.json").write_text(
        json.dumps(
            {
                "role": "plan-signer",
                "key_id": "sha256:" + "0" * 64,
                "algorithm": "ed25519",
                "public_key_base64": public,
                "trust_level": "development",
                "created_at": "2026-08-18T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    assert TrustAnchors.from_directory(tmp_path).key_ids("plan-signer") == frozenset()


def test_image_reference_carrying_its_own_digest_is_refused() -> None:
    """The approved digest is the only pin permitted to reach the runtime."""

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        raise AssertionError("the adapter must refuse before executing anything")

    adapter = ContainerFixtureAdapter(executor)
    with pytest.raises(OAKError, match="must not carry its own digest"):
        adapter.apply(
            {
                "container_name": "oak-fixture-demo",
                "image_reference": "postgres:17.6-alpine@sha256:" + "b" * 64,
                "image_digest": "sha256:" + "a" * 64,
                "isolation": "network-none-never-started",
            },
            120,
        )


def test_approved_digest_is_always_the_pin() -> None:
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        return CommandResult(returncode=0, stdout="", stderr="")

    ContainerFixtureAdapter(executor).apply(
        {
            "container_name": "oak-fixture-demo",
            "image_reference": "postgres:17.6-alpine",
            "image_digest": "sha256:" + "a" * 64,
            "isolation": "network-none-never-started",
        },
        120,
    )
    assert calls[0][-1] == "postgres:17.6-alpine@sha256:" + "a" * 64
