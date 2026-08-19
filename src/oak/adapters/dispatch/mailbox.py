# SPDX-License-Identifier: Apache-2.0
"""Filesystem mailbox transport for Community local mode.

The control plane writes signed dispatch envelopes, content-addressed
attachments, and revocation notices into the mailbox; the runner reads them and
writes signed protocol messages back. Neither side opens a network listener,
and every document is re-verified by its consumer — a tampered mailbox file is
an expected adversarial case, not a trusted input.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from oak.domain import OAKError, canonical_json_bytes

MAXIMUM_MESSAGE_BYTES = 1_048_576
DISPATCH_DIRECTORY = "dispatches"
REVOCATION_DIRECTORY = "revocations"
MESSAGE_DIRECTORY = "messages"
ACKNOWLEDGED_DIRECTORY = "acknowledged"


class FilesystemMailbox:
    def __init__(self, root: Path) -> None:
        self._root = root

    def deliver(
        self,
        envelope: dict[str, Any],
        attachments: dict[str, dict[str, Any]],
    ) -> None:
        dispatch_id = str(envelope["id"])
        _check_component(dispatch_id)
        directory = self._root / DISPATCH_DIRECTORY / dispatch_id
        if directory.exists():
            raise OAKError("OAK-DISPATCH-EXISTS", "dispatch envelope was already delivered")
        directory.mkdir(parents=True, mode=0o700)
        _write_document(directory / "envelope.json", envelope)
        for name, document in attachments.items():
            _check_component(name)
            _write_document(directory / f"{name}.json", document)

    def publish_revocation(self, notice: dict[str, Any]) -> None:
        directory = self._root / REVOCATION_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = str(notice["id"])
        _check_component(name)
        _write_document(directory / f"{name}.json", notice, overwrite=True)

    def read_messages(self) -> tuple[dict[str, Any], ...]:
        directory = self._root / MESSAGE_DIRECTORY
        if not directory.is_dir():
            return ()
        documents: list[dict[str, Any]] = []
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix != ".json":
                continue
            if path.stat().st_size > MAXIMUM_MESSAGE_BYTES:
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict):
                documents.append(document)
        return tuple(documents)

    def acknowledge(self, message_id: str) -> None:
        _check_component(message_id)
        source = self._root / MESSAGE_DIRECTORY / f"{message_id}.json"
        destination = self._root / ACKNOWLEDGED_DIRECTORY
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        if source.is_file():
            os.replace(source, destination / source.name)


def _write_document(path: Path, document: dict[str, Any], *, overwrite: bool = False) -> None:
    payload = canonical_json_bytes(document)
    if len(payload) > MAXIMUM_MESSAGE_BYTES:
        raise OAKError("OAK-DISPATCH-SIZE", "dispatch document exceeds the mailbox bound")
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def _check_component(value: str) -> None:
    if not value or "/" in value or "\\" in value or value.startswith("."):
        raise OAKError("OAK-DISPATCH-NAME", "mailbox document name is unsafe")
