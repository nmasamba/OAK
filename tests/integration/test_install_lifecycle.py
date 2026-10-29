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
from tests.runner_support import ROOT, build_compiled_case, enroll_test_runner

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
        enroll_test_runner(self.harness.trust_directory, tmp_path / "runner")
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


def _crash_mid_install(journey: Journey) -> None:
    """A dispatch whose install died after its operation began, reported on the next run."""

    from oak.runner.main import run_once

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")

    def crashing(argv: tuple[str, ...], timeout_seconds: int):
        if argv[1] == "create":
            raise KeyboardInterrupt
        return journey.docker(argv, timeout_seconds)

    with pytest.raises(KeyboardInterrupt):
        run_once(adapter=ContainerFixtureAdapter(crashing))
    journey.run_runner()


def _journal(tmp_path: Path) -> Path:
    (path,) = sorted((tmp_path / "runner" / "journals").glob("*.jsonl"))
    return path


def _full_status(capsys: pytest.CaptureFixture[str]) -> dict:
    from oak.runner.main import status

    capsys.readouterr()
    status()
    return json.loads(capsys.readouterr().out)


def _status(capsys: pytest.CaptureFixture[str]) -> dict:
    report = _full_status(capsys)
    assert report["missing_journals"] in ([], None) or report["journals"] == []
    (journal,) = report["journals"]
    return journal


def test_status_notices_a_journal_whose_tail_was_cut(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """OAK-V1-022 (RR-054): removing the recovery entries no longer reads as verified."""

    _crash_mid_install(journey)
    intact = _status(capsys)
    assert intact["chain"] == "verified" and intact["signed_head"] == "matched"
    assert intact["manual_recovery_required"] is True

    path = _journal(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["entry_type"] for line in lines] == [
        "lease_accepted",
        "operation_before",
        "manual_recovery_required",
    ]
    path.write_text(lines[0] + "\n", encoding="utf-8")

    cut = _status(capsys)
    assert cut["chain"] == "truncated"
    assert cut["signed_head"] == "missing_from_journal"
    assert cut["manual_recovery_required"] is True


def test_status_ignores_a_completion_this_runner_did_not_sign(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A planted completion naming the cut head cannot make the cut journal read as whole."""

    from oak.runner.identity import RunnerIdentity
    from oak.runner.journal import RunnerJournal
    from oak.runner.mailbox import RunnerMailbox

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    sequence, digest = RunnerJournal(path).head()
    lease_id = RunnerMailbox(journey.harness.mailbox_root, tmp_path / "runner").dispatch_lease_id(
        path.stem
    )
    assert lease_id is not None
    impostor = RunnerIdentity.load_or_create(tmp_path / "impostor", "runner.impostor")
    RunnerMailbox(journey.harness.mailbox_root, tmp_path / "impostor").publish_message(
        impostor,
        kind="completion",
        tenant_id="local",
        environment="development",
        correlation_id=lease_id,
        sequence=9,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=_now(),
        payload={"outcome": "succeeded", "journal_digest": digest, "journal_sequence": sequence},
    )

    assert _status(capsys)["chain"] == "truncated"


def test_status_ignores_a_completion_claiming_this_runner_s_key_with_a_bad_signature(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from oak.runner.identity import RunnerIdentity
    from oak.runner.journal import RunnerJournal
    from oak.runner.mailbox import RunnerMailbox

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    sequence, digest = RunnerJournal(path).head()
    home = tmp_path / "runner"
    mailbox = RunnerMailbox(journey.harness.mailbox_root, home)
    lease_id = mailbox.dispatch_lease_id(path.stem)
    assert lease_id is not None
    impostor = RunnerIdentity.load_or_create(tmp_path / "impostor", "runner.impostor")
    forged = RunnerMailbox(journey.harness.mailbox_root, tmp_path / "impostor").publish_message(
        impostor,
        kind="completion",
        tenant_id="local",
        environment="development",
        correlation_id=lease_id,
        sequence=9,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=_now(),
        payload={"outcome": "succeeded", "journal_digest": digest, "journal_sequence": sequence},
    )
    forged["signature"]["public_key_base64"] = RunnerIdentity.load_or_create(
        home, "runner.local-fixture-runner"
    ).public_key_base64
    (journey.harness.mailbox_root / "messages" / f"{forged['id']}.json").write_text(
        json.dumps(forged), encoding="utf-8"
    )

    assert _status(capsys)["chain"] == "truncated"


def test_status_without_a_mailbox_says_it_compared_nothing(
    journey: Journey,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _crash_mid_install(journey)
    monkeypatch.delenv("OAK_RUNNER_MAILBOX")

    report = _status(capsys)
    assert report["chain"] == "verified" and report["signed_head"] == "unchecked"


@pytest.mark.parametrize("damage", ["not utf-8", "unreadable"])
def test_status_reports_a_damaged_journal_beside_a_signed_completion(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str], damage: str
) -> None:
    """A journal that cannot be read is reported as such, never a traceback."""

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    if damage == "not utf-8":
        path.write_bytes(path.read_bytes() + b"\xff\xfe\n")
    else:
        path.chmod(0)
    try:
        report = _full_status(capsys)
    finally:
        path.chmod(0o600)
    (journal,) = report["journals"]
    assert journal["chain"] == "unreadable" and journal["manual_recovery_required"] is True
    assert report["missing_journals"] == []


@pytest.mark.parametrize("planted", ["deeply nested", "not a number"])
def test_status_survives_a_malformed_completion_in_the_mailbox(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str], planted: str
) -> None:
    """The mailbox is untrusted: a file anyone could drop there cannot stop `status`."""

    from oak.runner.identity import RunnerIdentity

    _crash_mid_install(journey)
    messages = journey.harness.mailbox_root / "messages"
    target = messages / "runner-message.completion.planted.1.json"
    if planted == "deeply nested":
        target.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    else:
        key = RunnerIdentity.load_or_create(
            tmp_path / "runner", "runner.local-fixture-runner"
        ).public_key_base64
        target.write_text(
            '{"kind": "completion", "id": "runner-message.completion.planted.1", '
            '"correlation_id": "lease.planted", "sequence": 1, '
            '"payload": {"journal_digest": "sha256:00", "n": NaN}, '
            f'"signature": {{"algorithm": "ed25519", "public_key_base64": "{key}", '
            '"signature_base64": "AA=="}}',
            encoding="utf-8",
        )

    journal = _status(capsys)
    assert journal["chain"] == "verified" and journal["signed_head"] == "matched"


@pytest.mark.parametrize("key", ["open to others", "unreadable", "moved aside"])
def test_status_refuses_to_compare_without_the_runner_key(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    """Hiding the key would otherwise turn a cut journal back into "verified"."""

    from oak.runner.main import status

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    runner_key = tmp_path / "runner" / "runner.key"
    if key == "open to others":
        runner_key.chmod(0o640)
    elif key == "unreadable":
        runner_key.chmod(0)
    else:
        runner_key.rename(runner_key.with_name("runner.key.aside"))
    capsys.readouterr()
    with pytest.raises(OAKError) as refused:
        status()
    assert refused.value.code == "OAK-RUNNER-KEY"
    assert capsys.readouterr().out == ""


def test_status_says_a_cut_journal_s_completion_was_signed_by_another_key(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Once the moved key is replaced, as the next `identity` or `run-once` does, the old
    completions verify under no current key; the journal says so, never "none"."""

    from oak.runner.main import identity

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    runner_key = tmp_path / "runner" / "runner.key"
    runner_key.rename(runner_key.with_name("runner.key.aside"))
    identity()

    journal = _status(capsys)
    assert journal["signed_head"] == "other_key"


def test_status_without_a_key_ignores_an_unsigned_file_in_the_mailbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a completion that verifies under the key it carries stops a keyless `status`."""

    messages = tmp_path / "mailbox" / "messages"
    messages.mkdir(parents=True)
    (messages / "runner-message.completion.planted.1.json").write_text(
        '{"kind": "completion", "id": "runner-message.completion.planted.1"}', encoding="utf-8"
    )
    monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(tmp_path / "mailbox"))
    monkeypatch.setenv("OAK_RUNNER_HOME", str(tmp_path / "home"))

    report = _full_status(capsys)

    assert report == {"journals": [], "missing_journals": []}
    assert not (tmp_path / "home" / "runner.key").exists()


def _publish_completion(journey: Journey, tmp_path: Path, sequence: int, **payload: object):
    """A completion for the dispatched lease, signed by the enrolled runner's own key."""

    from oak.runner.identity import RunnerIdentity
    from oak.runner.mailbox import RunnerMailbox

    home = tmp_path / "runner"
    mailbox = RunnerMailbox(journey.harness.mailbox_root, home)
    lease_id = mailbox.dispatch_lease_id(_journal(tmp_path).stem)
    assert lease_id is not None
    return mailbox.publish_message(
        RunnerIdentity.load_or_create(home, "runner.local-fixture-runner"),
        kind="completion",
        tenant_id="local",
        environment="development",
        correlation_id=lease_id,
        sequence=sequence,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=_now(),
        payload={
            "outcome": "manual_recovery_required",
            "requested_kinds": ["apply"],
            "applied_kinds": [],
            "failed_kind": "apply",
            "detail": "a later report",
            "evidence": [],
            **payload,
        },
    )


def test_ingest_refuses_a_completion_whose_journal_no_longer_reaches_an_accepted_one(
    journey: Journey, tmp_path: Path
) -> None:
    """OAK-V1-022 (RR-054): the control plane's record of a lease's journal never rewinds."""

    from oak.runner.journal import RunnerJournal

    _crash_mid_install(journey)
    first = journey.ingest()
    (accepted,) = first.accepted
    assert accepted["payload"]["journal_sequence"] == 3
    path = _journal(tmp_path)
    entries = RunnerJournal(path).entries()
    assert accepted["payload"]["journal_digest"] == entries[-1].digest

    shorter = _publish_completion(
        journey, tmp_path, 3, journal_sequence=1, journal_digest=entries[0].digest
    )
    other_last = _publish_completion(
        journey, tmp_path, 4, journal_sequence=3, journal_digest=entries[0].digest
    )
    unsequenced = _publish_completion(journey, tmp_path, 5, journal_digest=entries[-1].digest)
    result = journey.ingest()

    assert result.accepted == ()
    assert dict(result.refused) == {
        shorter["id"]: "OAK-INGEST-JOURNAL",
        other_last["id"]: "OAK-INGEST-JOURNAL",
        unsequenced["id"]: "OAK-INGEST-JOURNAL",
    }
    # Refused, never acknowledged: every later ingest reports them again.
    assert set(journey.ingest().rejected) == {shorter["id"], other_last["id"], unsequenced["id"]}


def test_ingest_accepts_a_completion_that_reaches_as_far_or_further(
    journey: Journey, tmp_path: Path
) -> None:
    from oak.runner.journal import RunnerJournal

    _crash_mid_install(journey)
    journey.ingest()
    sequence, digest = RunnerJournal(_journal(tmp_path)).head()

    same = _publish_completion(
        journey, tmp_path, 3, journal_sequence=sequence, journal_digest=digest
    )
    longer = _publish_completion(
        journey, tmp_path, 4, journal_sequence=sequence + 1, journal_digest="sha256:" + "a" * 64
    )
    result = journey.ingest()

    assert [message["id"] for message in result.accepted] == [same["id"], longer["id"]]
    assert result.refused == ()


def test_ingest_accepts_a_completion_from_a_runner_that_names_no_journal_length(
    journey: Journey, tmp_path: Path
) -> None:
    """A `0.9` runner's completion names only the digest; with nothing longer accepted
    before it for the lease, it ingests as it did."""

    from oak.runner.journal import RunnerJournal

    journey.approve("architecture")
    journey.approve("apply")
    journey.dispatch("apply")
    (tmp_path / "runner" / "journals").mkdir(parents=True)
    journal = RunnerJournal(tmp_path / "runner" / "journals" / "placeholder.jsonl")
    journal.append("lease_accepted", _now(), {})
    mailbox_dispatch = sorted((journey.harness.mailbox_root / "dispatches").iterdir())[0]
    (tmp_path / "runner" / "journals" / "placeholder.jsonl").rename(
        tmp_path / "runner" / "journals" / f"{mailbox_dispatch.name}.jsonl"
    )
    old = _publish_completion(journey, tmp_path, 1, journal_digest=journal.digest())
    result = journey.ingest()

    assert [message["id"] for message in result.accepted] == [old["id"]]


def test_ingest_refuses_a_completion_that_names_no_journal_head(
    journey: Journey, tmp_path: Path
) -> None:
    """FC-4: only a denial names no journal; any other completion without a head is refused."""

    _crash_mid_install(journey)
    journey.ingest()
    bare = _publish_completion(journey, tmp_path, 3)
    nulled = _publish_completion(journey, tmp_path, 4, journal_digest=None, journal_sequence=0)
    numeric = _publish_completion(journey, tmp_path, 5, journal_digest=7, journal_sequence=9)

    result = journey.ingest()

    assert result.accepted == ()
    assert dict(result.refused) == {
        bare["id"]: "OAK-INGEST-JOURNAL",
        nulled["id"]: "OAK-INGEST-JOURNAL",
        numeric["id"]: "OAK-INGEST-JOURNAL",
    }


@pytest.mark.parametrize("envelope", ["edited", "deleted"])
def test_status_notices_a_cut_journal_whose_envelope_was_changed_too(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str], envelope: str
) -> None:
    """FC-2: the journal's own lease ties it to its completions, not only the envelope."""

    _crash_mid_install(journey)
    path = _journal(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    delivered = journey.harness.mailbox_root / "dispatches" / path.stem / "envelope.json"
    if envelope == "deleted":
        delivered.unlink()
    else:
        document = json.loads(delivered.read_text(encoding="utf-8"))
        document["lease"]["lease_id"] = "lease.elsewhere"
        delivered.write_text(json.dumps(document), encoding="utf-8")

    report = _status(capsys)
    assert report["chain"] == "truncated" and report["manual_recovery_required"] is True


def test_status_lists_a_signed_completion_whose_journal_is_gone(
    journey: Journey, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """FC-3: a deleted journal leaves no file to report, but its completion names it."""

    _crash_mid_install(journey)
    intact = _full_status(capsys)
    assert intact["missing_journals"] == []

    _journal(tmp_path).unlink()

    report = _full_status(capsys)
    assert report["journals"] == []
    (missing,) = report["missing_journals"]
    assert missing["completion"].startswith("runner-message.completion.")
    assert missing["lease"].startswith("lease.")
