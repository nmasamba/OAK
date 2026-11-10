# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: a native installation, from dispatch to uninstall, through the real runner.

The stand-in profile installs OAK's own server for each node (ADR-0019): the runner copies
it, verifies its size and digest, starts it on 127.0.0.1, probes it and stops it, so after
the install nothing listens and nothing runs. The installation is one directory the runner
marked as its own; destroying it removes exactly that directory, and a failed check removes
only what the failed install created.
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tarfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.contracts import load_yaml_document
from oak.domain import ArtifactReference
from oak.runner import main as runner_main
from oak.runner import native_network
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        probe_path: str = "/health",
        adjust: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        document = load_yaml_document(EXAMPLE.read_text(encoding="utf-8"))
        if adjust is not None:
            adjust(document)
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

    def observe(self) -> dict[str, Any]:
        return dict(self.harness.release.record_observation(self.context("observe")).document)

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


def test_an_observation_reads_the_native_install_and_its_removal(journey: NativeJourney) -> None:
    journey.install()

    installed = journey.observe()
    assert journey.case["status"] == "observing"
    assert installed["target"]["isolation"] == "native-user-consented"
    assert installed["installation_state"] == "present"
    measures = {item["id"]: item for item in installed["deployment_measures"]}
    assert measures["EV-DEP-01"]["result"] == "pass"
    assert measures["smoke-test"]["result"] == "pass"
    assert {row["node_id"] for row in installed["unpredicted_measurements"]} == {
        "node.retrieval",
        "node.generation",
    }
    assert all(
        row["installation_id"] == journey.installation.name
        for row in installed["unpredicted_measurements"]
    )

    journey.approve("destroy")
    journey.dispatch_and_run(("destroy",))
    assert journey.observe()["installation_state"] == "removed"


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


# A release and a model the runner "downloads", over bytes held here: nothing leaves the
# machine. The model's URL carries a query string, as a signed download link would.
RELEASE_URL = "https://example.org/releases/download/b1/llama-b1-bin.tar.gz"
MODEL_URL = "https://example.org/models/tiny-q4.gguf?token=query-secret"
MODEL = b"GGUF" * 1000


def _release() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        member = tarfile.TarInfo("build/bin/llama-server")
        member.size = 4
        bundle.addfile(member, io.BytesIO(b"\x7fELF"))
    return buffer.getvalue()


FILES = {RELEASE_URL: _release(), MODEL_URL: MODEL}


def _keyed_probe(port: int, path: str, timeout: float) -> int:
    """`llama-server` with the installation's key (OAK-V1-045): its health path answers, and
    nothing else does for a request without the key."""

    return 200 if path == "/health" else 401


class _Response(io.BytesIO):
    def __init__(self, body: bytes, url: str) -> None:
        super().__init__(body)
        self._url = url

    def geturl(self) -> str:
        return self._url


class _Terminal(io.StringIO):
    """Keeps what it is shown, and always has room for more."""

    _room = os.open(os.devnull, os.O_WRONLY)

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return self._room


def _downloading(document: dict[str, Any]) -> None:
    """The stand-in profile with its model components as `llama_cpp_server` downloads."""

    def artifact(role: str, source: str, format_: str) -> dict[str, Any]:
        content = FILES[source]
        return {
            "role": role,
            "source": source,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "format": format_,
        }

    execution = document["execution"]
    execution["allowed_download_hosts"] = ["example.org"]
    for entry in execution["native_components"]:
        if "model" in entry["manifest_id"]:
            entry["harness_kind"] = "llama_cpp_server"
            entry["artifacts"] = [
                artifact("harness", RELEASE_URL, "tar.gz"),
                artifact("model", MODEL_URL, "file"),
            ]


def _install_with_downloads(journey: NativeJourney, monkeypatch: pytest.MonkeyPatch) -> None:
    """A native install through the real `run_once`, which builds its own adapter, so a test
    sees what it wires. A heartbeat at every step would show one driven by progress."""

    def popen(argv: list[str], **options: Any) -> Any:
        return subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"], **options
        )

    def adapter(root: Path, **keywords: Any) -> NativeProcessAdapter:
        return NativeProcessAdapter(
            root,
            fetch=functools.partial(
                native_network.fetch, opener=lambda url, timeout: _Response(FILES[url], url)
            ),
            popen=popen,
            probe=_keyed_probe,
            **keywords,
        )

    monkeypatch.setattr(runner_main, "NativeProcessAdapter", adapter)
    monkeypatch.setattr(native_network, "CHUNK_BYTES", 1000)
    for action in INSTALL:
        journey.approve(action)
    journey.harness.release.dispatch(("apply",), journey.context("dispatch"))
    assert runner_main.run_once(heartbeat_interval_seconds=0) == 0


def _recorded(journey: NativeJourney) -> dict[str, Any]:
    """All the runner wrote down: its journals and every signed message it published."""

    journals = sorted((journey.runner_home / "journals").glob("*.jsonl"))
    messages = sorted((journey.harness.mailbox_root / "messages").glob("*.json"))
    return {
        "journal": [
            json.loads(line)
            for path in journals
            for line in path.read_text(encoding="utf-8").splitlines()
        ],
        "messages": [json.loads(path.read_text(encoding="utf-8")) for path in messages],
    }


def _shape(value: Any) -> Any:
    """A document with each value replaced by its type: its ids and times differ per run."""

    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return type(value).__name__


def test_a_download_shows_on_a_terminal_and_nothing_new_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "piped").mkdir()
    (tmp_path / "watched").mkdir()
    piped = NativeJourney(tmp_path / "piped", monkeypatch, adjust=_downloading)
    _install_with_downloads(piped, monkeypatch)
    captured = capsys.readouterr().out
    without = _recorded(piped)

    watched = NativeJourney(tmp_path / "watched", monkeypatch, adjust=_downloading)
    terminal = _Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    _install_with_downloads(watched, monkeypatch)
    monkeypatch.undo()
    shown = terminal.getvalue()
    recorded = _recorded(watched)

    # A person watching sees each file, how far along it is, and then the result.
    assert (
        f"downloading llama-b1-bin.tar.gz, the harness ({len(FILES[RELEASE_URL])} bytes)\n" in shown
    )
    assert "downloading tiny-q4.gguf, the model (4,000 bytes)\n" in shown
    assert "\r  1,000 bytes of 4,000 bytes (25%)" in shown
    assert "\r  4,000 bytes of 4,000 bytes (100%)\ncompleted " in shown
    before_the_result = shown.partition("completed ")[0]
    for private in ("query-secret", "example.org", str(tmp_path)):
        assert private not in before_the_result

    # Anything that captures stdout gets exactly what it got before.
    assert [line.split()[0] for line in captured.splitlines()] == ["completed", "installed"]
    assert "\r" not in captured and "downloading" not in captured

    # Both installs passed, and the terminal added no entry, message or field to either.
    for document in (recorded, without):
        kinds = {message["kind"]: message for message in document["messages"]}
        assert kinds["completion"]["payload"]["outcome"] == "succeeded"
        assert "heartbeat" in kinds
    assert _shape(recorded) == _shape(without)
    written = json.dumps(recorded)
    for private in ("tiny-q4.gguf", "llama-b1-bin", "query-secret", "example.org", str(tmp_path)):
        assert private not in written
