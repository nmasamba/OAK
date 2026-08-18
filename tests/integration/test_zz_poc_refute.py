# SPDX-License-Identifier: Apache-2.0
"""Temporary PoC for adversarial refutation - delete after use."""

import copy
from pathlib import Path

import pytest

from oak.contracts import load_yaml_document
from oak.runner.verification import TrustAnchors, verify_dispatch
from tests.runner_support import ROOT, build_compiled_case, read_dispatch, with_time

pytestmark = pytest.mark.integration


def _target(name: str) -> dict:
    return load_yaml_document((ROOT / "examples/targets" / name).read_text(encoding="utf-8"))


def test_poc_dotless_approval_ref_id(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(
        ("inventory",),
        harness.context("dispatch-readonly-1", "0.1.9"),
    )
    envelope, attachments = read_dispatch(harness.mailbox_root)
    print("ORIGINAL approval_refs:", envelope["approval_refs"])
    poisoned = copy.deepcopy(envelope)
    poisoned["approval_refs"][0]["id"] = "approvalpending"
    try:
        verify_dispatch(
            envelope=poisoned,
            attachments=copy.deepcopy(attachments),
            registry=harness.registry,
            anchors=TrustAnchors.from_directory(harness.trust_directory),
            target_document=_target("local-fixture.yaml"),
            revoked_approval_ids=frozenset(),
            seen_lease_nonces=frozenset(),
            now=with_time(harness.now, 60),
        )
    except BaseException as exc:  # noqa: BLE001
        print("RAISED:", type(exc).__name__, exc)
        raise SystemExit(0) from None
    print("NO EXCEPTION")
