# SPDX-License-Identifier: Apache-2.0
"""OAK-S11-002/003: compile, verify and execute the install of a selected topology.

Compilation turns the selected candidate's nodes into one `apply` operation carrying
one container per node, from the images the target profile acknowledges. The runner
re-derives every name and image from its own profile before any adapter exists, even
when every document it holds is authentically signed; execution then installs through
the adapter, compensates exactly what a failed install created, and keeps the evidence.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.contracts import load_yaml_document
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.runner_adapters import (
    ISOLATION_NEVER_STARTED,
    ISOLATION_STARTED_HARDENED,
    container_name_for,
)
from oak.runner.adapters import ContainerFixtureAdapter
from oak.runner.execution import execute_dispatch
from oak.runner.journal import RunnerJournal
from oak.runner.verification import RunnerDenialError, TrustAnchors, verify_dispatch
from tests.container_support import FakeClock, FakeDocker
from tests.runner_support import (
    ROOT,
    approve_actions,
    build_compiled_case,
    read_dispatch,
    resign,
    with_time,
)

pytestmark = pytest.mark.integration

STARTED_TARGET = "local-started-fixture.yaml"
NEVER_STARTED_TARGET = "local-mutation-fixture.yaml"
PAUSE_DIGEST = "sha256:ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a"


def _profile(name: str) -> dict[str, Any]:
    return load_yaml_document((ROOT / "examples/targets" / name).read_text(encoding="utf-8"))


def _variant(tmp_path: Path, name: str, edit: Any) -> str:
    document = _profile(name)
    edit(document)
    path = tmp_path / f"variant-{name}"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return str(path)


def _install_dispatch(tmp_path: Path, target: str = STARTED_TARGET):
    harness = build_compiled_case(tmp_path, target_name=target)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    version = approve_actions(harness, ("architecture", "apply"), first_version=8)
    harness.release.dispatch(("apply",), harness.context("dispatch-apply-00001", version))
    envelope, attachments = read_dispatch(harness.mailbox_root)
    return harness, envelope, attachments


def _verify(harness, envelope, attachments, target: dict[str, Any]):
    return verify_dispatch(
        envelope=envelope,
        attachments=attachments,
        registry=harness.registry,
        anchors=TrustAnchors.from_directory(harness.trust_directory),
        target_document=target,
        revoked_approval_ids=frozenset(),
        seen_lease_nonces=frozenset(),
        now=with_time(harness.now, 60),
    )


def _reauthor(harness, envelope, attachments, edit_parameters: Any):
    """Edit the plan's apply parameters and re-sign every document that binds the plan.

    The result is what a compromised or buggy control plane with real keys would send:
    every signature and digest verifies, so only the runner's own re-derivation from its
    target profile can refuse it.
    """

    plan = copy.deepcopy(attachments["plan"])
    operation = next(item for item in plan["operations"] if item["kind"] == "apply")
    edit_parameters(operation["parameters"])
    plan_digest = content_digest(canonical_json_bytes(plan))
    attachments = dict(attachments)
    attachments["plan"] = plan
    signature = dict(attachments["plan-signature"])
    signature["plan_ref"] = {**signature["plan_ref"], "digest": plan_digest}
    attachments["plan-signature"] = resign(signature, harness.trust_directory, "plan-signer")
    envelope = dict(envelope)
    envelope["plan_ref"] = {**envelope["plan_ref"], "digest": plan_digest}
    envelope["plan_signature_ref"] = {
        **envelope["plan_signature_ref"],
        "digest": content_digest(canonical_json_bytes(attachments["plan-signature"])),
    }
    references = []
    for reference in envelope["approval_refs"]:
        name = "approval-" + str(reference["id"]).split(".")[1]
        approval = dict(attachments[name])
        approval["plan_digest"] = plan_digest
        if name == "approval-architecture":
            binding = dict(approval["extensions"]["oak.community/architecture"])
            binding["installation_digest"] = content_digest(
                canonical_json_bytes(operation["parameters"])
            )
            approval["extensions"] = {"oak.community/architecture": binding}
        attachments[name] = resign(approval, harness.trust_directory, "approver")
        references.append(
            {**reference, "digest": content_digest(canonical_json_bytes(attachments[name]))}
        )
    envelope["approval_refs"] = references
    return resign(envelope, harness.trust_directory, "plan-signer"), attachments


def _as_case(parameters: dict[str, Any], case_id: str) -> None:
    parameters["case_id"] = case_id
    for entry in parameters["containers"]:
        entry["container_name"] = container_name_for(
            case_id, parameters["target_id"], entry["node_id"]
        )


# -- compile ---------------------------------------------------------------------------


def test_the_plan_installs_one_container_per_node_from_acknowledged_images(
    tmp_path: Path,
) -> None:
    _harness, _envelope, attachments = _install_dispatch(tmp_path)

    plan = attachments["plan"]
    apply = next(item for item in plan["operations"] if item["kind"] == "apply")
    parameters = apply["parameters"]
    assert parameters["isolation"] == ISOLATION_STARTED_HARDENED
    assert [entry["node_id"] for entry in parameters["containers"]] == [
        "node.retrieval",
        "node.generation",
    ]
    case_id = parameters["case_id"]
    for entry in parameters["containers"]:
        assert entry["container_name"] == container_name_for(
            case_id, "target.local-started-fixture", entry["node_id"]
        )
        assert entry["image_reference"] == "rancher/mirrored-pause"
        assert entry["image_digest"] == PAUSE_DIGEST
    assert "execute" in apply["permissions"]["verbs"]
    assert {"aggregate_metric", "rollback_result"} <= set(
        plan["evidence_policy"]["allowed_categories"]
    )
    preflight = {
        item["id"]: item
        for item in attachments["bundle"]["extensions"]["oak.community/preflight_results"]
    }
    assert preflight["preflight.installation"]["result"] == "pass"


def test_a_never_started_profile_compiles_a_never_started_install(tmp_path: Path) -> None:
    _harness, _envelope, attachments = _install_dispatch(tmp_path, NEVER_STARTED_TARGET)

    apply = next(item for item in attachments["plan"]["operations"] if item["kind"] == "apply")
    assert apply["parameters"]["isolation"] == ISOLATION_NEVER_STARTED
    assert "execute" not in apply["permissions"]["verbs"]


def test_an_unmapped_component_fails_preflight_with_no_fallback(tmp_path: Path) -> None:
    def drop_local_model(document: dict[str, Any]) -> None:
        document["execution"]["component_images"] = [
            entry
            for entry in document["execution"]["component_images"]
            if entry["manifest_id"] != "component.fixture-local-model"
        ]

    variant = _variant(tmp_path, STARTED_TARGET, drop_local_model)
    with pytest.raises(OAKError) as caught:
        build_compiled_case(tmp_path, target_name=variant)
    assert caught.value.code == "OAK-TARGET-INCOMPATIBLE"
    assert "preflight.installation" in caught.value.message


def test_the_superseded_single_image_pair_is_refused_not_ignored(tmp_path: Path) -> None:
    def add_old_pair(document: dict[str, Any]) -> None:
        document["execution"]["container_image_reference"] = "postgres:17.6-alpine"
        document["execution"]["container_image_digest"] = "sha256:" + "e" * 64

    variant = _variant(tmp_path, NEVER_STARTED_TARGET, add_old_pair)
    with pytest.raises(OAKError) as caught:
        build_compiled_case(tmp_path, target_name=variant)
    assert caught.value.code == "OAK-TARGET-EXECUTION"
    assert "component_images" in caught.value.message


def test_a_component_listed_twice_is_refused(tmp_path: Path) -> None:
    def duplicate(document: dict[str, Any]) -> None:
        images = document["execution"]["component_images"]
        images.append(dict(images[0]))

    variant = _variant(tmp_path, NEVER_STARTED_TARGET, duplicate)
    with pytest.raises(OAKError) as caught:
        build_compiled_case(tmp_path, target_name=variant)
    assert caught.value.code == "OAK-TARGET-EXECUTION"


# -- runner verification ---------------------------------------------------------------


def test_the_install_verifies_against_the_runners_own_profile(tmp_path: Path) -> None:
    harness, envelope, attachments = _install_dispatch(tmp_path)

    verified = _verify(harness, envelope, attachments, _profile(STARTED_TARGET))

    assert verified.requested_kinds == ("apply",)


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (
            lambda parameters: parameters["containers"][0].update(
                container_name="oak-fixture-retrieval-000000000000"
            ),
            "OAK-RUNNER-PARAMETERS",
        ),
        (
            lambda parameters: parameters.update(case_id="design-case.someone-else"),
            "OAK-RUNNER-PARAMETERS",
        ),
        (
            lambda parameters: parameters["containers"][0].update(
                image_digest="sha256:" + "d" * 64
            ),
            "OAK-RUNNER-IMAGE",
        ),
        (
            lambda parameters: parameters["containers"][1].update(
                manifest_id="component.fixture-unknown"
            ),
            "OAK-RUNNER-IMAGE",
        ),
        (
            lambda parameters: parameters.update(isolation=ISOLATION_NEVER_STARTED),
            "OAK-RUNNER-TARGET-CAPABILITY",
        ),
        # Another case's installation with consistently derived names: only the binding
        # of the parameters to the envelope's case can refuse it.
        (
            lambda parameters: _as_case(parameters, "design-case.someone-else"),
            "OAK-RUNNER-PARAMETERS",
        ),
    ],
)
def test_an_authentically_signed_but_wrong_install_is_denied(
    tmp_path: Path, edit: Any, code: str
) -> None:
    harness, envelope, attachments = _install_dispatch(tmp_path)
    envelope, attachments = _reauthor(harness, envelope, attachments, edit)

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments, _profile(STARTED_TARGET))
    assert caught.value.code == code


def test_a_start_the_runners_profile_does_not_acknowledge_is_denied(tmp_path: Path) -> None:
    """The runner's own profile, not the plan, decides whether anything may start."""

    harness, envelope, attachments = _install_dispatch(tmp_path)
    runner_profile = _profile(STARTED_TARGET)
    runner_profile["execution"]["mutation_acknowledgement"] = "isolated-non-production-fixture-only"

    with pytest.raises(RunnerDenialError) as caught:
        _verify(harness, envelope, attachments, runner_profile)
    # The fingerprint binding refuses first; either way nothing is started.
    assert caught.value.code in {"OAK-RUNNER-TARGET", "OAK-RUNNER-TARGET-CAPABILITY"}


# -- execution -------------------------------------------------------------------------


def _execute(harness, envelope, attachments, docker: FakeDocker, tmp_path: Path):
    verified = _verify(harness, envelope, attachments, _profile(STARTED_TARGET))
    clock = FakeClock()
    journal = RunnerJournal(tmp_path / "journal.jsonl")
    # The harness runs on a fixed clock; the lease deadline is judged on the same one.
    moment = datetime.fromisoformat(with_time(harness.now, 60).replace("Z", "+00:00"))
    outcome = execute_dispatch(
        verified,
        journal=journal,
        target_document=_profile(STARTED_TARGET),
        registry=harness.registry,
        now=with_time(harness.now, 60),
        adapter=ContainerFixtureAdapter(
            docker, clock=clock, sleeper=clock.sleep, wall_clock=lambda: moment
        ),
    )
    return outcome, journal


def test_an_install_reports_typed_evidence_and_journals_its_resources(tmp_path: Path) -> None:
    harness, envelope, attachments = _install_dispatch(tmp_path)
    docker = FakeDocker(repo_digests=[f"rancher/mirrored-pause@{PAUSE_DIGEST}"])

    outcome, journal = _execute(harness, envelope, attachments, docker, tmp_path)

    assert outcome.outcome == "succeeded" and outcome.applied_kinds == ("apply",)
    assert [item["category"] for item in outcome.evidence] == [
        "status",
        "test_result",
        "aggregate_metric",
    ]
    assert len(docker.containers) == 2
    before = next(entry for entry in journal.entries() if entry.entry_type == "operation_before")
    assert sorted(before.details["resources"]) == sorted(docker.containers)
    serialized = json.dumps(outcome.evidence)
    assert "Log" not in serialized and "secret" not in serialized


def test_a_failed_smoke_test_is_compensated_and_its_evidence_kept(tmp_path: Path) -> None:
    harness, envelope, attachments = _install_dispatch(tmp_path)
    docker = FakeDocker(
        repo_digests=[f"rancher/mirrored-pause@{PAUSE_DIGEST}"],
        start_status="exited",
        exit_code=1,
    )

    outcome, journal = _execute(harness, envelope, attachments, docker, tmp_path)

    assert outcome.outcome == "failed" and outcome.failed_kind == "apply"
    assert outcome.applied_kinds == ()
    assert docker.containers == {}, "compensation must remove what the install created"
    categories = [item["category"] for item in outcome.evidence]
    assert "test_result" in categories and "rollback_result" in categories
    compensation = next(item for item in outcome.evidence if item["operation"] == "compensation")
    assert compensation["content"]["removed_all"] is True
    types = [entry.entry_type for entry in journal.entries()]
    assert types.index("operation_failed") < types.index("rollback_before")
    assert "manual_recovery_required" not in types


def test_a_failed_re_apply_leaves_the_existing_installation_alone(tmp_path: Path) -> None:
    harness, envelope, attachments = _install_dispatch(tmp_path)
    apply = next(item for item in attachments["plan"]["operations"] if item["kind"] == "apply")
    docker = FakeDocker(
        repo_digests=[f"rancher/mirrored-pause@{PAUSE_DIGEST}"],
        start_status="exited",
    )
    for entry in apply["parameters"]["containers"]:
        docker.add(
            entry["container_name"],
            {
                "oak.fixture": "true",
                "oak.case": apply["parameters"]["case_id"],
                "oak.node": entry["node_id"],
            },
        )

    outcome, _journal = _execute(harness, envelope, attachments, docker, tmp_path)

    assert outcome.outcome == "failed"
    assert len(docker.containers) == 2, "an adopted container is not this failure's to remove"
    assert "rm" not in docker.verbs()
