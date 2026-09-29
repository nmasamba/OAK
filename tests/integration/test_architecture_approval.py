# SPDX-License-Identifier: Apache-2.0
"""OAK-S11-002: nothing is installed until the architecture and the install are approved.

The owner's condition of 2026-09-29, checked three times: `approve apply` refuses
without a current architecture approval, dispatch refuses to issue an install without
one, and the runner independently denies an install envelope that lacks one or carries
one that approves a different decision or installation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oak.contracts import load_yaml_document
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.runner_adapters import plan_installation_digest
from oak.runner.verification import RunnerDenialError, TrustAnchors, verify_dispatch
from tests.runner_support import (
    ROOT,
    approve_actions,
    build_compiled_case,
    read_dispatch,
    resign,
    with_time,
)

pytestmark = pytest.mark.integration

MUTATION_TARGET = "local-mutation-fixture.yaml"


def _target() -> dict:
    return load_yaml_document(
        (ROOT / "examples/targets" / MUTATION_TARGET).read_text(encoding="utf-8")
    )


def _signed(tmp_path: Path):
    harness = build_compiled_case(tmp_path, target_name=MUTATION_TARGET)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    return harness


def _verify(harness, envelope, attachments):
    return verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=_target(),
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )


def test_apply_cannot_be_approved_before_the_architecture(tmp_path: Path) -> None:
    harness = _signed(tmp_path)

    with pytest.raises(OAKError) as caught:
        harness.release.approve("apply", harness.context("approve-apply-000001", "0.1.8"))

    assert caught.value.code == "OAK-APPROVAL-ARCHITECTURE"
    case = harness.release._repository.current_case()
    assert case["status"] == "bundle_compiled"
    assert "apply" not in case["extensions"].get("oak.community/approval_refs", {})


def test_the_architecture_approval_names_the_decision_and_the_installation(
    tmp_path: Path,
) -> None:
    harness = _signed(tmp_path)

    result = harness.release.approve(
        "architecture", harness.context("approve-architecture-01", "0.1.8")
    )

    approval = result.document
    assert approval["action"] == "architecture"
    binding = approval["extensions"]["oak.community/architecture"]
    decision_ref = result.case["extensions"]["oak.community/selection_decision_ref"]
    assert binding["decision_ref"]["digest"] == decision_ref["digest"]
    assert binding["candidate_ref"]["id"] == "candidate-03"
    plan = harness.release._repository.read_json_artifact(
        _reference(result.case["runner_plan_ref"])
    )
    assert binding["installation_digest"] == plan_installation_digest(plan)
    assert binding["installation_digest"] is not None
    # Approving the architecture is not approving the install.
    assert result.case["status"] == "bundle_compiled"

    applied = harness.release.approve("apply", harness.context("approve-apply-000001", "0.1.9"))
    assert applied.case["status"] == "deployment_approved"


def test_a_revoked_architecture_approval_blocks_the_install_dispatch(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, ("architecture", "apply"), first_version=8)
    harness.release.revoke_approval(
        "architecture",
        "The owner withdrew the architecture.",
        harness.context("revoke-architecture-1", version),
    )

    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", "0.1.11"))

    assert caught.value.code == "OAK-DISPATCH-APPROVAL"
    assert not (harness.mailbox_root / "dispatches").exists()


def test_an_install_dispatch_carries_both_approvals_and_verifies(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, ("architecture", "apply"), first_version=8)
    harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)

    assert {"approval-architecture", "approval-apply"} <= set(attachments)
    verified = _verify(harness, envelope, attachments)
    assert verified.requested_kinds == ("apply",)


def test_the_runner_denies_an_install_without_the_architecture_approval(
    tmp_path: Path,
) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, ("architecture", "apply"), first_version=8)
    harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)

    # An authentically signed envelope that simply omits the architecture approval.
    envelope["approval_refs"] = [
        reference
        for reference in envelope["approval_refs"]
        if not str(reference["id"]).startswith("approval.architecture.")
    ]
    attachments.pop("approval-architecture")
    envelope = resign(envelope, harness.trust_directory, "plan-signer")

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments)
    assert caught.value.code == "OAK-RUNNER-APPROVAL"
    assert "architecture" in str(caught.value)


def test_the_runner_denies_an_architecture_approval_for_a_different_installation(
    tmp_path: Path,
) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, ("architecture", "apply"), first_version=8)
    harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)

    # Signed by the real approver key, bound to the real plan and bundle digests, but
    # approving a different installation than the plan carries.
    approval = dict(attachments["approval-architecture"])
    binding = dict(approval["extensions"]["oak.community/architecture"])
    binding["installation_digest"] = "sha256:" + "0" * 64
    approval["extensions"] = {"oak.community/architecture": binding}
    approval = resign(approval, harness.trust_directory, "approver")
    attachments["approval-architecture"] = approval
    references = []
    for reference in envelope["approval_refs"]:
        if str(reference["id"]).startswith("approval.architecture."):
            reference = {**reference, "digest": content_digest(canonical_json_bytes(approval))}
        references.append(reference)
    envelope["approval_refs"] = references
    envelope = resign(envelope, harness.trust_directory, "plan-signer")

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments)
    assert caught.value.code == "OAK-RUNNER-APPROVAL"
    assert "different decision or installation" in str(caught.value)


def test_removal_never_needs_the_architecture_approval(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, ("rollback",), first_version=8)
    harness.release.dispatch(("rollback",), harness.context("dispatch-rollbk-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)

    assert "approval-architecture" not in attachments
    assert _verify(harness, envelope, attachments).requested_kinds == ("rollback",)


def _reference(document: dict):
    from oak.domain import ArtifactReference

    return ArtifactReference.from_document(document)
