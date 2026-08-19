# SPDX-License-Identifier: Apache-2.0
"""The oak-runner entrypoint: outbound-only, independently verifying, journaled.

The runner reads its mailbox, its trust anchors, and its own target profile; it
holds no control-plane database credential and opens no listening socket.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oak.contracts import load_yaml_document
from oak.domain import OAKError
from oak.runner.execution import execute_dispatch
from oak.runner.identity import RunnerIdentity
from oak.runner.journal import RunnerJournal
from oak.runner.mailbox import RunnerMailbox
from oak.runner.schemas import load_registry
from oak.runner.verification import RunnerDenialError, TrustAnchors, verify_dispatch


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _environment_path(name: str, default: str | None = None) -> Path:
    value = os.getenv(name, default)
    if not value:
        print(f"{name} is required", file=sys.stderr)
        raise SystemExit(64)
    return Path(value).absolute()


def run_once(*, cancellation_requested: bool = False) -> int:
    mailbox_root = _environment_path("OAK_RUNNER_MAILBOX")
    home = _environment_path("OAK_RUNNER_HOME", str(Path.home() / ".oak" / "runner"))
    trust_directory = _environment_path("OAK_RUNNER_TRUST_ANCHORS")
    target_path = _environment_path("OAK_RUNNER_TARGET_PROFILE")
    runner_id = os.getenv("OAK_RUNNER_ID", "runner.local-fixture-runner")

    registry = load_registry()
    target_document = load_yaml_document(target_path.read_text(encoding="utf-8"))
    registry.validate("target-profile.schema.json", target_document)
    identity = RunnerIdentity.load_or_create(home, runner_id)
    mailbox = RunnerMailbox(mailbox_root, home)
    anchors = TrustAnchors.from_directory(trust_directory)
    now = _now()

    processed_any = False
    for dispatch_id, envelope, attachments in mailbox.pending_dispatches():
        # dispatch_id comes from the filesystem, never from the unverified envelope.
        correlation = str(envelope.get("lease", {}).get("lease_id", dispatch_id) or dispatch_id)
        try:
            verified = verify_dispatch(
                envelope=envelope,
                attachments=attachments,
                registry=registry,
                anchors=anchors,
                target_document=target_document,
                revoked_approval_ids=mailbox.revoked_approval_ids(),
                seen_lease_nonces=mailbox.consumed_lease_nonces(),
                now=now,
            )
        except (RunnerDenialError, OAKError) as denial:
            _publish_denial(mailbox, identity, envelope, denial, now, correlation)
            mailbox.mark_processed(dispatch_id)
            processed_any = True
            print(f"denied {dispatch_id}: {denial}", file=sys.stderr)
            continue
        mailbox.consume_lease_nonce(str(envelope["lease"]["nonce"]))
        journal = RunnerJournal(home / "journals" / f"{dispatch_id}.jsonl")
        journal.verify_chain()
        outcome = execute_dispatch(
            verified,
            journal=journal,
            target_document=target_document,
            registry=registry,
            now=now,
            cancellation_requested=cancellation_requested,
        )
        mailbox.publish_message(
            identity,
            kind="completion",
            tenant_id=str(envelope["tenant_id"]),
            environment=str(envelope["environment"]),
            correlation_id=correlation,
            sequence=1,
            lease_id=str(envelope["lease"]["lease_id"]),
            operation_id=None,
            occurred_at=_now(),
            payload={
                "outcome": outcome.outcome,
                "applied_kinds": list(outcome.applied_kinds),
                "journal_digest": outcome.journal_digest,
                "detail": outcome.detail,
                "evidence": list(outcome.evidence),
            },
        )
        mailbox.mark_processed(dispatch_id)
        processed_any = True
        print(f"completed {dispatch_id}: {outcome.outcome}")
    if not processed_any:
        print("no pending dispatches")
    return 0


def _publish_denial(
    mailbox: RunnerMailbox,
    identity: RunnerIdentity,
    envelope: dict[str, Any],
    denial: OAKError,
    now: str,
    correlation: str,
) -> None:
    with contextlib.suppress(OSError, ValueError):
        mailbox.publish_message(
            identity,
            kind="completion",
            tenant_id=str(envelope.get("tenant_id", "local")),
            environment=str(envelope.get("environment", "development")),
            correlation_id=correlation or "correlation-denied",
            sequence=1,
            lease_id=None,
            operation_id=None,
            occurred_at=now,
            payload={
                "outcome": "denied",
                "applied_kinds": [],
                "denial_code": denial.code,
                "detail": str(denial),
            },
        )


def status() -> int:
    home = _environment_path("OAK_RUNNER_HOME", str(Path.home() / ".oak" / "runner"))
    journals = sorted((home / "journals").glob("*.jsonl")) if (home / "journals").is_dir() else []
    report: dict[str, Any] = {"journals": []}
    for path in journals:
        journal = RunnerJournal(path)
        try:
            journal.verify_chain()
            chain = "verified"
        except OAKError:
            chain = "tampered"
        report["journals"].append(
            {
                "dispatch": path.stem,
                "entries": len(journal.entries()),
                "chain": chain,
                "manual_recovery_required": journal.requires_manual_recovery(),
            }
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="oak-runner",
        description=(
            "Outbound-only OAK runner: independently verifies signed dispatches "
            "before any target access."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    run_parser = subcommands.add_parser("run-once", help="process pending dispatches once")
    run_parser.add_argument(
        "--cancel",
        action="store_true",
        help="observe a cooperative cancellation before the next operation",
    )
    subcommands.add_parser("status", help="report journal integrity and recovery state")
    arguments = parser.parse_args()
    try:
        if arguments.command == "run-once":
            return run_once(cancellation_requested=bool(arguments.cancel))
        return status()
    except OAKError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
