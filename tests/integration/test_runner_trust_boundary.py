# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005: the runner trust boundary, both directions, as the 1.0 review found it.

The control plane believed any runner message signed by the key the message itself carried
(F4-1), acknowledged messages before recording them (F4-7), could not record a denial
(F4-8), recorded a dispatch it then failed to deliver (F4-9) and re-signed whatever notices
the mailbox held (F4-2). The runner compared role-scoped key ids for separation of duties
(F4-3), let a second run take a live journal for an interrupted one (F4-5), wedged on a
dispatch name it could not book-keep (F4-6) and built a message path from an unverified
lease id (F4-11). Each test here pins the corrected shape.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from oak.adapters.dispatch import FilesystemMailbox
from oak.adapters.signing import initialize_trust_directory
from oak.domain import OAKError
from oak.runner.identity import RunnerIdentity
from oak.runner.journal import RunnerJournal
from oak.runner.mailbox import RunnerMailbox
from oak.runner.main import run_once
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    derive_key_id,
    verified_revocations,
)
from tests.runner_support import ROOT, build_compiled_case, enroll_test_runner, read_dispatch

pytestmark = pytest.mark.integration

READ_ONLY = ("inventory", "validate", "render", "plan", "verify")


def _dispatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str = "local-fixture.yaml"
):
    # The runner judges plan expiry and leases on the wall clock, so these run on it too.
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    harness = build_compiled_case(tmp_path, target_name=target, now=now)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(READ_ONLY, harness.context("dispatch-readonly-1", "0.1.9"))
    monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(harness.mailbox_root))
    monkeypatch.setenv("OAK_RUNNER_HOME", str(tmp_path / "runner"))
    monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(harness.trust_directory))
    monkeypatch.setenv("OAK_RUNNER_TARGET_PROFILE", str(ROOT / "examples/targets" / target))
    return harness


def _status(harness) -> str:
    return str(harness.release._repository.current_case()["status"])


def _messages(harness) -> list[Path]:
    directory = harness.mailbox_root / "messages"
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def _publish(home: Path, harness, lease_id: str, *, sequence: int = 1, **payload) -> dict:
    identity = RunnerIdentity.load_or_create(home, "runner.local-fixture-runner")
    return RunnerMailbox(harness.mailbox_root, home).publish_message(
        identity,
        kind="completion",
        tenant_id="local",
        environment="development",
        correlation_id=lease_id,
        sequence=sequence,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=harness.now,
        payload={
            "outcome": "succeeded",
            "requested_kinds": list(READ_ONLY),
            "applied_kinds": [],
            "failed_kind": None,
            "journal_digest": "sha256:" + "0" * 64,
            "detail": "",
            "evidence": [],
            **payload,
        },
    )


# ----- control plane: what ingest believes --------------------------------------------------


def test_ingest_refuses_until_a_runner_is_enrolled(tmp_path, monkeypatch) -> None:
    harness = _dispatched(tmp_path, monkeypatch)
    with pytest.raises(OAKError) as refused:
        harness.release.ingest_runner_messages(harness.context("ingest-00000001", None))
    assert refused.value.code == "OAK-INGEST-RUNNER-UNENROLLED"


def test_a_completion_signed_by_any_other_key_is_rejected_and_believes_nothing(
    tmp_path, monkeypatch
) -> None:
    """F4-1: a fresh key with a predictable lease id used to move a case to deployed."""

    harness = _dispatched(tmp_path, monkeypatch)
    enroll_test_runner(harness.trust_directory, tmp_path / "runner")
    envelope, _attachments = read_dispatch(harness.mailbox_root)
    lease_id = envelope["lease"]["lease_id"]
    forged = _publish(tmp_path / "forger", harness, lease_id, applied_kinds=["apply"])
    before = _status(harness)

    result = harness.release.ingest_runner_messages(harness.context("ingest-00000001", None))

    assert result.rejected == (forged["id"],) and result.accepted == ()
    assert _status(harness) == before
    assert [path.stem for path in _messages(harness)] == [forged["id"]], "left, not acknowledged"


def test_the_enrolled_runner_cannot_report_a_kind_its_envelope_never_requested(
    tmp_path, monkeypatch
) -> None:
    """F4-1: a completion is bound to its envelope's requested kinds."""

    harness = _dispatched(tmp_path, monkeypatch)
    enroll_test_runner(harness.trust_directory, tmp_path / "runner")
    envelope, _attachments = read_dispatch(harness.mailbox_root)
    widened = _publish(
        tmp_path / "runner", harness, envelope["lease"]["lease_id"], applied_kinds=["apply"]
    )

    result = harness.release.ingest_runner_messages(harness.context("ingest-00000001", None))

    assert result.rejected == (widened["id"],)


def test_a_denial_is_recorded_and_a_failed_recording_is_never_acknowledged(
    tmp_path, monkeypatch
) -> None:
    """F4-8 and F4-7: a denial names its lease and is recorded; one message that cannot
    be recorded stays in the mailbox while the next is still recorded."""

    harness = _dispatched(tmp_path, monkeypatch)
    enroll_test_runner(harness.trust_directory, tmp_path / "runner")
    envelope, _attachments = read_dispatch(harness.mailbox_root)
    plan = harness.mailbox_root / "dispatches" / envelope["id"] / "plan.json"
    document = json.loads(plan.read_text(encoding="utf-8"))
    document["status"] = "signed"
    plan.write_text(json.dumps(document), encoding="utf-8")
    assert run_once() == 0
    [denial_path] = _messages(harness)
    denial = json.loads(denial_path.read_text(encoding="utf-8"))
    assert denial["lease_id"] == envelope["lease"]["lease_id"]
    assert denial["payload"]["outcome"] == "denied"
    before = _status(harness)

    first = harness.release.ingest_runner_messages(harness.context("ingest-00000001", None))
    assert [message["id"] for message in first.accepted] == [denial["id"]]
    assert _status(harness) == before and _messages(harness) == []

    # The same id again with other content cannot be recorded (an immutable artifact);
    # it is reported and left, and the message after it is still recorded.
    clash = _publish(tmp_path / "runner", harness, envelope["lease"]["lease_id"], outcome="denied")
    assert clash["id"] == denial["id"]
    later = _publish(tmp_path / "runner", harness, envelope["lease"]["lease_id"], sequence=3)
    second = harness.release.ingest_runner_messages(harness.context("ingest-00000002", None))
    assert second.rejected == (clash["id"],)
    assert [message["id"] for message in second.accepted] == [later["id"]]
    assert [path.stem for path in _messages(harness)] == [clash["id"]]


def test_a_dispatch_id_the_mailbox_already_holds_is_refused_before_the_case_records_it(
    tmp_path, monkeypatch
) -> None:
    """F4-9: a refused delivery used to leave the lease on the case."""

    harness = _dispatched(tmp_path, monkeypatch)
    repository = harness.release._repository
    case = repository.current_case()
    sequence = len(repository.manifest()["audit_events"]) + 1
    suffix = str(case["id"]).removeprefix("design-case.")
    (harness.mailbox_root / "dispatches" / f"dispatch.{suffix}.{sequence}").mkdir()

    with pytest.raises(OAKError) as refused:
        harness.release.dispatch(
            ("inventory",), harness.context("dispatch-again-0001", case["version"])
        )

    assert refused.value.code == "OAK-DISPATCH-EXISTS"
    assert repository.current_case()["version"] == case["version"]


def test_the_control_plane_never_delivers_a_name_the_runner_cannot_take_up(tmp_path) -> None:
    with pytest.raises(OAKError) as refused:
        FilesystemMailbox(tmp_path / "mailbox").check_unused("dispatch.manual..qa.11")
    assert refused.value.code == "OAK-DISPATCH-NAME"


def test_a_deleted_notice_stays_in_the_next_signed_manifest(tmp_path, monkeypatch) -> None:
    """F4-2: the next revocation used to sign the mailbox as it stood, minus the notice."""

    harness = build_compiled_case(tmp_path, target_name="local-mutation-fixture.yaml")
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("rollback", harness.context("approve-rollback-01", "0.1.9"))
    harness.release.dispatch(READ_ONLY, harness.context("dispatch-readonly-1", "0.1.10"))
    harness.release.revoke_approval(
        "dry_run", "drill: withdrawn", harness.context("revoke-dryrun-00001", "0.1.11")
    )
    revocations = harness.mailbox_root / "revocations"
    [dry_run_notice] = [path for path in revocations.glob("*.json") if path.name != "manifest.json"]
    listed = json.loads((revocations / "manifest.json").read_text(encoding="utf-8"))["revoked"]
    dry_run_notice.unlink()

    harness.release.revoke_approval(
        "rollback",
        "an unrelated later revocation",
        harness.context("revoke-rollback-001", "0.1.12"),
    )

    manifest = json.loads((revocations / "manifest.json").read_text(encoding="utf-8"))
    assert set(map(json.dumps, listed)) <= set(map(json.dumps, manifest["revoked"]))
    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    manifest_document, notices = mailbox.revocation_documents()
    with pytest.raises(RunnerDenialError) as denied:
        verified_revocations(
            manifest_document,
            notices,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            minimum_sequence=-1,
        )
    assert denied.value.code == "OAK-RUNNER-REVOCATION"


# ----- runner: separation, one run at a time, safe names -----------------------------------


def test_one_key_pinned_as_signer_and_approver_is_refused(tmp_path) -> None:
    """F4-3: role-scoped key ids differ for one key, so the material is compared."""

    trust = tmp_path / "trust"
    initialize_trust_directory(trust)
    signer = json.loads((trust / "plan-signer.identity.json").read_text(encoding="utf-8"))
    approver = {
        **signer,
        "role": "approver",
        "key_id": derive_key_id("approver", signer["public_key_base64"]),
    }
    (trust / "approver.identity.json").write_text(json.dumps(approver), encoding="utf-8")

    with pytest.raises(RunnerDenialError) as refused:
        TrustAnchors.from_directory(trust)
    assert refused.value.code == "OAK-RUNNER-SEPARATION"


def test_a_second_run_on_the_same_home_is_refused(tmp_path, monkeypatch) -> None:
    """F4-5: one run per runner home."""

    _dispatched(tmp_path, monkeypatch)
    home = tmp_path / "runner"
    home.mkdir(mode=0o700)
    held = os.open(home / "run.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OAKError) as refused:
            run_once()
        assert refused.value.code == "OAK-RUNNER-BUSY"
    finally:
        os.close(held)
    assert run_once() == 0


def test_a_finished_dispatch_missing_its_marker_is_only_marked_again(
    tmp_path, monkeypatch, capsys
) -> None:
    """F4-5: a lost `.processed` marker is not an interrupted install."""

    harness = _dispatched(tmp_path, monkeypatch)
    assert run_once() == 0
    envelope, _attachments = read_dispatch(harness.mailbox_root)
    journal = RunnerJournal(tmp_path / "runner" / "journals" / f"{envelope['id']}.jsonl")
    entries = journal.entries()
    (harness.mailbox_root / "dispatches" / envelope["id"] / ".processed").unlink()

    assert run_once() == 0

    assert journal.entries() == entries
    assert not journal.requires_manual_recovery()
    assert "already completed" in capsys.readouterr().err


def test_an_unsafe_dispatch_name_is_skipped_and_the_next_dispatch_still_runs(
    tmp_path, monkeypatch, capsys
) -> None:
    """F4-6: one name the runner cannot book-keep used to stop every later dispatch."""

    harness = _dispatched(tmp_path, monkeypatch)
    planted = harness.mailbox_root / "dispatches" / "a..b"
    planted.mkdir()
    (planted / "envelope.json").write_text("{}", encoding="utf-8")

    assert run_once() == 0

    output = capsys.readouterr()
    assert "skipped 'a..b'" in output.err and "completed dispatch." in output.out
    assert not (planted / ".processed").exists()


def test_a_denial_never_writes_outside_the_mailbox(tmp_path, monkeypatch) -> None:
    """F4-11: an unverified lease id named the denial's file."""

    harness = _dispatched(tmp_path, monkeypatch)
    shutil.rmtree(harness.mailbox_root / "dispatches")
    planted = harness.mailbox_root / "dispatches" / "dz"
    planted.mkdir(parents=True)
    (harness.mailbox_root / "messages" / "runner-message.completion.x").mkdir(parents=True)
    (planted / "envelope.json").write_text(
        json.dumps({"protocol_version": "0.0.0", "lease": {"lease_id": "x/../../../outside"}}),
        encoding="utf-8",
    )

    assert run_once() == 0

    assert not list(harness.mailbox_root.parent.glob("outside*"))
    assert [path.name for path in _messages(harness)] == ["runner-message.completion.dz.1.json"]
