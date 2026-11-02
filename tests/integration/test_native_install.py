# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: a native installation, from dispatch to uninstall, through the real runner.

The stand-in profile installs OAK's own server for each node (ADR-0019): the runner copies
it, verifies its size and digest, starts it on 127.0.0.1, probes it and stops it, so after
the install nothing listens and nothing runs. The installation is one directory the runner
marked as its own; destroying it removes exactly that directory, and a failed check removes
only what the failed install created.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.contracts import load_yaml_document
from oak.domain import ArtifactReference
from oak.runner.native import MARKER, NativeProcessAdapter
from tests.container_support import FakeClock
from tests.runner_support import ROOT, build_compiled_case, consent_digest, enroll_test_runner

pytestmark = pytest.mark.integration

EXAMPLE = ROOT / "examples/targets/local-native-stand-in.yaml"
INSTALL = ("architecture", "native_consent", "apply")


def _now() -> str:
    # The runner judges leases on the wall clock, so this journey runs on it too.
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _free_ports(count: int) -> list[int]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [int(item.getsockname()[1]) for item in sockets]
    finally:
        for item in sockets:
            item.close()


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


class NativeJourney:
    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, probe_path: str = "/health"
    ) -> None:
        document = load_yaml_document(EXAMPLE.read_text(encoding="utf-8"))
        components = document["execution"]["native_components"]
        self.ports = _free_ports(len(components))
        for entry, port in zip(components, self.ports, strict=True):
            entry["listen_port"] = port
            entry["health_probe"] = {"path": probe_path}
        self.profile = tmp_path / "native-target.yaml"
        self.profile.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        self.harness = build_compiled_case(tmp_path, target_name=str(self.profile), now=_now())
        self.runner_home = tmp_path / "runner"
        self.counter = 0
        monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(self.harness.mailbox_root))
        monkeypatch.setenv("OAK_RUNNER_HOME", str(self.runner_home))
        enroll_test_runner(self.harness.trust_directory, self.runner_home)
        monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(self.harness.trust_directory))
        monkeypatch.setenv("OAK_RUNNER_TARGET_PROFILE", str(self.profile))
        self.harness.release.sign_plan(self.context("sign"))

    @property
    def case(self) -> dict[str, Any]:
        return self.harness.release._repository.current_case()

    @property
    def plan(self) -> dict[str, Any]:
        return self.harness.release._repository.read_json_artifact(
            ArtifactReference.from_document(self.case["runner_plan_ref"])
        )

    def context(self, label: str):
        self.counter += 1
        return self.harness.context(f"{label}-{self.counter:04d}-native", str(self.case["version"]))

    def approve(self, action: str):
        return self.harness.release.approve(
            action,
            self.context(f"approve-{action.replace('_', '-')}"),
            consent_digest=consent_digest() if action == "native_consent" else None,
        )

    def install(self, native_adapter: NativeProcessAdapter | None = None) -> dict[str, Any]:
        for action in INSTALL:
            self.approve(action)
        return self.dispatch_and_run(("apply",), native_adapter)

    def dispatch_and_run(
        self, kinds: tuple[str, ...], native_adapter: NativeProcessAdapter | None = None
    ) -> dict[str, Any]:
        from oak.runner.main import run_once

        self.harness.release.dispatch(kinds, self.context("dispatch"))
        run_once(native_adapter=native_adapter)
        ingested = self.harness.release.ingest_runner_messages(self.context("ingest"))
        assert ingested.rejected == (), ingested
        return dict(ingested.accepted[-1]["payload"])

    @property
    def installation(self) -> Path:
        apply = next(item for item in self.plan["operations"] if item["kind"] == "apply")
        return self.runner_home / "native" / str(apply["parameters"]["installation_id"])


@pytest.fixture
def journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> NativeJourney:
    return NativeJourney(tmp_path, monkeypatch)


def _evidence(payload: dict[str, Any], category: str) -> dict[str, Any]:
    return next(item["content"] for item in payload["evidence"] if item["category"] == category)


def test_a_native_install_proves_each_component_and_leaves_nothing_running(
    journey: NativeJourney,
) -> None:
    payload = journey.install()

    assert payload["outcome"] == "succeeded", payload
    assert payload["applied_kinds"] == ["apply"]
    assert journey.case["status"] == "deployed"
    status = _evidence(payload, "status")
    assert status["mode"] == "native"
    assert {row["node_id"] for row in status["installation"]} == {
        "node.retrieval",
        "node.generation",
    }
    assert all(
        artifact["verified"] for row in status["installation"] for artifact in row["artifacts"]
    )
    tested = _evidence(payload, "test_result")
    assert tested["passed"] is True and tested["stopped"] is True
    # Stopped once proven: nothing listens on any acknowledged port after the install.
    assert not any(_listening(port) for port in journey.ports)
    marker = json.loads((journey.installation / MARKER).read_text(encoding="utf-8"))
    assert marker["installation_id"] == journey.installation.name
    assert marker["state"] == "installed"
    assert oct(journey.installation.stat().st_mode & 0o777) == "0o700"


def test_destroy_removes_exactly_the_installation(journey: NativeJourney) -> None:
    journey.install()
    beside = journey.installation.parent / "canary.txt"
    beside.write_text("not the installation's", encoding="utf-8")
    home_canary = journey.runner_home / "canary.txt"
    home_canary.write_text("the operator's", encoding="utf-8")

    journey.approve("destroy")
    payload = journey.dispatch_and_run(("destroy",))

    assert payload["outcome"] == "succeeded", payload
    removal = _evidence(payload, "rollback_result")
    assert removal == {
        "installation_id": journey.installation.name,
        "removed": True,
        "absent": True,
    }
    assert not journey.installation.exists()
    assert beside.read_text(encoding="utf-8") == "not the installation's"
    assert home_canary.read_text(encoding="utf-8") == "the operator's"


def test_a_component_that_fails_its_check_is_stopped_and_its_install_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The stand-in answers only /health, so a profile probing elsewhere never passes.
    journey = NativeJourney(tmp_path, monkeypatch, probe_path="/missing")
    clock = FakeClock()

    payload = journey.install(
        NativeProcessAdapter(journey.runner_home / "native", clock=clock, sleep=clock.sleep)
    )

    assert payload["outcome"] == "failed" and payload["failed_kind"] == "apply", payload
    assert journey.case["status"] == "deployment_approved"
    tested = _evidence(payload, "test_result")
    assert tested["passed"] is False and tested["stopped"] is True
    assert not any(_listening(port) for port in journey.ports)
    assert _evidence(payload, "rollback_result")["removed"] is True
    assert not journey.installation.exists()


def test_a_directory_the_runner_did_not_create_is_never_adopted_or_removed(
    journey: NativeJourney,
) -> None:
    journey.installation.mkdir(parents=True)
    canary = journey.installation / "keep.txt"
    canary.write_text("someone else's", encoding="utf-8")

    payload = journey.install()

    assert payload["outcome"] == "failed" and payload["failed_kind"] == "apply", payload
    kept = _evidence(payload, "rollback_result")
    assert kept["removed"] is False and kept["kept"] is True
    assert canary.read_text(encoding="utf-8") == "someone else's"
    assert not (journey.installation / MARKER).exists()
