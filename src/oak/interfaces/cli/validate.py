# SPDX-License-Identifier: Apache-2.0
"""Headless validation of exported cases, compiled bundles, and signed webhooks.

Suitable for CI and portal pipelines: no live server, no network, no mutation.
Every check fails closed with a stable ``OAK-VALIDATE-*`` or import error code.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from oak.bootstrap import canonical_schema_directory, create_design_case_service
from oak.contracts import SchemaRegistry, load_json_document, load_yaml_document
from oak.contracts.signatures import signed_payload_bytes, verify_signature
from oak.domain import OAKError, canonical_json_bytes, content_digest

MAXIMUM_DOCUMENT_BYTES = 8_388_608
FORBIDDEN_EXECUTION_KEYS = frozenset({"argv", "command", "executable", "shell", "shell_command"})
BUNDLE_FILES: dict[str, str] = {
    "architecture-decision.json": "architecture-decision.schema.json",
    "assurance-plan.json": "assurance-plan.schema.json",
    "semantic-manifest.json": "review-artifact.schema.json",
    "deployment-bundle.json": "deployment-bundle.schema.json",
    "runner-plan.json": "runner-plan.schema.json",
}


def _read_bounded(path: Path) -> bytes:
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise OAKError("OAK-VALIDATE-UNSAFE-PATH", "input must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise OAKError("OAK-VALIDATE-UNSAFE-PATH", "input could not be opened safely") from error
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode):
            raise OAKError("OAK-VALIDATE-UNSAFE-PATH", "input must be a regular file")
        if details.st_size < 1 or details.st_size > MAXIMUM_DOCUMENT_BYTES:
            raise OAKError("OAK-VALIDATE-SIZE", "input size is outside the accepted range")
        content = stream.read(MAXIMUM_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAXIMUM_DOCUMENT_BYTES:
        raise OAKError("OAK-VALIDATE-SIZE", "input size is outside the accepted range")
    return content


def _reject_execution_fields(value: Any, *, name: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in FORBIDDEN_EXECUTION_KEYS:
                raise OAKError(
                    "OAK-VALIDATE-EXECUTION-FIELD",
                    f"{name} contains a prohibited execution field",
                )
            _reject_execution_fields(nested, name=name)
    elif isinstance(value, list):
        for nested in value:
            _reject_execution_fields(nested, name=name)


def validate_export(source: Path) -> dict[str, Any]:
    """Import the export into a throwaway workspace, proving schema/digest/lineage."""

    with tempfile.TemporaryDirectory(prefix="oak-validate-export-") as temporary:
        service = create_design_case_service(Path(temporary) / "workspace")
        service.import_from(source.absolute())
        result = service.current()
    case = result.case
    return {
        "kind": "export",
        "valid": True,
        "case_id": str(case["id"]),
        "case_version": str(case["version"]),
        "status": str(case["status"]),
    }


def validate_bundle(source: Path) -> dict[str, Any]:
    """Verify a compiled review bundle: schemas, digest links, and inertness."""

    directory = source.absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise OAKError("OAK-VALIDATE-UNSAFE-PATH", "bundle must be a regular directory")
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    documents: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for name, schema in BUNDLE_FILES.items():
        content = _read_bounded(directory / name)
        try:
            document = load_json_document(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise OAKError("OAK-VALIDATE-MALFORMED", f"{name} is not canonical JSON") from error
        registry.validate(schema, document)
        _reject_execution_fields(document, name=name)
        documents[name] = document
        digests[name] = content_digest(canonical_json_bytes(document))
    runner_plan = documents["runner-plan.json"]
    bundle = documents["deployment-bundle.json"]
    if runner_plan["bundle_ref"]["digest"] != digests["deployment-bundle.json"]:
        raise OAKError(
            "OAK-VALIDATE-DIGEST",
            "runner plan does not reference this deployment bundle",
        )
    if bundle["architecture_decision_ref"]["digest"] != digests["architecture-decision.json"]:
        raise OAKError(
            "OAK-VALIDATE-DIGEST",
            "deployment bundle does not reference this architecture decision",
        )
    if str(runner_plan["status"]) != "draft":
        raise OAKError("OAK-VALIDATE-PLAN-STATUS", "runner plan is not an inert draft")
    return {
        "kind": "bundle",
        "valid": True,
        "bundle_id": str(bundle["id"]),
        "runner_plan_id": str(runner_plan["id"]),
        "digests": digests,
    }


def _pinned_public_key(value: str) -> str:
    """Accept a base64 key value or a path to a publisher identity document."""

    candidate = Path(value)
    if candidate.suffix.lower() == ".json" and candidate.is_file():
        content = _read_bounded(candidate)
        try:
            identity = load_json_document(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise OAKError("OAK-VALIDATE-KEY", "publisher identity document is invalid") from error
        public_key = identity.get("public_key_base64")
        if not isinstance(public_key, str) or not public_key:
            raise OAKError("OAK-VALIDATE-KEY", "publisher identity carries no public key")
        return public_key
    return value


def validate_webhook(path: Path, pinned_key: str) -> dict[str, Any]:
    """Verify a signed webhook envelope against a pinned publisher key.

    The key embedded in the envelope is never trusted: it must equal the pinned
    key, and the signature is verified with the pinned key alone.
    """

    public_key = _pinned_public_key(pinned_key)
    content = _read_bounded(path)
    try:
        text = content.decode("utf-8")
        envelope = (
            load_json_document(text) if path.suffix.lower() == ".json" else load_yaml_document(text)
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise OAKError("OAK-VALIDATE-MALFORMED", "webhook envelope is malformed") from error
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    registry.validate("webhook-envelope.schema.json", envelope)
    signature = envelope["signature"]
    if signature["public_key_base64"] != public_key:
        raise OAKError(
            "OAK-VALIDATE-WEBHOOK-KEY",
            "envelope signer does not match the pinned publisher key",
        )
    expected_key_id = content_digest(
        canonical_json_bytes(
            {
                "algorithm": "ed25519",
                "public_key_base64": public_key,
                "role": "webhook-publisher",
            }
        )
    )
    if signature["key_id"] != expected_key_id:
        raise OAKError(
            "OAK-VALIDATE-WEBHOOK-KEY",
            "envelope key id does not derive from the pinned publisher key",
        )
    if not verify_signature(
        algorithm=str(signature["algorithm"]),
        public_key_base64=public_key,
        message=signed_payload_bytes(envelope),
        signature_base64=str(signature["signature_base64"]),
    ):
        raise OAKError(
            "OAK-VALIDATE-WEBHOOK-SIGNATURE",
            "envelope signature does not verify under the pinned publisher key",
        )
    event = envelope["event"]
    return {
        "kind": "webhook",
        "valid": True,
        "delivery_id": str(envelope["delivery_id"]),
        "case_id": str(envelope["case_id"]),
        "sequence": int(envelope["sequence"]),
        "event_type": str(event["event_type"]),
    }


__all__ = ["validate_bundle", "validate_export", "validate_webhook"]
