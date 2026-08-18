# SPDX-License-Identifier: Apache-2.0
"""Runner-side mailbox access: read dispatches, publish signed messages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from oak.domain import canonical_json_bytes
from oak.runner.identity import RunnerIdentity

MAXIMUM_DOCUMENT_BYTES = 1_048_576
DISPATCH_DIRECTORY = "dispatches"
REVOCATION_DIRECTORY = "revocations"
MESSAGE_DIRECTORY = "messages"
PROCESSED_MARKER = ".processed"


class RunnerMailbox:
    def __init__(self, root: Path, home: Path) -> None:
        self._root = root
        self._home = home

    def pending_dispatches(self) -> tuple[tuple[dict[str, Any], dict[str, dict[str, Any]]], ...]:
        directory = self._root / DISPATCH_DIRECTORY
        if not directory.is_dir():
            return ()
        results: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
        for dispatch_dir in sorted(directory.iterdir()):
            if not dispatch_dir.is_dir() or (dispatch_dir / PROCESSED_MARKER).exists():
                continue
            envelope = _read_document(dispatch_dir / "envelope.json")
            if envelope is None:
                continue
            attachments: dict[str, dict[str, Any]] = {}
            for path in sorted(dispatch_dir.glob("*.json")):
                if path.name == "envelope.json":
                    continue
                document = _read_document(path)
                if document is not None:
                    attachments[path.stem] = document
            results.append((envelope, attachments))
        return tuple(results)

    def mark_processed(self, dispatch_id: str) -> None:
        marker = self._root / DISPATCH_DIRECTORY / dispatch_id / PROCESSED_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("processed\n", encoding="utf-8")

    def revoked_approval_ids(self) -> frozenset[str]:
        directory = self._root / REVOCATION_DIRECTORY
        if not directory.is_dir():
            return frozenset()
        revoked: set[str] = set()
        for path in directory.glob("*.json"):
            document = _read_document(path)
            if document is not None and isinstance(document.get("approval_id"), str):
                revoked.add(document["approval_id"])
        return frozenset(revoked)

    def consumed_lease_nonces(self) -> frozenset[str]:
        path = self._home / "consumed-nonces.json"
        if not path.is_file():
            return frozenset()
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return frozenset()
        return frozenset(str(value) for value in values if isinstance(value, str))

    def consume_lease_nonce(self, nonce: str) -> None:
        nonces = sorted({*self.consumed_lease_nonces(), nonce})
        path = self._home / "consumed-nonces.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(nonces) + "\n", encoding="utf-8")

    def publish_message(
        self,
        identity: RunnerIdentity,
        *,
        kind: str,
        tenant_id: str,
        environment: str,
        correlation_id: str,
        sequence: int,
        lease_id: str | None,
        operation_id: str | None,
        occurred_at: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        import hashlib

        message: dict[str, Any] = {
            "schema_version": "0.1.0",
            "protocol_version": "0.1.0",
            "id": f"runner-message.{kind}.{correlation_id}.{sequence}",
            "version": "0.1.0",
            "kind": kind,
            "runner_id": identity.runner_id,
            "tenant_id": tenant_id,
            "environment": environment,
            "correlation_id": correlation_id,
            "sequence": sequence,
            "lease_id": lease_id,
            "operation_id": operation_id,
            "occurred_at": occurred_at,
            "nonce": hashlib.sha256(
                f"{identity.runner_id}\n{correlation_id}\n{sequence}\n{kind}".encode()
            ).hexdigest(),
            "payload": payload,
            "extensions": {},
        }
        message["signature"] = identity.signature_block(canonical_json_bytes(message))
        directory = self._root / MESSAGE_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload_bytes = canonical_json_bytes(message)
        if len(payload_bytes) > MAXIMUM_DOCUMENT_BYTES:
            raise ValueError("runner message exceeds the mailbox bound")
        descriptor = os.open(
            directory / f"{message['id']}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload_bytes)
        return message


def _read_document(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAXIMUM_DOCUMENT_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None
