# SPDX-License-Identifier: Apache-2.0
"""The oak-runner entrypoint: outbound-only, independently verifying, journaled.

The runner reads its mailbox, its trust anchors, and its own target profile; it
holds no control-plane database credential and opens no listening socket.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import load_yaml_document
from oak.contracts.signatures import verify_signed_document
from oak.domain import OAKError
from oak.runner.adapters import ContainerFixtureAdapter, isolated_executor
from oak.runner.execution import execute_dispatch
from oak.runner.identity import RunnerIdentity
from oak.runner.journal import RunnerJournal
from oak.runner.mailbox import RunnerMailbox, is_safe_name
from oak.runner.schemas import load_registry
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    verified_revocations,
    verify_dispatch,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _environment_path(name: str, default: str | None = None) -> Path:
    value = os.getenv(name, default)
    if not value:
        # `CODE: message` on stderr is the documented diagnostic contract for every
        # entrypoint; this path used to emit a bare sentence with no code.
        print(f"OAK-RUNNER-CONFIG: {name} is required", file=sys.stderr)
        raise SystemExit(64)
    return Path(value).absolute()


def run_once(
    *,
    cancellation_requested: bool = False,
    adapter: ContainerFixtureAdapter | None = None,
) -> int:
    """Process pending dispatches once. ``adapter`` is a test seam, never a CLI option.

    One run at a time per runner home: a second run started while an install is still
    in its readiness wait would otherwise take the first run's journal for an interrupted
    one and report it, mid-install, as needing recovery (F4-5).
    """

    home = _environment_path("OAK_RUNNER_HOME", str(Path.home() / ".oak" / "runner"))
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(home / "run.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OAKError(
                "OAK-RUNNER-BUSY", "another oak-runner run-once is using this runner home"
            ) from error
        with _run_directory(home) as work:
            return _run_once_locked(
                home, work, cancellation_requested=cancellation_requested, adapter=adapter
            )
    finally:
        os.close(lock)


@contextlib.contextmanager
def _run_directory(home: Path) -> Iterator[Path]:
    """A private, empty working directory for this run's children, removed when it ends.

    A child the runner starts never runs in the directory the operator started the runner
    from (RR-027). The caller holds the run lock, so a `run-*` directory already in the
    home was left by a run that crashed, and is removed before this one starts.
    """

    for stale in home.glob("run-*"):
        if stale.is_dir() and not stale.is_symlink():
            shutil.rmtree(stale, ignore_errors=True)
    try:
        directory = Path(tempfile.mkdtemp(prefix="run-", dir=home))
    except OSError as error:
        raise OAKError(
            "OAK-RUNNER-CONFIG", "the runner home has no room for a working directory"
        ) from error
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _run_once_locked(
    home: Path,
    work: Path,
    *,
    cancellation_requested: bool,
    adapter: ContainerFixtureAdapter | None,
) -> int:
    mailbox_root = _environment_path("OAK_RUNNER_MAILBOX")
    trust_directory = _environment_path("OAK_RUNNER_TRUST_ANCHORS")
    target_path = _environment_path("OAK_RUNNER_TARGET_PROFILE")
    runner_id = os.getenv("OAK_RUNNER_ID", "runner.local-fixture-runner")

    # Configuration failures must arrive as a stable code, not a traceback. An
    # unreadable profile used to raise OSError and a malformed one ContractValidationError
    # (a ValueError); `main` catches only OAKError, so both escaped as a Python traceback
    # that disclosed absolute paths and profile fragments on an operator's terminal.
    registry = load_registry()
    try:
        target_document = load_yaml_document(target_path.read_text(encoding="utf-8"))
        registry.validate("target-profile.schema.json", target_document)
    except OSError as error:
        raise OAKError(
            "OAK-RUNNER-CONFIG", "OAK_RUNNER_TARGET_PROFILE could not be read"
        ) from error
    # `yaml.YAMLError` is not a `ValueError`; the same pair is caught at every other
    # untrusted-YAML boundary in the codebase (local_file.py, local_profile.py,
    # local_catalogue.py, cli/main.py). The runner was the one that missed it.
    except (ValueError, yaml.YAMLError) as error:
        raise OAKError(
            "OAK-RUNNER-CONFIG", "OAK_RUNNER_TARGET_PROFILE is not a valid target profile"
        ) from error
    try:
        identity = RunnerIdentity.load_or_create(home, runner_id)
        mailbox = RunnerMailbox(mailbox_root, home)
        anchors = TrustAnchors.from_directory(trust_directory)
    except OSError as error:
        raise OAKError(
            "OAK-RUNNER-CONFIG", "the runner home, mailbox or trust anchors are unreadable"
        ) from error
    # Resolved once for the whole run: every dispatch runs the same `docker` (RR-002).
    executor = isolated_executor(home / "docker-config", working_directory=work)
    processed_any = False
    for unsafe in mailbox.unsafe_dispatch_names():
        print(f"skipped {unsafe!r}: not a dispatch name a control plane delivers", file=sys.stderr)
    for dispatch_id, envelope, attachments in mailbox.pending_dispatches():
        # Each dispatch is judged at the moment it is taken up, not at the start of the
        # run: an earlier long install must not stretch a later dispatch's lease.
        now = _now()
        journal = RunnerJournal(home / "journals" / f"{dispatch_id}.jsonl")
        if _resume_interrupted(journal, mailbox, identity, envelope, dispatch_id, now):
            processed_any = True
            continue
        # dispatch_id comes from the filesystem, never from the unverified envelope.
        # The lease block is untrusted and unvalidated at this point — the schema check
        # happens inside `verify_dispatch`, below — so its *shape* cannot be assumed
        # either. An envelope carrying `"lease": null` used to raise AttributeError here,
        # outside the try, killing the runner before it could deny anything.
        lease = envelope.get("lease")
        lease_id = lease.get("lease_id") if isinstance(lease, dict) else None
        safe_lease = lease_id if is_safe_name(lease_id) else None
        correlation = safe_lease or dispatch_id
        try:
            manifest, notices = mailbox.revocation_documents()
            revocations = verified_revocations(
                manifest,
                notices,
                registry=registry,
                anchors=anchors,
                minimum_sequence=mailbox.last_revocation_sequence(),
            )
            mailbox.record_revocation_sequence(revocations.sequence)
            verified = verify_dispatch(
                envelope=envelope,
                attachments=attachments,
                registry=registry,
                anchors=anchors,
                target_document=target_document,
                revoked_approval_ids=revocations.approval_ids,
                seen_lease_nonces=mailbox.consumed_lease_nonces(),
                now=now,
            )
        except (RunnerDenialError, OAKError) as denial:
            _publish_denial(mailbox, identity, envelope, denial, now, correlation, safe_lease)
            mailbox.mark_processed(dispatch_id)
            processed_any = True
            print(f"denied {dispatch_id}: {denial}", file=sys.stderr)
            continue
        mailbox.consume_lease_nonce(str(envelope["lease"]["nonce"]))
        journal.verify_chain()
        outcome = execute_dispatch(
            verified,
            journal=journal,
            target_document=target_document,
            registry=registry,
            now=now,
            cancellation_requested=cancellation_requested,
            adapter=adapter or ContainerFixtureAdapter(executor),
        )
        try:
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
                    # What was asked for and what failed, so a completion alone says
                    # whether an install was attempted even when nothing was applied
                    # (OAK-FR-DEP-004).
                    "requested_kinds": list(verified.requested_kinds),
                    "applied_kinds": list(outcome.applied_kinds),
                    "failed_kind": outcome.failed_kind,
                    "journal_digest": outcome.journal_digest,
                    "journal_sequence": outcome.journal_sequence,
                    "detail": outcome.detail,
                    "evidence": list(outcome.evidence),
                },
            )
            mailbox.mark_processed(dispatch_id)
        except (OSError, ValueError) as error:
            # After side effects, a filesystem error is a stable code, never a
            # traceback; the journal holds the outcome and the next run reports it.
            raise OAKError(
                "OAK-RUNNER-MAILBOX",
                f"the completion for {dispatch_id} could not be published; its journal "
                "records the outcome",
            ) from error
        processed_any = True
        print(f"completed {dispatch_id}: {outcome.outcome}")
    if not processed_any:
        print("no pending dispatches")
    return 0


def _resume_interrupted(
    journal: RunnerJournal,
    mailbox: RunnerMailbox,
    identity: RunnerIdentity,
    envelope: dict[str, Any],
    dispatch_id: str,
    now: str,
) -> bool:
    """Report a dispatch an earlier run started but never finished; never re-run it.

    A dispatch whose journal already has entries was taken up before: its nonce is spent,
    so re-verifying it could only ever end in a replay denial that says nothing was done —
    while containers may exist. Instead the interruption is recorded where `status` and
    the control plane can see it: a `manual_recovery_required` journal entry naming the
    open operation and its resources, and a signed completion saying so.
    """

    try:
        entries = journal.entries()
    except OAKError:
        entries = ()
    if not entries:
        return False
    lease = envelope.get("lease")
    lease_id = lease.get("lease_id") if isinstance(lease, dict) else None
    safe_lease = lease_id if is_safe_name(lease_id) else None
    correlation = safe_lease or dispatch_id
    if entries[-1].entry_type == "completion_recorded" and mailbox.completion_published(
        f"runner-message.completion.{correlation}.1"
    ):
        # The dispatch finished and said so; only its processed marker went missing (a
        # crash after publishing, or a deleted marker). Nothing was interrupted.
        mailbox.mark_processed(dispatch_id)
        print(f"already completed {dispatch_id}", file=sys.stderr)
        return True
    requested: list[str] = []
    for entry in entries:
        if entry.entry_type == "lease_accepted":
            kinds = entry.details.get("requested_kinds")
            requested = [str(kind) for kind in kinds] if isinstance(kinds, list) else []
    interrupted: dict[str, Any] | None = None
    with contextlib.suppress(OAKError):
        interrupted = journal.incomplete_operation()
        if not journal.requires_manual_recovery():
            journal.append(
                "manual_recovery_required",
                now,
                {
                    "reason": "the dispatch was interrupted before it published a completion",
                    **(interrupted or {}),
                },
            )
    with contextlib.suppress(OSError, ValueError, OAKError):
        head = journal.head()
        mailbox.publish_message(
            identity,
            kind="completion",
            tenant_id=str(envelope.get("tenant_id", "local")),
            environment=str(envelope.get("environment", "development")),
            correlation_id=correlation,
            # Sequence 2: a recovery report never takes the id of a completion an
            # earlier run may already have published for this lease.
            sequence=2,
            lease_id=safe_lease,
            operation_id=None,
            occurred_at=now,
            payload={
                "outcome": "manual_recovery_required",
                "requested_kinds": requested,
                "applied_kinds": [],
                "failed_kind": str(interrupted["kind"]) if interrupted else None,
                "journal_digest": head[1],
                "journal_sequence": head[0],
                "detail": "an earlier run was interrupted; inspect the journal and the "
                "named resources before any further dispatch",
                "evidence": [],
            },
        )
    mailbox.mark_processed(dispatch_id)
    print(f"interrupted {dispatch_id}: manual recovery required", file=sys.stderr)
    return True


def _publish_denial(
    mailbox: RunnerMailbox,
    identity: RunnerIdentity,
    envelope: dict[str, Any],
    denial: OAKError,
    now: str,
    correlation: str,
    lease_id: str | None,
) -> None:
    """Publish a signed denial; it names the lease when the envelope's is a safe name.

    The lease ties the denial to a dispatch the control plane issued, so `oak ingest`
    records it instead of reporting it as rejected (F4-8); the lease id is still only a
    claim of the unverified envelope, and the control plane checks it against its own.
    """

    with contextlib.suppress(OSError, ValueError):
        mailbox.publish_message(
            identity,
            kind="completion",
            tenant_id=str(envelope.get("tenant_id", "local")),
            environment=str(envelope.get("environment", "development")),
            correlation_id=correlation or "correlation-denied",
            sequence=1,
            lease_id=lease_id,
            operation_id=None,
            occurred_at=now,
            payload={
                "outcome": "denied",
                "applied_kinds": [],
                "denial_code": denial.code,
                "detail": str(denial),
            },
        )


def identity() -> int:
    """Print this runner's public identity, for the control plane to enroll."""

    home = _environment_path("OAK_RUNNER_HOME", str(Path.home() / ".oak" / "runner"))
    runner_id = os.getenv("OAK_RUNNER_ID", "runner.local-fixture-runner")
    try:
        runner = RunnerIdentity.load_or_create(home, runner_id)
    except OSError as error:
        raise OAKError("OAK-RUNNER-CONFIG", "the runner home is unreadable") from error
    print(json.dumps(runner.public_identity(), indent=2, sort_keys=True))
    return 0


def status() -> int:
    home = _environment_path("OAK_RUNNER_HOME", str(Path.home() / ".oak" / "runner"))
    journals = sorted((home / "journals").glob("*.jsonl")) if (home / "journals").is_dir() else []
    signed_heads = _SignedHeads.from_environment(home)
    report: dict[str, Any] = {"journals": []}
    for path in journals:
        journal = RunnerJournal(path)
        # A corrupt or truncated journal is precisely the condition `status` exists to
        # report, and it used to be the condition that killed it: `verify_chain` caught
        # only OAKError, so a malformed line raised JSONDecodeError (a ValueError), and
        # `entries()` below was outside any guard at all. An operator inspecting a
        # damaged runner got a traceback instead of the word "tampered".
        try:
            journal.verify_chain()
            chain = "verified"
        except OAKError:
            chain = "tampered"
        except (ValueError, OSError):
            chain = "unreadable"
        try:
            entries = len(journal.entries())
            # An open operation with no after-entry is an interrupted side effect even
            # before any run has written the explicit manual-recovery entry for it.
            manual_recovery = (
                journal.requires_manual_recovery() or journal.incomplete_operation() is not None
            )
        except (OAKError, ValueError, OSError):
            entries = 0
            manual_recovery = True
            chain = "unreadable"
        signed_head = "unchecked"
        if chain != "verified":
            # Still tie the journal to its completions, so they are not listed as missing.
            signed_heads.compare(path.stem, journal)
        else:
            # Any prefix of a valid journal verifies, so a journal whose last entries were
            # removed reads as intact. The head this runner signed into its newest
            # completion for the dispatch says how far the journal reached (RR-054).
            signed_head = signed_heads.compare(path.stem, journal)
            if signed_head == "missing_from_journal":
                chain = "truncated"
                manual_recovery = True
        report["journals"].append(
            {
                "dispatch": path.stem,
                "entries": entries,
                "chain": chain,
                "signed_head": signed_head,
                "manual_recovery_required": manual_recovery,
            }
        )
    # A journal that was deleted outright has no file to report; the completion this runner
    # signed for it still names the lease, and its recovery state is unknown.
    report["missing_journals"] = signed_heads.missing()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


class _SignedHeads:
    """The journal heads this runner signed into the completions still in its mailbox.

    A journal is tied to its completions by its dispatch, by the lease its own
    `lease_accepted` entry names and by the lease in the delivered envelope, so editing the
    envelope does not hide a cut journal. A completion tied to no journal is a journal that
    is gone, and `missing` lists it.
    """

    def __init__(self, completions: list[dict[str, Any]] | None) -> None:
        self._completions = completions
        self._claimed: set[str] = set()
        self._mailbox: RunnerMailbox | None = None

    @classmethod
    def from_environment(cls, home: Path) -> _SignedHeads:
        # `status` only reads: no mailbox configured, or no key yet, means nothing to
        # compare with, never a key created as a side effect.
        mailbox_root = os.getenv("OAK_RUNNER_MAILBOX")
        if not mailbox_root or not (home / "runner.key").is_file():
            return cls(None)
        try:
            runner = RunnerIdentity.load_or_create(home, os.getenv("OAK_RUNNER_ID", "runner"))
        except (OAKError, OSError):
            return cls(None)
        mailbox = RunnerMailbox(Path(mailbox_root).absolute(), home)
        signed = [
            message
            for message in mailbox.completions(None)
            if _signed_head_of(message, runner.public_key_base64)
        ]
        heads = cls(signed)
        heads._mailbox = mailbox
        return heads

    def compare(self, dispatch_id: str, journal: RunnerJournal) -> str:
        """`matched`, `missing_from_journal`, `none` (nothing signed to compare), or
        `unchecked` (no mailbox or key, or a journal that cannot be read)."""

        if self._completions is None or self._mailbox is None:
            return "unchecked"
        correlations = {dispatch_id}
        lease_id = self._mailbox.dispatch_lease_id(dispatch_id)
        if lease_id is not None:
            correlations.add(lease_id)
        try:
            entries = journal.entries()
        except (OAKError, OSError, ValueError):
            entries = ()
        for entry in entries:
            if entry.entry_type == "lease_accepted" and is_safe_name(entry.details.get("lease_id")):
                correlations.add(str(entry.details["lease_id"]))
        mine = [
            message for message in self._completions if message["correlation_id"] in correlations
        ]
        self._claimed.update(str(message["id"]) for message in mine)
        if not mine:
            return "none"
        newest = max(mine, key=lambda message: int(message["sequence"]))
        digest = str(newest["payload"]["journal_digest"])
        sequence = newest["payload"].get("journal_sequence")
        try:
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                reached = journal.contains_head(sequence, digest)
            else:
                # A completion from before the sequence was signed names only the digest.
                reached = any(entry.digest == digest for entry in journal.entries())
        except OAKError:
            return "unchecked"
        return "matched" if reached else "missing_from_journal"

    def missing(self) -> list[dict[str, Any]]:
        """Completions this runner signed whose journal no journal file is tied to."""

        if self._completions is None:
            return []
        return [
            {"completion": str(message["id"]), "lease": str(message["correlation_id"])}
            for message in sorted(self._completions, key=lambda message: str(message["id"]))
            if str(message["id"]) not in self._claimed
        ]


def _signed_head_of(message: dict[str, Any], public_key: str) -> bool:
    """Whether a completion is this runner's own, signed, and names a journal head."""

    signature = message.get("signature")
    payload = message.get("payload")
    return (
        isinstance(signature, dict)
        and signature.get("public_key_base64") == public_key
        and verify_signed_document(message)
        and isinstance(payload, dict)
        and isinstance(payload.get("journal_digest"), str)
        and isinstance(message.get("sequence"), int)
        and isinstance(message.get("correlation_id"), str)
        and isinstance(message.get("id"), str)
    )


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
    subcommands.add_parser(
        "identity", help="print this runner's public identity for `oak keys enroll-runner`"
    )
    arguments = parser.parse_args()
    try:
        if arguments.command == "run-once":
            return run_once(cancellation_requested=bool(arguments.cancel))
        if arguments.command == "identity":
            return identity()
        return status()
    except OAKError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
