# SPDX-License-Identifier: Apache-2.0
"""OAK-PL-004: the revocation channel is signed and fails closed (RR-001).

The channel used to fail open four ways — a missing directory, an unreadable or
oversized file, and a malformed document all read as "nothing revoked" — and the
notices themselves were unsigned, so deleting a file from the mailbox restored a
revoked approval. Every test here asserts the refusal shape of the fix.
"""

import copy
import shutil
from pathlib import Path

import pytest

from oak.domain import OAKError
from oak.runner.mailbox import RunnerMailbox
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    verified_revocation_ids,
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


def _target(state):
    from oak.contracts import load_yaml_document
    from tests.runner_support import ROOT

    return load_yaml_document(
        (ROOT / "examples/targets/local-fixture.yaml").read_text(encoding="utf-8")
    )


def test_a_signed_revocation_denies_the_matching_dispatch(revoked_dispatch, tmp_path) -> None:
    """The full producer-to-runner path: revoke, read, verify, deny."""

    documents = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    assert len(documents) == 1
    revoked = verified_revocation_ids(
        documents, registry=revoked_dispatch["registry"], anchors=_anchors(revoked_dispatch)
    )
    assert revoked == {revoked_dispatch["envelope"]["approval_refs"][0]["id"]}

    with pytest.raises(RunnerDenialError) as caught:
        verify_dispatch(
            envelope=copy.deepcopy(revoked_dispatch["envelope"]),
            attachments=copy.deepcopy(revoked_dispatch["attachments"]),
            registry=revoked_dispatch["registry"],
            anchors=_anchors(revoked_dispatch),
            target_document=_target(revoked_dispatch),
            revoked_approval_ids=revoked,
            seen_lease_nonces=frozenset(),
            now=with_time(revoked_dispatch["now"], 60),
        )
    assert caught.value.code == "OAK-RUNNER-APPROVAL"


def test_an_unsigned_legacy_notice_fails_closed(revoked_dispatch, tmp_path) -> None:
    """The pre-fix notice shape is refused, not honoured on its say-so."""

    legacy = {
        "id": "revocation.approval.dry-run.forged",
        "approval_id": "approval.dry-run.forged",
        "approval_digest": "sha256:" + "a" * 64,
        "action": "dry_run",
        "revoked_at": revoked_dispatch["now"],
        "reason": "unsigned",
    }
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocation_ids(
            (legacy,), registry=revoked_dispatch["registry"], anchors=_anchors(revoked_dispatch)
        )
    assert caught.value.code == "OAK-RUNNER-SCHEMA"


def test_a_tampered_notice_fails_signature_verification(revoked_dispatch, tmp_path) -> None:
    documents = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    tampered = copy.deepcopy(documents[0])
    tampered["reason"] = "some other reason entirely"
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocation_ids(
            (tampered,), registry=revoked_dispatch["registry"], anchors=_anchors(revoked_dispatch)
        )
    assert caught.value.code == "OAK-RUNNER-SIGNATURE"


def test_a_notice_signed_by_an_unpinned_key_is_refused(revoked_dispatch, tmp_path) -> None:
    documents = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    empty = TrustAnchors(keys_by_role={"plan-signer": {}, "approver": {}})
    with pytest.raises(RunnerDenialError) as caught:
        verified_revocation_ids(documents, registry=revoked_dispatch["registry"], anchors=empty)
    assert caught.value.code == "OAK-RUNNER-TRUST"


def test_one_bad_notice_denies_the_whole_read(revoked_dispatch, tmp_path) -> None:
    """A planted malformed file must not suppress the valid notices beside it."""

    documents = _mailbox(revoked_dispatch, tmp_path).revocation_documents()
    forged = {"approval_id": "approval.other", "anything": True}
    with pytest.raises(RunnerDenialError):
        verified_revocation_ids(
            (*documents, forged),
            registry=revoked_dispatch["registry"],
            anchors=_anchors(revoked_dispatch),
        )


def test_deleting_the_revocations_directory_does_not_restore_an_approval(
    tmp_path,
) -> None:
    """The RR-001 attack, as a regression test: absence is denial, not emptiness."""

    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory",),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    harness.release.revoke_approval(
        "dry_run", "drill: approval withdrawn", harness.context("revoke-dryrun-00001", "0.1.10")
    )
    shutil.rmtree(harness.mailbox_root / "revocations")

    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_garbage_notice_fails_closed(revoked_dispatch, tmp_path) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / "garbage.json").write_text("not json", encoding="utf-8")
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_an_oversized_notice_fails_closed(revoked_dispatch, tmp_path) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / "huge.json").write_text(
        "{" + " " * 1_048_576 + "}", encoding="utf-8"
    )
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_an_unexpected_entry_fails_closed_but_hidden_files_are_ignored(
    revoked_dispatch, tmp_path
) -> None:
    scratch_root = tmp_path / "mailbox"
    (scratch_root / "revocations").mkdir(parents=True)
    (scratch_root / "revocations" / ".DS_Store").write_bytes(b"\x00")
    mailbox = RunnerMailbox(scratch_root, tmp_path / "runner-home")
    assert mailbox.revocation_documents() == ()

    (scratch_root / "revocations" / "notes.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(OAKError) as caught:
        mailbox.revocation_documents()
    assert caught.value.code == "OAK-RUNNER-REVOCATION"


def test_a_delivered_mailbox_carries_an_empty_revocation_channel(tmp_path) -> None:
    """deliver() creates the directory, so a fresh dispatch reads cleanly."""

    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory",),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    mailbox = RunnerMailbox(harness.mailbox_root, tmp_path / "runner-home")
    assert mailbox.revocation_documents() == ()
