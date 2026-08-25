# SPDX-License-Identifier: Apache-2.0
"""OAK-PL-004: the revocation channel is signed, inventoried, and fails closed (RR-001).

The channel originally failed open four ways — a missing directory, an unreadable or
oversized file, and a malformed document all read as "nothing revoked" — and the notices
were unsigned, so deleting a file restored a revoked approval. The first fix signed the
notices and refused malformed state; the closing audit then showed that deleting one
*valid* notice from an otherwise healthy directory still restored its approval, because
nothing inventoried the set. The signed revocation manifest closes that: the notice set
must match the manifest exactly, and the manifest's sequence may never regress below the
runner's recorded high-water mark. Every test here asserts a refusal shape of that design.
"""

import copy
import json
import shutil
from pathlib import Path

import pytest

from oak.domain import OAKError, canonical_json_bytes
from oak.runner.mailbox import RunnerMailbox
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    verified_revocations,
    verify_dispatch,
)
from tests.runner_support import build_compiled_case, read_dispatch, with_time

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def revoked_dispatch(tmp_path_factory):
    """A signed, approved, dispatched case whose dry-run approval is then revoked."""

    tmp_path = tmp_path_factory.mktemp("revocation")
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory", "validate", "render", "plan", "verify"),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    harness.release.revoke_approval(
        "dry_run", "drill: approval withdrawn", harness.context("revoke-dryrun-00001", "0.1.10")
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    return {
        "harness": harness,
        "mailbox_root": harness.mailbox_root,
        "trust_directory": harness.trust_directory,
        "registry": harness.registry,
        "now": harness.now,
        "envelope": envelope,
        "attachments": attachments,
    }


def _mailbox(state, tmp_path: Path) -> RunnerMailbox:
    return RunnerMailbox(state["mailbox_root"], tmp_path / "runner-home")


def _anchors(state) -> TrustAnchors:
    return TrustAnchors.from_directory(state["trust_directory"])


def _verified(state, tmp_path: Path, *, minimum_sequence: int = -1):
    manifest, notices = _mailbox(state, tmp_path).revocation_documents()
    return verified_revocations(
        manifest,
        notices,
        registry=state["registry"],
        anchors=_anchors(state),
        minimum_sequence=minimum_sequence,
    )


def _target(state):
    from oak.contracts import load_yaml_document
    from tests.runner_support import ROOT

    return load_yaml_document(
        (ROOT / "examples/targets/local-fixture.yaml").read_text(encoding="utf-8")
    )


def _fresh_revoked_mailbox(tmp_path: Path):
    """An independent harness (module fixture must stay pristine for other tests)."""

    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(("inventory",), harness.context("dispatch-readonly-1", "0.1.9"))
    harness.release.revoke_approval(
        "dry_run", "drill: approval withdrawn", harness.context("revoke-dryrun-00001", "0.1.10")
    )
    return harness


def test_a_signed_revocation_denies_the_matching_dispatch(revoked_dispatch, tmp_path) -> None:
    """The full producer-to-runner path: revoke, read, verify set and notices, deny."""

    revocations = _verified(revoked_dispatch, tmp_path)
    assert revocations.approval_ids == {revoked_dispatch["envelope"]["approval_refs"][0]["id"]}
    assert revocations.sequence >= 1

    with pytest.raises(RunnerDenialError) as caught:
        verify_dispatch(
            envelope=copy.deepcopy(revoked_dispatch["envelope"]),
            attachments=copy.deepcopy(revoked_dispatch["attachments"]),
            registry=revoked_dispatch["registry"],
            anchors=_anchors(revoked_dispatch),
            target_document=_target(revoked_dispatch),
            revoked_approval_ids=revocations.approval_ids,
            seen_lease_nonces=frozenset(),
            now=with_time(revoked_dispatch["now"], 60),
        )
    assert caught.value.code == "OAK-RUNNER-APPROVAL"


def test_a_dispatched_mailbox_carries_an_empty_signed_manifest(tmp_path) -> None:
    """dispatch() establishes the manifest, so 'no manifest' becomes tampering."""

    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(("inventory",), harness.context("dispatch-readonly-1", "0.1.9"))

    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    manifest, notices = mailbox.revocation_documents()
    assert manifest is not None and manifest["sequence"] == 0 and manifest["revoked"] == []
    assert notices == ()
    revocations = verified_revocations(
        manifest,
        notices,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        minimum_sequence=-1,
    )
    assert revocations.approval_ids == frozenset()


def test_deleting_a_single_valid_notice_denies_instead_of_restoring(tmp_path) -> None:
    """The audit's finding, as a regression: one deleted notice is a set mismatch."""

    harness = _fresh_revoked_mailbox(tmp_path)
    notices = [
        path
        for path in (harness.mailbox_root / "revocations").glob("*.json")
        if path.name != "manifest.json"
    ]
    assert len(notices) == 1
    notices[0].unlink()

    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    manifest, remaining = mailbox.revocation_documents()
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            remaining,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            minimum_sequence=-1,
        )
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_deleting_the_manifest_denies_every_dispatch(tmp_path) -> None:
    harness = _fresh_revoked_mailbox(tmp_path)
    (harness.mailbox_root / "revocations" / "manifest.json").unlink()

    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    manifest, notices = mailbox.revocation_documents()
    assert manifest is None
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            notices,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            minimum_sequence=-1,
        )
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_rolled_back_manifest_sequence_is_refused(tmp_path) -> None:
    """A validly signed but older set is refused once the runner has seen newer."""

    harness = _fresh_revoked_mailbox(tmp_path)
    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    manifest, notices = mailbox.revocation_documents()
    assert manifest is not None

    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            notices,
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            minimum_sequence=int(manifest["sequence"]) + 1,
        )
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_the_runner_records_and_reloads_the_sequence_high_water_mark(tmp_path) -> None:
    mailbox = RunnerMailbox(tmp_path / "mailbox", tmp_path / "runner-home")
    assert mailbox.last_revocation_sequence() == -1
    mailbox.record_revocation_sequence(4)
    assert mailbox.last_revocation_sequence() == 4

    (tmp_path / "runner-home" / "revocation-sequence.json").write_text("nonsense")
    with pytest.raises(OAKError) as caught:
        mailbox.last_revocation_sequence()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_an_unsigned_legacy_notice_fails_closed(revoked_dispatch, tmp_path) -> None:
    """The pre-fix notice shape is refused, not honoured on its say-so."""

    manifest, _ = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    legacy = {
        "id": "revocation.approval.dry-run.forged",
        "approval_id": "approval.dry-run.forged",
        "approval_digest": "sha256:" + "a" * 64,
        "action": "dry_run",
        "revoked_at": revoked_dispatch["now"],
        "reason": "unsigned",
    }
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            (legacy,),
            registry=revoked_dispatch["registry"],
            anchors=_anchors(revoked_dispatch),
            minimum_sequence=-1,
        )
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_tampered_notice_is_a_set_mismatch(revoked_dispatch, tmp_path) -> None:
    """Editing a notice changes its canonical digest, so the manifest refuses it."""

    manifest, notices = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    tampered = copy.deepcopy(notices[0])
    tampered["reason"] = "some other reason entirely"
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            (tampered,),
            registry=revoked_dispatch["registry"],
            anchors=_anchors(revoked_dispatch),
            minimum_sequence=-1,
        )
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_manifest_signed_by_an_unpinned_key_is_refused(revoked_dispatch, tmp_path) -> None:
    manifest, notices = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    empty = TrustAnchors(keys_by_role={"plan-signer": {}, "approver": {}})
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocations(
            manifest,
            notices,
            registry=revoked_dispatch["registry"],
            anchors=empty,
            minimum_sequence=-1,
        )
    assert caught.value.code == "OAK-RUNNER-TRUST"


def test_deleting_the_revocations_directory_does_not_restore_an_approval(tmp_path) -> None:
    """The original RR-001 attack, as a regression: absence is denial, not emptiness."""

    harness = _fresh_revoked_mailbox(tmp_path)
    shutil.rmtree(harness.mailbox_root / "revocations")

    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_garbage_notice_fails_closed(tmp_path) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / "garbage.json").write_text("not json", encoding="utf-8")
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_an_oversized_notice_fails_closed(tmp_path) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / "huge.json").write_text(
        "{" + " " * 1_048_576 + "}", encoding="utf-8"
    )
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_an_unexpected_entry_fails_closed_but_hidden_files_are_ignored(tmp_path) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / ".DS_Store").write_bytes(b"\x00")
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    assert mailbox.revocation_documents() == (None, ())

    (scratch_root / "revocations" / "notes.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_corrupt_nonce_ledger_fails_closed_and_is_not_erased(tmp_path) -> None:
    """The audit's second high finding, as a regression.

    A corrupt ledger used to read as empty, and the next consume rewrote the file from
    that empty read — permanently erasing every previously burned nonce. Now both the
    read and the consume refuse, and the corrupt bytes stay on disk for the operator.
    """

    home = tmp_path / "runner-home"
    home.mkdir(parents=True)
    ledger = home / "consumed-nonces.json"
    ledger.write_text("{corrupt", encoding="utf-8")
    mailbox = RunnerMailbox(tmp_path / "mailbox", home)

    with pytest.raises(OAKError) as read_error:
        mailbox.consumed_lease_nonces()
    assert read_error.value.code == "OAK-RUNNER-REPLAY"

    with pytest.raises(OAKError) as consume_error:
        mailbox.consume_lease_nonce("a" * 64)
    assert consume_error.value.code == "OAK-RUNNER-REPLAY"
    assert ledger.read_text(encoding="utf-8") == "{corrupt"


def test_the_nonce_ledger_round_trips_and_replaces_atomically(tmp_path) -> None:
    home = tmp_path / "runner-home"
    mailbox = RunnerMailbox(tmp_path / "mailbox", home)
    mailbox.consume_lease_nonce("a" * 64)
    mailbox.consume_lease_nonce("b" * 64)
    assert mailbox.consumed_lease_nonces() == {"a" * 64, "b" * 64}
    ledger = home / "consumed-nonces.json"
    assert json.loads(ledger.read_text(encoding="utf-8")) == sorted(["a" * 64, "b" * 64])
    assert not ledger.with_name(ledger.name + ".tmp").exists()


def test_the_manifest_binds_notice_bytes_not_just_ids(revoked_dispatch, tmp_path) -> None:
    """A digest in the manifest covers the whole canonical notice, signature included."""

    manifest, notices = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    assert manifest is not None
    from oak.domain import content_digest

    listed = {entry["id"]: entry["digest"] for entry in manifest["revoked"]}
    for notice in notices:
        assert listed[notice["id"]] == content_digest(canonical_json_bytes(notice))
