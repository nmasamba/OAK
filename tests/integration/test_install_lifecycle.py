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
