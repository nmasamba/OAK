# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-033 (RR-031): the runner's soak hazards, bounded and proven through run_once.

A running dispatch publishes signed heartbeats that `oak ingest` records and later
completions must reach; the consumed-nonce ledger keeps a nonce only while its lease could
still be replayed; processed dispatch directories are cleaned after a retention, never the
newest nor one whose completion is not yet ingested, and `oak-runner status` still ties
every journal to its completions afterwards.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from oak.contracts.signatures import verify_signed_document
from oak.domain import OAKError
from oak.runner.adapters import ContainerFixtureAdapter
from oak.runner.identity import RunnerIdentity
from oak.runner.mailbox import NONCE_RETENTION_SKEW_SECONDS, RunnerMailbox
from tests.container_support import FakeClock, FakeDocker
from tests.runner_support import ROOT, build_compiled_case, enroll_test_runner

pytestmark = pytest.mark.integration

TARGET = ROOT / "examples/targets/local-started-fixture.yaml"
PAUSE = (
    "rancher/mirrored-pause@sha256:ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a"
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Soak:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.harness = build_compiled_case(tmp_path, target_name=str(TARGET), now=_now())
        self.docker = FakeDocker(repo_digests=[PAUSE])
        self.home = tmp_path / "runner"
        self.counter = 0
        monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(self.harness.mailbox_root))
        monkeypatch.setenv("OAK_RUNNER_HOME", str(self.home))
        monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(self.harness.trust_directory))
        monkeypatch.setenv("OAK_RUNNER_TARGET_PROFILE", str(TARGET))
        monkeypatch.delenv("OAK_RUNNER_HEARTBEAT_SECONDS", raising=False)
        monkeypatch.delenv("OAK_RUNNER_DISPATCH_RETENTION_DAYS", raising=False)
        enroll_test_runner(self.harness.trust_directory, self.home)
        self.harness.release.sign_plan(self.context("sign"))

    @property
    def case(self) -> dict[str, Any]:
        case = self.harness.release._repository.current_case()
        assert case is not None
        return case

    def context(self, label: str) -> Any:
        self.counter += 1
        return self.harness.context(
            f"{label}-{self.counter:04d}-soak-journey", str(self.case["version"])
        )

    def approve(self, action: str) -> None:
        self.harness.release.approve(action, self.context(f"approve-{action}"))

    def dispatch(self, *kinds: str) -> dict[str, Any]:
        """Dispatch, returning the envelope the mailbox now holds."""

        return self.harness.release.dispatch(kinds, self.context("dispatch")).document

    def directory(self, envelope: dict[str, Any]) -> Path:
        return self.harness.mailbox_root / "dispatches" / str(envelope["id"])

    def run(self, interval: float | None = 0.0) -> int:
        from oak.runner.main import run_once

        clock = FakeClock()
        return run_once(
            adapter=ContainerFixtureAdapter(self.docker, clock=clock, sleeper=clock.sleep),
            heartbeat_interval_seconds=interval,
        )

    def ingest(self) -> Any:
        return self.harness.release.ingest_runner_messages(self.context("ingest"))

    def messages(self, kind: str) -> list[dict[str, Any]]:
        found = []
        for folder in ("messages", "acknowledged"):
            directory = self.harness.mailbox_root / folder
            if directory.is_dir():
                for path in sorted(directory.glob(f"runner-message.{kind}.*.json")):
                    found.append(json.loads(path.read_text(encoding="utf-8")))
        return found

    def events(self) -> list[str]:
        from oak.domain import ArtifactReference

        repository = self.harness.release._repository
        return [
            str(repository.read_json_artifact(ArtifactReference.from_document(entry))["event_type"])
            for entry in repository.manifest()["audit_events"]
        ]

    def dispatch_directories(self) -> set[Path]:
        return {
            path for path in (self.harness.mailbox_root / "dispatches").iterdir() if path.is_dir()
        }


@pytest.fixture
def soak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Soak:
    return Soak(tmp_path, monkeypatch)


def test_a_running_dispatch_publishes_signed_heartbeats_that_ingest_records(soak: Soak) -> None:
    soak.approve("architecture")
    soak.approve("apply")
    lease_id = str(soak.dispatch("apply")["lease"]["lease_id"])
    assert soak.run(interval=0.0) == 0

    heartbeats = soak.messages("heartbeat")
    assert len(heartbeats) >= 4, "accepted, before and after the operation, and between nodes"
    assert sorted(message["sequence"] for message in heartbeats) == list(
        range(1, len(heartbeats) + 1)
    )
    assert {message["lease_id"] for message in heartbeats} == {lease_id}
    assert all(verify_signed_document(message) for message in heartbeats)
    first = min(heartbeats, key=lambda message: message["sequence"])
    assert first["payload"]["stage"] == "lease_accepted"
    assert first["payload"]["journal_sequence"] == 1
    heads = [
        message["payload"]["journal_sequence"]
        for message in sorted(heartbeats, key=lambda m: m["sequence"])
    ]
    assert heads == sorted(heads), "a later heartbeat named an earlier head"

    result = soak.ingest()
    assert result.rejected == ()
    assert len(result.heartbeats) == len(heartbeats)
    assert soak.case["status"] == "deployed"
    assert soak.events().count("runner_heartbeat") == len(heartbeats)
    assert len(soak.case["extensions"]["oak.community/runner_heartbeat_refs"]) == len(heartbeats)
    # A second ingest finds nothing new and changes nothing.
    again = soak.ingest()
    assert (again.accepted, again.heartbeats) == ((), ())


def test_the_default_interval_publishes_the_acceptance_beat_only(soak: Soak) -> None:
    soak.approve("architecture")
    soak.approve("apply")
    soak.dispatch("apply")
    assert soak.run(interval=None) == 0
    assert [message["payload"]["stage"] for message in soak.messages("heartbeat")] == [
        "lease_accepted"
    ]


def test_heartbeats_can_be_switched_off_and_a_bad_interval_is_refused(
    soak: Soak, monkeypatch: pytest.MonkeyPatch
) -> None:
    soak.approve("dry_run")
    soak.dispatch("inventory")
    monkeypatch.setenv("OAK_RUNNER_HEARTBEAT_SECONDS", "0")
    assert soak.run(interval=None) == 0
    assert soak.messages("heartbeat") == []
    assert len(soak.messages("completion")) == 1
    soak.dispatch("inventory")
    monkeypatch.setenv("OAK_RUNNER_HEARTBEAT_SECONDS", "soon")
    with pytest.raises(OAKError) as refusal:
        soak.run(interval=None)
    assert refusal.value.code == "OAK-RUNNER-CONFIG"


def test_a_completion_that_falls_short_of_a_heartbeat_head_is_refused(soak: Soak) -> None:
    soak.approve("architecture")
    soak.approve("apply")
    lease_id = str(soak.dispatch("apply")["lease"]["lease_id"])
    assert soak.run(interval=0.0) == 0
    completions = sorted(
        (soak.harness.mailbox_root / "messages").glob("runner-message.completion.*.json")
    )
    assert len(completions) == 1
    genuine = json.loads(completions[0].read_text(encoding="utf-8"))
    completions[0].unlink()  # only the heartbeats reach the control plane first
    assert len(soak.ingest().heartbeats) >= 4
    floor = max(message["payload"]["journal_sequence"] for message in soak.messages("heartbeat"))

    runner = RunnerIdentity.load_or_create(soak.home, "runner.local-fixture-runner")
    mailbox = RunnerMailbox(soak.harness.mailbox_root, soak.home)
    forged = mailbox.publish_message(
        runner,
        kind="completion",
        tenant_id=str(genuine["tenant_id"]),
        environment=str(genuine["environment"]),
        correlation_id=str(genuine["correlation_id"]),
        sequence=3,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=_now(),
        payload={
            **genuine["payload"],
            "journal_sequence": floor - 1,
            "journal_digest": "sha256:" + "0" * 64,
        },
    )
    result = soak.ingest()
    assert dict(result.refused).get(forged["id"]) == "OAK-INGEST-JOURNAL"
    assert soak.case["status"] == "deployment_approved", "a cut journal moved the case"


def test_a_heartbeat_signed_by_another_key_is_rejected(soak: Soak, tmp_path: Path) -> None:
    soak.approve("dry_run")
    lease_id = str(soak.dispatch("inventory")["lease"]["lease_id"])
    stranger = RunnerIdentity.load_or_create(tmp_path / "stranger", "runner.stranger")
    RunnerMailbox(soak.harness.mailbox_root, tmp_path / "stranger").publish_message(
        stranger,
        kind="heartbeat",
        tenant_id="local",
        environment="development",
        correlation_id=lease_id,
        sequence=1,
        lease_id=lease_id,
        operation_id=None,
        occurred_at=_now(),
        payload={
            "stage": "lease_accepted",
            "operation_kind": None,
            "journal_sequence": 1,
            "journal_digest": "sha256:" + "0" * 64,
        },
    )
    result = soak.ingest()
    assert len(result.rejected) == 1 and result.accepted == ()
    assert "runner_heartbeat" not in soak.events()


def test_processed_dispatches_are_cleaned_after_the_retention(
    soak: Soak, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from oak.runner.main import status

    soak.approve("dry_run")
    first = soak.directory(soak.dispatch("inventory"))
    second = soak.directory(soak.dispatch("inventory"))
    assert soak.run() == 0
    assert (first / ".processed").is_file() and (second / ".processed").is_file()
    soak.ingest()  # both completions acknowledged
    old = time.time() - 40 * 86_400
    for directory in (first, second):
        os.utime(directory / ".processed", (old, old))

    # Retention off: nothing is removed.
    monkeypatch.setenv("OAK_RUNNER_DISPATCH_RETENTION_DAYS", "0")
    assert soak.run() == 0
    assert soak.dispatch_directories() == {first, second}

    # Thirty days: the older one goes; the newest processed dispatch stays whatever its age.
    monkeypatch.setenv("OAK_RUNNER_DISPATCH_RETENTION_DAYS", "30")
    assert soak.run() == 0
    assert soak.dispatch_directories() == {second}
    assert "cleaned 1 processed dispatch(es)" in capsys.readouterr().err
    assert (soak.home / "journals" / f"{first.name}.jsonl").is_file(), "a journal was removed"

    # A processed dispatch whose completion is not yet ingested stays, however old.
    third = soak.directory(soak.dispatch("inventory"))
    assert soak.run() == 0  # the second, old and ingested, is no longer the newest
    assert soak.dispatch_directories() == {third}
    os.utime(third / ".processed", (old, old))
    fourth = soak.directory(soak.dispatch("inventory"))
    assert soak.run() == 0
    assert soak.dispatch_directories() == {third, fourth}, "an uningested dispatch was removed"
    soak.ingest()
    assert soak.run() == 0
    assert soak.dispatch_directories() == {fourth}

    # The journals of removed dispatches still tie to their signed completions.
    capsys.readouterr()
    assert status() == 0
    report = json.loads(capsys.readouterr().out)
    heads = {entry["dispatch"]: entry["signed_head"] for entry in report["journals"]}
    assert {heads[path.name] for path in (first, second, third, fourth)} == {"matched"}
    assert report["missing_journals"] == []

    monkeypatch.setenv("OAK_RUNNER_DISPATCH_RETENTION_DAYS", "forever")
    with pytest.raises(OAKError) as refusal:
        soak.run()
    assert refusal.value.code == "OAK-RUNNER-CONFIG"


def test_the_nonce_ledger_keeps_a_nonce_while_its_lease_could_be_replayed(tmp_path: Path) -> None:
    home = tmp_path / "runner-home"
    mailbox = RunnerMailbox(tmp_path / "mailbox", home)
    now = "2026-10-29T12:00:00Z"
    mailbox.consume_lease_nonce("a" * 64, expires_at="2026-10-29T11:00:00Z", now=now)  # lapsed
    mailbox.consume_lease_nonce(
        "b" * 64, expires_at="2026-10-29T11:58:00Z", now=now
    )  # inside the skew
    mailbox.consume_lease_nonce("c" * 64, expires_at="not a time", now=now)  # unreadable: kept
    mailbox.consume_lease_nonce("d" * 64, expires_at=None, now=now)  # unknown: kept
    mailbox.consume_lease_nonce("e" * 64, expires_at="2026-10-29T13:00:00Z", now=now)  # live
    assert mailbox.consumed_lease_nonces() == {"b" * 64, "c" * 64, "d" * 64, "e" * 64}
    assert NONCE_RETENTION_SKEW_SECONDS == 300
    later = "2026-10-29T12:04:00Z"
    mailbox.consume_lease_nonce("f" * 64, expires_at="2026-10-29T13:00:00Z", now=later)
    assert "b" * 64 not in mailbox.consumed_lease_nonces(), "a lapsed lease's nonce was kept"
    assert {"c" * 64, "d" * 64, "e" * 64, "f" * 64} <= mailbox.consumed_lease_nonces()
    ledger = json.loads((home / "consumed-nonces.json").read_text(encoding="utf-8"))
    assert ledger["c" * 64] == "not a time" and ledger["d" * 64] is None


def test_a_ledger_written_before_the_batch_is_read_and_its_nonces_kept_for_ever(
    tmp_path: Path,
) -> None:
    home = tmp_path / "runner-home"
    home.mkdir()
    (home / "consumed-nonces.json").write_text(json.dumps(["a" * 64, "b" * 64]), encoding="utf-8")
    mailbox = RunnerMailbox(tmp_path / "mailbox", home)
    assert mailbox.consumed_lease_nonces() == {"a" * 64, "b" * 64}
    mailbox.consume_lease_nonce(
        "c" * 64, expires_at="2026-10-29T13:00:00Z", now="2030-01-01T00:00:00Z"
    )
    assert mailbox.consumed_lease_nonces() == {"a" * 64, "b" * 64}, "an unknown expiry was dropped"


def test_a_run_records_each_consumed_nonce_with_its_lease_expiry(soak: Soak) -> None:
    soak.approve("dry_run")
    soak.dispatch("inventory")
    assert soak.run() == 0
    ledger = json.loads((soak.home / "consumed-nonces.json").read_text(encoding="utf-8"))
    assert len(ledger) == 1
    (expiry,) = ledger.values()
    assert isinstance(expiry, str) and expiry.endswith("Z")
