# SPDX-License-Identifier: Apache-2.0
"""Shared Sprint 5 fixtures: a compiled case advanced to a signed dispatch."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from oak.adapters.dispatch import FilesystemMailbox
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.signing import LocalEd25519Signer, initialize_trust_directory
from oak.application import CommandContext, ReleaseService
from oak.bootstrap import (
    create_candidate_planning_service,
    create_design_case_service,
)
from oak.contracts import SchemaRegistry, load_yaml_document

ROOT = Path(__file__).resolve().parents[1]
BASE_TIME = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)


def _stamp(offset_seconds: int) -> str:
    return (
        (BASE_TIME + timedelta(seconds=offset_seconds))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class ReleaseHarness:
    workspace: Path
    trust_directory: Path
    mailbox_root: Path
    registry: SchemaRegistry
    release: ReleaseService
    now: str

    def context(
        self, key: str, version: str | None, *, actor: str = "local-user"
    ) -> CommandContext:
        return CommandContext(
            actor=actor,
            tenant_id="local",
            idempotency_key=key,
            expected_version=version,
            correlation_id=f"correlation-{key}",
            interface_origin="cli",
            occurred_at=self.now,
        )


def build_compiled_case(
    tmp_path: Path,
    *,
    target_name: str = "local-fixture.yaml",
    now: str | None = None,
) -> ReleaseHarness:
    """Drive a fresh workspace to bundle_compiled against the named target."""

    stamp = now or _stamp(0)
    workspace = tmp_path / "workspace"
    trust_directory = tmp_path / "trust"
    mailbox_root = tmp_path / "mailbox"
    initialize_trust_directory(trust_directory)
    registry = SchemaRegistry.from_directory(ROOT / "schemas")

    design = create_design_case_service(workspace)
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=stamp)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(stamp, "harness-design-000001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context(stamp, "harness-confirm-000001", "0.1.1"))
    planning = create_candidate_planning_service(workspace)
    planning.candidates(_context(stamp, "harness-candidates-000001", "0.1.2"))
    planning.evaluate("candidate-03", _context(stamp, "harness-evaluate-000001", "0.1.3"))
    planning.select("candidate-03", "balanced", _context(stamp, "harness-select-000001", "0.1.4"))
    planning.assure("candidate-03", _context(stamp, "harness-assure-000001", "0.1.5"))
    target = load_yaml_document(
        (ROOT / "examples/targets" / target_name).read_text(encoding="utf-8")
    )
    planning.plan_document("candidate-03", target, _context(stamp, "harness-plan-000001", "0.1.6"))

    release = ReleaseService(
        FileWorkspaceRepository(workspace, registry),
        registry,
        lambda role: LocalEd25519Signer.load(trust_directory, role),
        FilesystemMailbox(mailbox_root),
    )
    return ReleaseHarness(
        workspace=workspace,
        trust_directory=trust_directory,
        mailbox_root=mailbox_root,
        registry=registry,
        release=release,
        now=stamp,
    )


def _context(stamp: str, key: str, version: str | None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=stamp,
    )


def read_dispatch(mailbox_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Return the single delivered envelope and its attachments."""

    import json

    dispatch_dir = next((mailbox_root / "dispatches").iterdir())
    envelope = json.loads((dispatch_dir / "envelope.json").read_text(encoding="utf-8"))
    attachments: dict[str, dict[str, Any]] = {}
    for path in dispatch_dir.glob("*.json"):
        if path.name != "envelope.json":
            attachments[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return envelope, attachments


def tamper(document: dict[str, Any], pointer: str, value: Any) -> dict[str, Any]:
    """Return a deep copy with one field replaced, leaving the signature stale."""

    clone = copy.deepcopy(document)
    parts = pointer.strip("/").split("/")
    cursor: Any = clone
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    key = parts[-1]
    if isinstance(cursor, list):
        cursor[int(key)] = value
    else:
        cursor[key] = value
    return clone


def with_time(stamp: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (
        (parsed + timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


__all__ = [
    "ROOT",
    "ReleaseHarness",
    "build_compiled_case",
    "read_dispatch",
    "replace",
    "tamper",
    "with_time",
]
