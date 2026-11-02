# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: a native install needs the user's signed consent to what it relaxes.

Checked three times, as the architecture approval is (ADR-0019): `approve` refuses the
consent out of order, for a plan that installs nothing natively, without the digest of the
text the user read, or after that text changed; dispatch refuses to issue a native install
without a current consent; and the runner independently denies a native install whose
envelope lacks one, carries one for another installation or another list of relaxed
controls, or whose parameters are not the ones its own profile acknowledges.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from oak.bootstrap import load_native_consent
from oak.contracts import load_yaml_document
from oak.domain import ArtifactReference, OAKError, canonical_json_bytes, content_digest
from oak.domain.runner_adapters import (
    NATIVE_ADAPTER_ID,
    NATIVE_CONSENT_BINDING_KEY,
    NATIVE_RELAXED_CONTROLS,
    native_consent_binding,
    native_consent_problem,
    native_consent_reference,
)
from oak.runner.verification import (
    RunnerDenialError,
    TrustAnchors,
    _check_native_installation,
    verify_dispatch,
)
from tests.runner_support import (
    ROOT,
    approve_actions,
    build_compiled_case,
    consent_digest,
    read_dispatch,
    resign,
    with_time,
)

pytestmark = pytest.mark.integration

NATIVE_TARGET = ROOT / "examples/targets/local-native-stand-in.yaml"
INSTALL = ("architecture", "native_consent", "apply")


def _target() -> dict[str, Any]:
    return load_yaml_document(NATIVE_TARGET.read_text(encoding="utf-8"))


def _signed(tmp_path: Path, target: str = str(NATIVE_TARGET)):
    harness = build_compiled_case(tmp_path, target_name=target)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    return harness


def _plan(harness) -> dict[str, Any]:
    case = harness.release._repository.current_case()
    return harness.release._repository.read_json_artifact(
        ArtifactReference.from_document(case["runner_plan_ref"])
    )


def _apply(plan: dict[str, Any]) -> dict[str, Any]:
    return next(operation for operation in plan["operations"] if operation["kind"] == "apply")


def _verify(harness, envelope, attachments, target: dict[str, Any] | None = None):
    return verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=target or _target(),
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )


def _dispatched(tmp_path: Path):
    harness = _signed(tmp_path)
    version = approve_actions(harness, INSTALL, first_version=8)
    harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)
    return harness, envelope, attachments


def _rebind_consent(harness, envelope, attachments, binding: dict[str, Any]):
    """An authentically signed consent whose binding says something else."""

    approval = dict(attachments["approval-native-consent"])
    approval["extensions"] = {NATIVE_CONSENT_BINDING_KEY: binding}
    approval = resign(approval, harness.trust_directory, "approver")
    attachments["approval-native-consent"] = approval
    envelope["approval_refs"] = [
        {**reference, "digest": content_digest(canonical_json_bytes(approval))}
        if str(reference["id"]).startswith("approval.native-consent.")
        else reference
        for reference in envelope["approval_refs"]
    ]
    return resign(envelope, harness.trust_directory, "plan-signer")


def test_a_native_plan_names_the_consent_text_it_was_compiled_against(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    plan = _plan(harness)
    apply = _apply(plan)

    assert apply["adapter"]["id"] == NATIVE_ADAPTER_ID
    assert apply["parameters"]["consent_ref"] == native_consent_reference(load_native_consent())
    # The example installs only OAK's stand-in, so the install may reach no host at all.
    assert apply["parameters"]["allowed_download_hosts"] == []
    assert apply["permissions"]["network_destinations"] == []
    case = harness.release._repository.current_case()
    bundle = harness.release._repository.read_json_artifact(
        ArtifactReference.from_document(case["deployment_bundle_ref"])
    )
    installation = next(
        result
        for result in bundle["extensions"]["oak.community/preflight_results"]
        if result["id"] == "preflight.installation"
    )
    assert installation["result"] == "pass"
    assert installation["evidence"]["mode"] == "native"


def test_the_consent_comes_after_the_architecture_and_before_the_install(
    tmp_path: Path,
) -> None:
    harness = _signed(tmp_path)

    with pytest.raises(OAKError) as early:
        harness.release.approve(
            "native_consent",
            harness.context("approve-consent-00001", "0.1.7"),
            consent_digest=consent_digest(),
        )
    assert early.value.code == "OAK-APPROVAL-ARCHITECTURE"
    harness.release.approve("architecture", harness.context("approve-arch-000001", "0.1.8"))
    with pytest.raises(OAKError) as unconsented:
        harness.release.approve("apply", harness.context("approve-apply-000001", "0.1.9"))
    assert unconsented.value.code == "OAK-NATIVE-CONSENT"
    for given in (None, "sha256:" + "0" * 64):
        with pytest.raises(OAKError) as unread:
            harness.release.approve(
                "native_consent",
                harness.context("approve-consent-00002", "0.1.9"),
                consent_digest=given,
            )
        assert unread.value.code == "OAK-NATIVE-CONSENT"

    result = harness.release.approve(
        "native_consent",
        harness.context("approve-consent-00003", "0.1.9"),
        consent_digest=consent_digest(),
    )

    plan = _plan(harness)
    assert result.document["action"] == "native_consent"
    binding = result.document["extensions"][NATIVE_CONSENT_BINDING_KEY]
    assert binding == native_consent_binding(plan)
    assert binding["relaxed_controls"] == list(NATIVE_RELAXED_CONTROLS)
    # The case keeps the text the user consented to, under the digest the plan names.
    recorded = [
        entry
        for entry in harness.release._repository.manifest()["artifact_index"]
        if entry["kind"] == "native_consent"
    ]
    assert [(entry["id"], entry["digest"]) for entry in recorded] == [
        ("consent.native-installation", _apply(plan)["parameters"]["consent_ref"]["digest"])
    ]
    # Consenting is not approving the install.
    assert result.case["status"] == "bundle_compiled"
    applied = harness.release.approve("apply", harness.context("approve-apply-000002", "0.1.10"))
    assert applied.case["status"] == "deployment_approved"


def test_a_container_plan_takes_no_native_consent(tmp_path: Path) -> None:
    harness = _signed(tmp_path, "local-mutation-fixture.yaml")

    with pytest.raises(OAKError) as caught:
        harness.release.approve(
            "native_consent",
            harness.context("approve-consent-00001", "0.1.8"),
            consent_digest=consent_digest(),
        )

    assert caught.value.code == "OAK-NATIVE-CONSENT"
    assert "installs nothing natively" in caught.value.message


def test_a_consent_text_that_changed_after_the_compile_is_refused(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    approve_actions(harness, ("architecture",), first_version=8)
    edited = copy.deepcopy(load_native_consent())
    edited["statement"] = edited["statement"] + " Edited after the plan was compiled."
    harness.release._native_consent = lambda: edited

    with pytest.raises(OAKError) as caught:
        harness.release.approve(
            "native_consent",
            harness.context("approve-consent-00001", "0.1.9"),
            consent_digest=native_consent_reference(edited)["digest"],
        )

    assert caught.value.code == "OAK-NATIVE-CONSENT"
    assert "compile the plan again" in caught.value.message


def test_a_consent_text_that_names_other_controls_is_refused(tmp_path: Path) -> None:
    text = load_native_consent()
    assert native_consent_problem(text) is None
    fewer = copy.deepcopy(text)
    fewer["relaxed_controls"] = fewer["relaxed_controls"][1:]
    reordered = copy.deepcopy(text)
    reordered["relaxed_controls"] = list(reversed(reordered["relaxed_controls"]))
    other = copy.deepcopy(text)
    other["id"] = "consent.another"
    for document in (fewer, reordered, other):
        assert native_consent_problem(document) is not None

    harness = _signed(tmp_path)
    approve_actions(harness, ("architecture",), first_version=8)
    harness.release._native_consent = lambda: fewer
    with pytest.raises(OAKError) as caught:
        harness.release.approve(
            "native_consent",
            harness.context("approve-consent-00001", "0.1.9"),
            consent_digest=native_consent_reference(fewer)["digest"],
        )
    assert caught.value.code == "OAK-NATIVE-CONSENT"


def test_a_revoked_consent_blocks_the_install_dispatch(tmp_path: Path) -> None:
    harness = _signed(tmp_path)
    version = approve_actions(harness, INSTALL, first_version=8)
    harness.release.revoke_approval(
        "native_consent",
        "The user withdrew the consent.",
        harness.context("revoke-consent-00001", version),
    )

    with pytest.raises(OAKError) as caught:
        harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", "0.1.12"))

    assert caught.value.code == "OAK-DISPATCH-APPROVAL"
    assert not (harness.mailbox_root / "dispatches").exists()


def test_a_native_install_dispatch_carries_three_approvals_and_verifies(
    tmp_path: Path,
) -> None:
    harness, envelope, attachments = _dispatched(tmp_path)

    assert {
        "approval-architecture",
        "approval-native-consent",
        "approval-apply",
    } <= set(attachments)
    assert _verify(harness, envelope, attachments).requested_kinds == ("apply",)


def test_the_runner_denies_a_native_install_without_its_consent(tmp_path: Path) -> None:
    harness, envelope, attachments = _dispatched(tmp_path)
    envelope["approval_refs"] = [
        reference
        for reference in envelope["approval_refs"]
        if not str(reference["id"]).startswith("approval.native-consent.")
    ]
    attachments.pop("approval-native-consent")
    envelope = resign(envelope, harness.trust_directory, "plan-signer")

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments)
    assert caught.value.code == "OAK-RUNNER-APPROVAL"
    assert "native_consent" in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("installation_digest", "sha256:" + "0" * 64),
        ("relaxed_controls", list(NATIVE_RELAXED_CONTROLS[1:])),
        (
            "consent_ref",
            {
                "id": "consent.native-installation",
                "version": "0.1.0",
                "digest": "sha256:" + "1" * 64,
            },
        ),
    ],
)
def test_the_runner_denies_a_consent_to_something_else(
    tmp_path: Path, field: str, value: Any
) -> None:
    harness, envelope, attachments = _dispatched(tmp_path)
    binding = dict(attachments["approval-native-consent"]["extensions"][NATIVE_CONSENT_BINDING_KEY])
    binding[field] = value
    envelope = _rebind_consent(harness, envelope, attachments, binding)

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments)
    assert caught.value.code == "OAK-RUNNER-APPROVAL"
    assert "another consent text, control list or installation" in str(caught.value)


def _bound(tmp_path: Path):
    harness = _signed(tmp_path)
    plan = _plan(harness)
    parameters = copy.deepcopy(_apply(plan)["parameters"])
    envelope = {"case_id": parameters["case_id"]}
    return plan, parameters, envelope


def test_the_runner_accepts_only_what_its_own_profile_acknowledges(tmp_path: Path) -> None:
    plan, parameters, envelope = _bound(tmp_path)
    target = _target()
    _check_native_installation(parameters, envelope, plan, target)

    moved = copy.deepcopy(parameters)
    moved["components"][0]["listen_port"] = 18999
    widened = copy.deepcopy(parameters)
    widened["allowed_download_hosts"] = ["example.org"]
    swapped = copy.deepcopy(parameters)
    swapped["components"][0]["artifacts"][0]["sha256"] = "sha256:" + "2" * 64
    elsewhere = copy.deepcopy(parameters)
    elsewhere["installation_id"] = "installation." + "b" * 24
    for tampered in (moved, widened, swapped, elsewhere):
        with pytest.raises(RunnerDenialError) as caught:
            _check_native_installation(tampered, envelope, plan, target)
        assert caught.value.code == "OAK-RUNNER-PARAMETERS"

    container = copy.deepcopy(target)
    container["execution"]["mutation_acknowledgement"] = "isolated-non-production-fixture-only"
    with pytest.raises(RunnerDenialError) as refused:
        _check_native_installation(parameters, envelope, plan, container)
    assert refused.value.code == "OAK-RUNNER-TARGET-CAPABILITY"


def test_the_runner_refuses_a_download_from_a_host_it_does_not_acknowledge(
    tmp_path: Path,
) -> None:
    plan, parameters, envelope = _bound(tmp_path)
    target = _target()
    downloaded = {
        "manifest_id": "component.fixture-local-model",
        "harness_kind": "llama_cpp_server",
        "artifacts": [
            {
                "role": "harness",
                "source": "https://downloads.example.net/llama.zip",
                "sha256": "sha256:" + "3" * 64,
                "size_bytes": 1000,
                "format": "zip",
            },
            {
                "role": "model",
                "source": "https://models.example.org/model.gguf",
                "sha256": "sha256:" + "4" * 64,
                "size_bytes": 2000,
                "format": "file",
            },
        ],
        "listen_port": 18432,
        "health_probe": {"path": "/health"},
    }
    target["execution"]["native_components"][1] = downloaded
    target["execution"]["allowed_download_hosts"] = ["downloads.example.net"]
    parameters["allowed_download_hosts"] = ["downloads.example.net"]
    parameters["components"][1] = {"node_id": "node.generation", **downloaded}

    with pytest.raises(RunnerDenialError) as caught:
        _check_native_installation(parameters, envelope, plan, target)
    assert caught.value.code == "OAK-RUNNER-NETWORK"

    target["execution"]["allowed_download_hosts"] = ["downloads.example.net", "models.example.org"]
    parameters["allowed_download_hosts"] = ["downloads.example.net", "models.example.org"]
    _check_native_installation(parameters, envelope, plan, target)
