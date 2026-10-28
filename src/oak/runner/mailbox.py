# SPDX-License-Identifier: Apache-2.0
"""Runner-side mailbox access: read dispatches, publish signed messages."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from oak.domain import OAKError, canonical_json_bytes
from oak.runner.identity import RunnerIdentity

MAXIMUM_DOCUMENT_BYTES = 1_048_576
DISPATCH_DIRECTORY = "dispatches"
REVOCATION_DIRECTORY = "revocations"
REVOCATION_MANIFEST_NAME = "manifest.json"
MESSAGE_DIRECTORY = "messages"
ACKNOWLEDGED_DIRECTORY = "acknowledged"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
PROCESSED_MARKER = ".processed"


class RunnerMailbox:
    def __init__(self, root: Path, home: Path) -> None:
        self._root = root
        self._home = home

    def pending_dispatches(
        self,
    ) -> tuple[tuple[str, dict[str, Any], dict[str, dict[str, Any]]], ...]:
        """Yield (directory name, envelope, attachments).

        The directory name is authoritative for bookkeeping; the envelope's own
        id is an unverified claim at this point and must never build a path.
        """

        directory = self._root / DISPATCH_DIRECTORY
        if not directory.is_dir():
            return ()
        results: list[tuple[str, dict[str, Any], dict[str, dict[str, Any]]]] = []
        for dispatch_dir in sorted(directory.iterdir()):
            if not dispatch_dir.is_dir() or (dispatch_dir / PROCESSED_MARKER).exists():
                continue
            if not is_safe_name(dispatch_dir.name):
                # A name no control plane delivers (`a..b`) is left alone rather than
                # taken up: its bookkeeping would fail, and every later dispatch with it.
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
            results.append((dispatch_dir.name, envelope, attachments))
        return tuple(results)

    def unsafe_dispatch_names(self) -> tuple[str, ...]:
        directory = self._root / DISPATCH_DIRECTORY
        if not directory.is_dir():
            return ()
        return tuple(
            sorted(
                path.name
                for path in directory.iterdir()
                if path.is_dir()
                and not is_safe_name(path.name)
                and not (path / PROCESSED_MARKER).exists()
            )
        )

    def completion_published(self, message_id: str) -> bool:
        """Whether a message with this id is in the mailbox, read or not yet read."""

        if not is_safe_name(message_id):
            return False
        return any(
            (self._root / directory / f"{message_id}.json").exists()
            for directory in (MESSAGE_DIRECTORY, ACKNOWLEDGED_DIRECTORY)
        )

    def dispatch_lease_id(self, dispatch_id: str) -> str | None:
        """The lease a delivered dispatch names, if its envelope is still in the mailbox."""

        if not is_safe_name(dispatch_id):
            return None
        envelope = _read_document(self._root / DISPATCH_DIRECTORY / dispatch_id / "envelope.json")
        lease = envelope.get("lease") if envelope is not None else None
        lease_id = lease.get("lease_id") if isinstance(lease, dict) else None
        return lease_id if is_safe_name(lease_id) else None

    def completions(self, correlation_ids: frozenset[str]) -> tuple[dict[str, Any], ...]:
        """Every completion in the mailbox, read or not, for one of these correlations.

        Unverified: the caller checks each signature against the key it trusts.
        """

        found: list[dict[str, Any]] = []
        for directory in (MESSAGE_DIRECTORY, ACKNOWLEDGED_DIRECTORY):
            folder = self._root / directory
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("runner-message.completion.*.json")):
                document = _read_document(path)
                if (
                    document is not None
                    and document.get("kind") == "completion"
                    and document.get("correlation_id") in correlation_ids
                ):
                    found.append(document)
        return tuple(found)

    def mark_processed(self, dispatch_id: str) -> None:
        _check_component(dispatch_id)
        marker = self._root / DISPATCH_DIRECTORY / dispatch_id / PROCESSED_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("processed\n", encoding="utf-8")

    def revocation_documents(self) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], ...]]:
        """Read the revocation manifest and every notice, failing closed on anything odd.

        The channel used to fail open four ways: a missing directory, an unreadable or
        oversized file, and a malformed document all read as "nothing revoked", so
        deleting a notice restored a revoked approval (RR-001). Every one of those is now
        a refusal — a runner that cannot prove what is revoked must not guess. The
        manifest (a signed inventory of the whole set) is returned separately for
        verification; its absence is an acceptable state only for a mailbox that has
        never carried a dispatch, which verification decides, not this reader. Hidden
        files are ignored (no valid notice can be named with a leading dot; the producer
        refuses such names), so stray filesystem metadata cannot brick the channel.
        """

        directory = self._root / REVOCATION_DIRECTORY
        try:
            entries = sorted(directory.iterdir())
        except OSError as error:
            raise OAKError(
                "OAK-RUNNER-REVOCATION",
                "revocation directory is missing or unreadable",
            ) from error
        manifest: dict[str, Any] | None = None
        documents: list[dict[str, Any]] = []
        for path in entries:
            if path.name.startswith("."):
                continue
            if not path.is_file() or path.suffix != ".json":
                raise OAKError(
                    "OAK-RUNNER-REVOCATION",
                    "revocation directory contains an entry that is not a notice",
                )
            try:
                if path.stat().st_size > MAXIMUM_DOCUMENT_BYTES:
                    raise OAKError(
                        "OAK-RUNNER-REVOCATION",
                        "revocation notice exceeds the mailbox bound",
                    )
                document = json.loads(path.read_text(encoding="utf-8"))
            except OAKError:
                raise
            except (OSError, ValueError) as error:
                raise OAKError(
                    "OAK-RUNNER-REVOCATION",
                    "revocation notice is unreadable",
                ) from error
            if not isinstance(document, dict):
                raise OAKError(
                    "OAK-RUNNER-REVOCATION",
                    "revocation notice is not a document",
                )
            if path.name == REVOCATION_MANIFEST_NAME:
                manifest = document
            else:
                documents.append(document)
        return manifest, tuple(documents)

    def last_revocation_sequence(self) -> int:
        """The highest manifest sequence this runner has accepted; -1 before any.

        Persisted in the runner's own home so a mailbox rolled back to an older —
        validly signed — revocation set is refused rather than believed. An unreadable
        record fails closed like the ledger it protects.
        """

        path = self._home / "revocation-sequence.json"
        if not path.is_file():
            return -1
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise OAKError(
                "OAK-RUNNER-REVOCATION",
                "the recorded revocation-manifest sequence is unreadable",
            ) from error
        if not isinstance(value, int):
            raise OAKError(
                "OAK-RUNNER-REVOCATION",
                "the recorded revocation-manifest sequence is not a number",
            )
        return value

    def record_revocation_sequence(self, sequence: int) -> None:
        path = self._home / "revocation-sequence.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        scratch = path.with_name(path.name + ".tmp")
        scratch.write_text(json.dumps(int(sequence)) + "\n", encoding="utf-8")
        os.replace(scratch, path)

    def consumed_lease_nonces(self) -> frozenset[str]:
        """The replay ledger, failing closed on corruption.

        This used to return an empty set for an unreadable or malformed file — and
        because `consume_lease_nonce` rewrites the file from this reader's result, one
        corrupt read did not merely fail open once: the next consume permanently erased
        every previously burned nonce. A ledger that cannot be read now refuses
        (`OAK-RUNNER-REPLAY`) until an operator inspects or removes it deliberately.
        """

        path = self._home / "consumed-nonces.json"
        if not path.is_file():
            return frozenset()
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise OAKError(
                "OAK-RUNNER-REPLAY",
                "the consumed-nonce ledger is unreadable; refusing to treat it as empty",
            ) from error
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise OAKError(
                "OAK-RUNNER-REPLAY",
                "the consumed-nonce ledger is malformed; refusing to treat it as empty",
            )
        return frozenset(values)

    def consume_lease_nonce(self, nonce: str) -> None:
        nonces = sorted({*self.consumed_lease_nonces(), nonce})
        path = self._home / "consumed-nonces.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        scratch = path.with_name(path.name + ".tmp")
        scratch.write_text(json.dumps(nonces) + "\n", encoding="utf-8")
        os.replace(scratch, path)

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
        # The id names the file; a correlation copied from an unverified envelope must
        # never build a path (F4-11).
        _check_component(str(message["id"]))
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


def is_safe_name(value: object) -> bool:
    """A name that can only ever name one entry inside its own directory."""

    return isinstance(value, str) and bool(SAFE_NAME.fullmatch(value)) and ".." not in value


def _check_component(value: str) -> None:
    """Refuse any self-declared name that could escape its directory."""

    if not is_safe_name(value):
        raise ValueError("mailbox document name is unsafe")


def _read_document(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAXIMUM_DOCUMENT_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None
