# SPDX-License-Identifier: Apache-2.0
"""A scripted Docker daemon for the topology installer, and parameter builders.

The fake keeps a small container table and answers exactly the argument vectors the
adapter builds, so tests assert on behaviour (what exists afterwards, what evidence
says) and on the argv, without a daemon. Anything the adapter was never meant to
send fails the test loudly. A created container's configuration is derived from the
flags it was created with, the way the daemon reports it, so the adapter's read-back
of the hardening is exercised against what the create actually asked for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from oak.domain.runner_adapters import (
    ISOLATION_NEVER_STARTED,
    ISOLATION_STARTED_HARDENED,
    container_name_for,
)
from oak.runner.adapters import CommandResult

CASE_ID = "design-case.public-manual-qa"
TARGET_ID = "target.local-started-fixture"
INSTALLATION_ID = "installation." + "0123456789abcdef01234567"
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
    installation_id: str = INSTALLATION_ID,
    image: str = IMAGE,
    digest: str = DIGEST,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "target_id": target_id,
        "installation_id": installation_id,
        "isolation": isolation,
        "containers": [
            {
                "node_id": node_id,
                "manifest_id": manifest_id,
                "container_name": container_name_for(installation_id, node_id),
                "image_reference": image,
                "image_digest": digest,
            }
            for node_id, manifest_id in nodes
        ],
    }


def names(document: dict[str, Any]) -> list[str]:
    return [str(entry["container_name"]) for entry in document["containers"]]


def owned_labels(
    node_id: str,
    case_id: str = CASE_ID,
    *,
    installation_id: str = INSTALLATION_ID,
    isolation: str = ISOLATION_NEVER_STARTED,
) -> dict[str, str]:
    return {
        "oak.fixture": "true",
        "oak.case": case_id,
        "oak.node": node_id,
        "oak.installation": installation_id,
        "oak.isolation": isolation,
    }


def host_configuration(argv: tuple[str, ...]) -> tuple[dict[str, Any], str]:
    """What the daemon reports back for a container created with these flags."""

    flags = dict(item.split("=", 1) for item in argv if item.startswith("--") and "=" in item)
    memory = {"256m": 268_435_456}.get(flags.get("--memory", ""), 0)
    swap = {"256m": 268_435_456}.get(flags.get("--memory-swap", ""), 0)
    host = {
        "NetworkMode": flags.get("--network", "bridge"),
        "ReadonlyRootfs": "--read-only" in argv,
        "CapDrop": [flags["--cap-drop"]] if "--cap-drop" in flags else None,
        "SecurityOpt": [flags["--security-opt"]] if "--security-opt" in flags else None,
        "Memory": memory,
        "MemorySwap": swap,
        "PidsLimit": int(flags["--pids-limit"]) if "--pids-limit" in flags else None,
        "RestartPolicy": {"Name": flags.get("--restart", "no"), "MaximumRetryCount": 0},
    }
    return host, flags.get("--user", "")


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
    create_then_fail_for: set[str] = field(default_factory=set)
    fail_inspect: bool = False
    fail_rm_for: set[str] = field(default_factory=set)
    keep_after_rm: bool = False
    containers: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    _state_reads: dict[str, int] = field(default_factory=dict)

    def add(
        self,
        name: str,
        labels: dict[str, str],
        status: str = "created",
        *,
        hardened: bool = False,
    ) -> None:
        """A container that already exists, as if created by OAK (or by hand)."""

        from oak.domain.runner_adapters import HARDENING_FLAGS

        argv = ("docker", "create", "--network=none", *(HARDENING_FLAGS if hardened else ()))
        host, user = host_configuration(argv)
        self.containers[name] = {
            "labels": dict(labels),
            "status": status,
            "host": host,
            "user": user,
        }

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
            host, user = host_configuration(argv)
            self.containers[name] = {
                "labels": labels,
                "status": "created",
                "host": host,
                "user": user,
            }
            if name in self.create_then_fail_for:
                return CommandResult(returncode=1, stdout="", stderr="context deadline exceeded")
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
            if template == "{{json .HostConfig}}\t{{json .Config.User}}":
                return _ok(json.dumps(container["host"]) + "\t" + json.dumps(container["user"]))
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
            # Count state reads from the start, so a scripted change after the settle
            # applies to the reads that follow it.
            self._state_reads[name] = 0
            return _ok(name + "\n")
        if verb == "stats":
            return _ok(self.stats + "\n")
        if verb == "rm":
            name = argv[-1]
            if name in self.fail_rm_for:
                return CommandResult(returncode=1, stdout="", stderr="device or resource busy")
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


__all__ = [
    "CASE_ID",
    "DIGEST",
    "IMAGE",
    "INSTALLATION_ID",
    "ISOLATION_STARTED_HARDENED",
    "TARGET_ID",
    "FakeClock",
    "FakeDocker",
    "host_configuration",
    "names",
    "owned_labels",
    "parameters",
]
