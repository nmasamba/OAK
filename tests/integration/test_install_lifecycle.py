# SPDX-License-Identifier: Apache-2.0
"""OAK-S11-004/005: the journey reaches `deployed` and `observing`, truthfully.

Dispatch → the real `oak-runner run-once` path (with a scripted daemon) → `ingest`
moves the case to `deployed` and records the completion; `observe` writes the record
and moves it to `observing`; a rollback in a later dispatch is classified as such and
the next record says the installation was removed. Every refusal along the way stops
before a side effect with a stable code.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from oak.domain import OAKError
from oak.runner.adapters import ContainerFixtureAdapter
from tests.container_support import FakeClock, FakeDocker
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

TARGET = ROOT / "examples/targets/local-started-fixture.yaml"
PAUSE = (
    "rancher/mirrored-pause@sha256:ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a"
)


def _now() -> str:
    # The runner judges leases on the wall clock, so this journey runs on it too.
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Journey:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.harness = build_compiled_case(tmp_path, target_name=str(TARGET), now=_now())
        self.docker = FakeDocker(repo_digests=[PAUSE])
        self.counter = 0
        monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(self.harness.mailbox_root))
        monkeypatch.setenv("OAK_RUNNER_HOME", str(tmp_path / "runner"))
        monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(self.harness.trust_directory))
        monkeypatch.setenv("OAK_RUNNER_TARGET_PROFILE", str(TARGET))

    @property
    def case(self) -> dict:
        return self.harness.release._repository.current_case()

    def context(self, label: str):
        self.counter += 1
        return self.harness.context(
            f"{label}-{self.counter:04d}-journey", str(self.case["version"])
        )

    def derived_context(self):
        """A command with no idempotency key: the service derives one, as the CLI does."""

        from dataclasses import replace

        return replace(self.context("derived"), idempotency_key="")

    def approve(self, action: str):
        return self.harness.release.approve(action, self.context(f"approve-{action}"))

    def dispatch(self, *kinds: str):
        return self.harness.release.dispatch(kinds, self.context("dispatch"))

    def run_runner(self) -> None:
        from oak.runner.main import run_once

        clock = FakeClock()
        run_once(adapter=ContainerFixtureAdapter(self.docker, clock=clock, sleeper=clock.sleep))

    def ingest(self):
        return self.harness.release.ingest_runner_messages(self.context("ingest"))

    def observe(self):
        return self.harness.release.record_observation(self.context("observe"))

    def events(self) -> list[str]:
        from oak.domain import ArtifactReference

        repository = self.harness.release._repository
        return [
            str(repository.read_json_artifact(ArtifactReference.from_document(entry))["event_type"])
            for entry in repository.manifest()["audit_events"]
        ]


@pytest.fixture
def journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Journey:
    journey = Journey(tmp_path, monkeypatch)
    journey.harness.release.sign_plan(journey.context("sign"))
    return journey


def test_the_journey_reaches_deployed_then_observing_and_records_what_it_saw(
    journey: Journey,
) -> None:
    journey.approve("architecture")
    journey.approve("apply")
    assert journey.case["status"] == "deployment_approved"

    journey.dispatch("apply")
    journey.run_runner()
    ingested = journey.ingest()

    assert [message["payload"]["outcome"] for message in ingested.accepted] == ["succeeded"]
    case = journey.case
    assert case["status"] == "deployed"
    assert len(case["extensions"]["oak.community/runner_result_refs"]) == 1
    assert journey.events()[-1] == "runner_completed"
    assert len(journey.docker.containers) == 2

    observed = journey.observe()
    record = observed.document
    assert observed.case["status"] == "observing"
    assert journey.events()[-1] == "observation_recorded"
    assert record["installation_state"] == "present"
    measures = {item["id"]: item for item in record["deployment_measures"]}
    assert (measures["EV-DEP-01"]["result"], measures["EV-DEP-01"]["sample_size"]) == ("pass", 1)
    assert measures["EV-DEP-03"]["result"] == "unknown"
    calibrated = {row["name"]: row for row in record["calibration"]}
    # The reference candidate predicts all four calibrated measures; none was observed.
    assert set(calibrated) >= {"monthly_cost", "latency_p95", "quality", "energy"}
    assert calibrated["latency_p95"]["predicted"]["lower"] is not None
    assert record["assurance"]["status"] == "not_satisfied"
    assert len(record["assurance"]["missing"]) == 4
    assert record["proposals"] == []
    # The record changed nothing else: no approval, no dispatch, no promotion.
    assert set(observed.case["extensions"]) - set(case["extensions"]) == {
        "oak.community/observation_refs"
    }


def test_observe_is_refused_before_an_install_and_repeated_only_on_new_evidence(
    journey: Journey,
) -> None:
    with pytest.raises(OAKError) as early:
        journey.observe()
    assert early.value.code == "OAK-OBSERVE-STATE"

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")
    journey.run_runner()
    journey.ingest()
    journey.observe()

    with pytest.raises(OAKError) as again:
        journey.observe()
    assert again.value.code == "OAK-OBSERVE-DUPLICATE"


def test_an_installed_case_accepts_only_removal_approvals_and_a_later_rollback_is_seen(
    journey: Journey,
) -> None:
    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")
    journey.run_runner()
    journey.ingest()
    journey.observe()

    for action in ("apply", "dry_run", "architecture"):
        with pytest.raises(OAKError) as refused:
            journey.approve(action)
        assert refused.value.code == "OAK-APPROVAL-STATE"

    journey.approve("rollback")
    journey.dispatch("rollback")
    journey.run_runner()
    journey.ingest()
    assert journey.events()[-1] == "runner_rolled_back"
    assert journey.docker.containers == {}

    record = journey.observe().document
    assert record["installation_state"] == "removed"
    measures = {item["id"]: item for item in record["deployment_measures"]}
    assert measures["EV-DEP-03"]["result"] == "pass"
    assert len(record["source_message_refs"]) == 2


def test_a_re_apply_over_the_installation_is_measured_as_idempotent(journey: Journey) -> None:
    journey.approve("architecture")
    journey.approve("apply")
    for _ in range(2):
        journey.dispatch("apply")
        journey.run_runner()
        journey.ingest()

    record = journey.observe().document
    reapply = next(item for item in record["deployment_measures"] if item["id"] == "EV-DEP-02")
    assert (reapply["result"], reapply["sample_size"]) == ("pass", 1)
    creates = [argv for argv in journey.docker.calls if argv[1] == "create"]
    assert len(creates) == 2, "the second apply must adopt, not create again"


def test_a_failed_install_leaves_the_case_approved_and_its_evidence_recorded(
    journey: Journey,
) -> None:
    journey.docker.start_status = "exited"
    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")
    journey.run_runner()
    ingested = journey.ingest()

    payload = ingested.accepted[0]["payload"]
    assert payload["outcome"] == "failed" and payload["failed_kind"] == "apply"
    assert journey.case["status"] == "deployment_approved"
    assert journey.docker.containers == {}
    with pytest.raises(OAKError) as refused:
        journey.observe()
    assert refused.value.code == "OAK-OBSERVE-STATE"
    assert json.dumps(payload).count("rollback_result") == 1


# -- audit regressions (Sprint 11 closing audit) ---------------------------------------


def test_an_earlier_dispatchs_completion_is_still_accepted_after_a_later_dispatch(
    journey: Journey,
) -> None:
    """S12/S17: a completion is this control plane's work whichever dispatch it answers."""

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")
    journey.dispatch("apply")
    journey.run_runner()
    ingested = journey.ingest()

    assert len(ingested.accepted) == 2 and ingested.rejected == ()
    record = journey.observe().document
    measures = {item["id"]: item for item in record["deployment_measures"]}
    assert measures["EV-DEP-01"]["sample_size"] == 1
    assert measures["EV-DEP-02"]["result"] == "pass"


def test_apply_then_destroy_in_one_dispatch_is_never_deployed(journey: Journey) -> None:
    """S13: a completion that installed and removed leaves nothing installed."""

    for action in ("architecture", "apply", "destroy"):
        journey.approve(action)
    journey.dispatch("apply", "destroy")
    journey.run_runner()
    journey.ingest()

    assert journey.case["status"] == "deployment_approved"
    assert journey.events()[-1] == "runner_rolled_back"
    assert journey.docker.containers == {}


def test_a_renewed_approval_after_revocation_works_and_can_be_revoked_again(
    journey: Journey,
) -> None:
    """S9/S10/S11/S21/S24: each issuance has its own identity and its own revocation."""

    journey.approve("architecture")
    first = journey.approve("apply").document
    journey.harness.release.revoke_approval(
        "apply", "Withdrawn for review.", journey.derived_context()
    )
    renewed = journey.approve("apply").document
    assert renewed["id"] != first["id"]

    journey.dispatch("apply")
    journey.run_runner()
    accepted = journey.ingest().accepted
    assert accepted[0]["payload"]["outcome"] == "succeeded", accepted[0]["payload"]

    # Revoking the renewal with the default key revokes the renewal, and the signed
    # revocation set stays valid: a later dispatch is verified, not refused wholesale.
    journey.approve("rollback")
    journey.harness.release.revoke_approval("apply", "Withdrawn again.", journey.derived_context())
    from oak.domain import ArtifactReference

    approval_refs = journey.case["extensions"]["oak.community/approval_refs"]
    assert approval_refs["apply"]["id"] == renewed["id"]
    current = journey.harness.release._repository.read_json_artifact(
        ArtifactReference.from_document(approval_refs["apply"])
    )
    assert current["revoked"] is True, "the second revocation must revoke the renewal"
    with pytest.raises(OAKError) as refused:
        journey.dispatch("apply")
    assert refused.value.code == "OAK-DISPATCH-APPROVAL"
    journey.dispatch("rollback")
    journey.run_runner()
    payload = journey.ingest().accepted[-1]["payload"]
    assert payload["outcome"] == "succeeded", payload
    assert journey.docker.containers == {}


def test_an_explicit_idempotency_key_still_retries_after_a_commit(journey: Journey) -> None:
    """S14: a retry with the caller's own key returns the committed result."""

    version = str(journey.case["version"])
    context = journey.harness.context("explicit-architecture-key", version)
    first = journey.harness.release.approve("architecture", context)
    retry_context = journey.harness.context(
        "explicit-architecture-key", str(journey.case["version"])
    )
    retried = journey.harness.release.approve("architecture", retry_context)

    assert retried.duplicate is True
    assert retried.case["version"] == first.case["version"]


def test_a_crash_mid_install_is_reported_as_manual_recovery_not_a_replay(
    journey: Journey, tmp_path: Path
) -> None:
    """S2: an interrupted dispatch is recorded as such, never re-run or called denied."""

    from oak.runner.main import run_once

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")

    class Crash(BaseException):
        pass

    def crashing(argv: tuple[str, ...], timeout_seconds: int):
        if argv[1] == "start":
            raise Crash
        return journey.docker(argv, timeout_seconds)

    clock = FakeClock()
    with pytest.raises(Crash):
        run_once(adapter=ContainerFixtureAdapter(crashing, clock=clock, sleeper=clock.sleep))
    assert len(journey.docker.containers) == 2, "the crash left what it had created"

    journey.run_runner()
    payload = journey.ingest().accepted[0]["payload"]

    assert payload["outcome"] == "manual_recovery_required"
    assert payload["requested_kinds"] == ["apply"] and payload["failed_kind"] == "apply"
    assert journey.events()[-1] == "runner_recovery_required"
    assert journey.case["status"] == "deployment_approved"


def test_status_reports_an_open_operation_as_needing_recovery(
    journey: Journey, capsys: pytest.CaptureFixture[str]
) -> None:
    from oak.runner.main import run_once, status

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")

    def crashing(argv: tuple[str, ...], timeout_seconds: int):
        if argv[1] == "create":
            raise KeyboardInterrupt
        return journey.docker(argv, timeout_seconds)

    with pytest.raises(KeyboardInterrupt):
        run_once(adapter=ContainerFixtureAdapter(crashing))
    capsys.readouterr()
    status()
    report = json.loads(capsys.readouterr().out)

    assert report["journals"][0]["manual_recovery_required"] is True
