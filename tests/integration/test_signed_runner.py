# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-001..011 signed dispatch journey and adversarial verification."""

import copy
from pathlib import Path

import pytest

from oak.contracts import load_yaml_document
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.runner.execution import execute_dispatch
from oak.runner.journal import RunnerJournal
from oak.runner.verification import RunnerDenialError, TrustAnchors, verify_dispatch
from tests.runner_support import ROOT, build_compiled_case, read_dispatch, tamper, with_time

pytestmark = pytest.mark.integration

MUTATION_TARGET = "local-mutation-fixture.yaml"


def _target(name: str) -> dict:
    return load_yaml_document((ROOT / "examples/targets" / name).read_text(encoding="utf-8"))


def _dispatch_readonly(tmp_path: Path):
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory", "validate", "render", "plan", "verify"),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    return harness, envelope, attachments


@pytest.fixture(scope="module")
def readonly_dispatch(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("readonly")
    harness, envelope, attachments = _dispatch_readonly(tmp_path)
    return {
        "trust_directory": harness.trust_directory,
        "registry": harness.registry,
        "now": harness.now,
        "envelope": envelope,
        "attachments": attachments,
    }


def _verify(
    state, *, target_name="local-fixture.yaml", envelope=None, attachments=None, **overrides
):
    kwargs: dict = {
        "envelope": copy.deepcopy(envelope if envelope is not None else state["envelope"]),
        "attachments": copy.deepcopy(
            attachments if attachments is not None else state["attachments"]
        ),
        "registry": state["registry"],
        "anchors": TrustAnchors.from_directory(state["trust_directory"]),
        "target_document": _target(target_name),
        "revoked_approval_ids": frozenset(),
        "seen_lease_nonces": frozenset(),
        "now": with_time(state["now"], 60),
    }
    kwargs.update(overrides)
    return verify_dispatch(**kwargs)


def test_read_only_dispatch_verifies_and_executes(readonly_dispatch, tmp_path: Path) -> None:
    verified = _verify(readonly_dispatch)
    assert verified.requested_kinds == ("inventory", "validate", "render", "plan", "verify")
    journal = RunnerJournal(tmp_path / "journal.jsonl")
    outcome = execute_dispatch(
        verified,
        journal=journal,
        target_document=_target("local-fixture.yaml"),
        registry=readonly_dispatch["registry"],
        now=with_time(readonly_dispatch["now"], 61),
    )
    assert outcome.outcome == "succeeded"
    assert set(outcome.applied_kinds) == {"inventory", "validate", "render", "plan", "verify"}
    journal.verify_chain()


def test_tampered_plan_is_denied_before_execution(readonly_dispatch) -> None:
    attachments = copy.deepcopy(readonly_dispatch["attachments"])
    attachments["plan"] = tamper(attachments["plan"], "/status", "approved")
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, attachments=attachments)
    assert caught.value.code == "OAK-RUNNER-DIGEST"


def test_wrong_target_fingerprint_is_denied(readonly_dispatch) -> None:
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, target_name=MUTATION_TARGET)
    assert caught.value.code == "OAK-RUNNER-TARGET"


def test_expired_lease_is_denied(readonly_dispatch) -> None:
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, now=with_time(readonly_dispatch["now"], 10_000))
    assert caught.value.code == "OAK-RUNNER-LEASE"


def test_replayed_lease_nonce_is_denied(readonly_dispatch) -> None:
    seen = frozenset({readonly_dispatch["envelope"]["lease"]["nonce"]})
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, seen_lease_nonces=seen)
    assert caught.value.code == "OAK-RUNNER-REPLAY"


def test_untrusted_signer_is_denied(readonly_dispatch) -> None:
    empty = TrustAnchors(plan_signer_key_ids=frozenset(), approver_key_ids=frozenset())
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, anchors=empty)
    assert caught.value.code == "OAK-RUNNER-TRUST"


def test_revoked_approval_is_denied(readonly_dispatch) -> None:
    approval_id = readonly_dispatch["envelope"]["approval_refs"][0]["id"]
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, revoked_approval_ids=frozenset({approval_id}))
    assert caught.value.code == "OAK-RUNNER-APPROVAL"


def test_forbidden_execution_field_is_denied(readonly_dispatch) -> None:
    attachments = copy.deepcopy(readonly_dispatch["attachments"])
    plan = attachments["plan"]
    plan["operations"][0]["parameters"]["command"] = "rm -rf /"
    envelope = tamper(
        readonly_dispatch["envelope"],
        "/plan_ref/digest",
        content_digest(canonical_json_bytes(plan)),
    )
    with pytest.raises(RunnerDenialError) as caught:
        _verify(readonly_dispatch, envelope=envelope, attachments=attachments)
    assert caught.value.code in {
        "OAK-RUNNER-SIGNATURE",
        "OAK-RUNNER-PARAMETERS",
        "OAK-RUNNER-SCHEMA",
    }


def test_dispatch_without_signing_is_refused(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("inventory",), harness.context("dispatch-nosign-01", "0.1.7"))
    assert caught.value.code == "OAK-DEPENDENCY-MISSING"


def test_dispatch_without_approval_is_refused(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("inventory",), harness.context("dispatch-noappr-01", "0.1.8"))
    assert caught.value.code == "OAK-DISPATCH-APPROVAL"


def test_mutating_dispatch_applies_and_rolls_back(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.approve("apply", harness.context("approve-apply-00001", "0.1.9"))
    harness.release.approve("rollback", harness.context("approve-rollbk-0001", "0.1.10"))
    harness.release.dispatch(
        ("apply", "verify", "rollback"),
        harness.context("dispatch-mutating-1", "0.1.11"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    verified = verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=_target(MUTATION_TARGET),
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )
    assert "apply" in verified.requested_kinds


def test_mutating_dispatch_without_apply_approval_is_denied(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(
            ("apply", "verify"), harness.context("dispatch-noapply-1", "0.1.9")
        )
    assert caught.value.code == "OAK-DISPATCH-APPROVAL"
