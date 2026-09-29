# SPDX-License-Identifier: Apache-2.0
"""A scripted Docker daemon for the topology installer, and parameter builders.

The fake keeps a small container table and answers exactly the argument vectors the
adapter builds, so tests assert on behaviour (what exists afterwards, what evidence
says) and on the argv, without a daemon. Anything the adapter was never meant to
send fails the test loudly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from oak.domain.runner_adapters import (
    ISOLATION_NEVER_STARTED,
    container_name_for,
)
from oak.runner.adapters import CommandResult

CASE_ID = "design-case.public-manual-qa"
TARGET_ID = "target.local-started-fixture"
IMAGE = "rancher/mirrored-pause"
DIGEST = "sha256:" + "e" * 64
NODES = (
    ("node.retrieval", "component.fixture-lexical-search"),
    ("node.generation", "component.fixture-local-model"),
)


def parameters(
    isolation: str = ISOLATION_NEVER_STARTED,
    *,
    nodes: tuple[tuple[str, str], ...] = NODES,
    case_id: str = CASE_ID,
    target_id: str = TARGET_ID,
    image: str = IMAGE,
    digest: str = DIGEST,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "target_id": target_id,
        "isolation": isolation,
        "containers": [
            {
                "node_id": node_id,
                "manifest_id": manifest_id,
                "container_name": container_name_for(case_id, target_id, node_id),
                "image_reference": image,
                "image_digest": digest,
            }
            for node_id, manifest_id in nodes
        ],
    }


def names(document: dict[str, Any]) -> list[str]:
    return [str(entry["container_name"]) for entry in document["containers"]]


def owned_labels(node_id: str, case_id: str = CASE_ID) -> dict[str, str]:
    return {"oak.fixture": "true", "oak.case": case_id, "oak.node": node_id}


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


def _absent(name: str) -> CommandResult:
    return CommandResult(
        returncode=1, stdout="", stderr=f"Error response from daemon: No such container: {name}"
    )


@dataclass
class FakeDocker:
    """A container table plus scripted answers for start, health and stats."""

    repo_digests: list[str] = field(default_factory=lambda: [f"{IMAGE}@{DIGEST}"])
    start_status: str = "running"
    health: str | None = None
    exit_code: int = 0
    stats: str = "1.5MiB / 256MiB"
    status_after_settle: str | None = None
    fail_create_for: set[str] = field(default_factory=set)
    fail_inspect: bool = False
    keep_after_rm: bool = False
    containers: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    _state_reads: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, labels: dict[str, str], status: str = "created") -> None:
        self.containers[name] = {"labels": dict(labels), "status": status}

    def __call__(self, argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        self.calls.append(argv)
        assert argv[0] == "docker", argv
        verb = argv[1]
        if verb == "create":
            name = argv[argv.index("--name") + 1]
            if name in self.fail_create_for:
                return CommandResult(returncode=1, stdout="", stderr="create failed")
            labels = dict(
                argv[index + 1].split("=", 1)
                for index, value in enumerate(argv[:-1])
                if value == "--label"
            )
            self.add(name, labels)
            return _ok(name + "\n")
        if verb == "inspect":
            if self.fail_inspect:
                return CommandResult(returncode=1, stdout="", stderr="Cannot connect")
            name = argv[-1]
            template = argv[argv.index("--format") + 1]
            container = self.containers.get(name)
            if container is None:
                return _absent(name)
            if template == "{{json .Config.Labels}}":
                return _ok(json.dumps(container["labels"]) + "\n")
            if template == "{{.Image}}":
                return _ok("sha256:imageid\n")
            if template == "{{json .State}}":
                reads = self._state_reads.get(name, 0) + 1
                self._state_reads[name] = reads
                status = container["status"]
                if self.status_after_settle is not None and status == "running" and reads > 1:
                    status = container["status"] = self.status_after_settle
                state: dict[str, Any] = {"Status": status, "ExitCode": self.exit_code}
                if self.health is not None:
                    state["Health"] = {"Status": self.health, "Log": [{"Output": "secret"}]}
                return _ok(json.dumps(state) + "\n")
            raise AssertionError(f"unexpected inspect template {template}")
        if argv[1:3] == ("image", "inspect"):
            return _ok(json.dumps(self.repo_digests) + "\n")
        if verb == "start":
            name = argv[-1]
            self.containers[name]["status"] = self.start_status
            return _ok(name + "\n")
        if verb == "stats":
            return _ok(self.stats + "\n")
        if verb == "rm":
            name = argv[-1]
            if not self.keep_after_rm:
                self.containers.pop(name, None)
            return _ok(name + "\n")
        raise AssertionError(f"the adapter sent an unexpected command: {argv}")

    def verbs(self) -> list[str]:
        return [" ".join(argv[1:3]) if argv[1] == "image" else argv[1] for argv in self.calls]


class FakeClock:
    """Monotonic time that advances only when the adapter sleeps."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
