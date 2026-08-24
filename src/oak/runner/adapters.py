# SPDX-License-Identifier: Apache-2.0
"""Runner adapters: bounded local inventory and the isolated container fixture.

Adapters map validated typed parameters to fixed allowlisted argument vectors.
The executable comes from a code-level allowlist, never from plan data; no
shell interpreter is involved anywhere, and command output is size-bounded.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from oak.domain import OAKError
from oak.domain.runner_adapters import CONTAINER_NAME_PATTERN

MAXIMUM_OUTPUT_BYTES = 65_536
ALLOWLISTED_EXECUTABLES = frozenset({"docker"})
_IMAGE_PATTERN = re.compile(r"^[a-z0-9][a-zA-Z0-9./_:@-]*$")
_NAME_PATTERN = re.compile(CONTAINER_NAME_PATTERN)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandExecutor = Callable[[tuple[str, ...], int], CommandResult]


def default_executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
    executable = shutil.which(argv[0])
    if executable is None:
        raise OAKError("OAK-RUNNER-EXECUTABLE", f"{argv[0]} is not installed on this host")
    completed = subprocess.run(
        (executable, *argv[1:]),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env={"PATH": os.defpath},
        check=False,
        shell=False,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout[:MAXIMUM_OUTPUT_BYTES],
        stderr=completed.stderr[:MAXIMUM_OUTPUT_BYTES],
    )


def collect_inventory() -> dict[str, Any]:
    """Bounded host capabilities; no file scraping and no secret access."""

    memory_bytes = 0
    if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
        memory_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    usage = shutil.disk_usage("/")
    return {
        "operating_system": platform.system().lower(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "ram_gib": round(memory_bytes / 2**30, 1),
        "storage_gib": round(usage.total / 2**30, 1),
    }


class ContainerFixtureAdapter:
    """Create, inspect, and remove one labelled never-started container."""

    def __init__(self, executor: CommandExecutor = default_executor) -> None:
        self._executor = executor

    def apply(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        name, image = self._validated(parameters)
        argv = (
            "docker",
            "create",
            "--network=none",
            "--label",
            "oak.fixture=true",
            "--name",
            name,
            image,
        )
        result = self._run(argv, timeout_seconds)
        if result.returncode != 0:
            raise OAKError("OAK-RUNNER-APPLY", "fixture container creation failed")
        self._verify_resolved_digest(name, str(parameters["image_digest"]), timeout_seconds)
        return {
            "container_name": name,
            "created": True,
            "resolved_image_digest": str(parameters["image_digest"]),
        }

    def _verify_resolved_digest(self, name: str, digest: str, timeout_seconds: int) -> None:
        """Require the runtime's resolved image to carry the approved repo digest.

        The digest pin in the create argv is an input assertion: it constrains what the
        daemon is asked for, not what it resolved (RR-003, TM-08 time-of-use). This reads
        back the created container's image and demands a `RepoDigests` entry ending in
        the approved digest. Anything else — an inspect failure, an image with no repo
        digest (for example one loaded from a tarball, which cannot prove its identity),
        or a mismatch — removes the container and denies, so no unproven container
        survives a failed admission.
        """

        inspected = self._run(
            ("docker", "inspect", "--format", "{{.Image}}", name), timeout_seconds
        )
        image_id = inspected.stdout.strip()
        entries: list[Any] = []
        if inspected.returncode == 0 and image_id:
            listed = self._run(
                ("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id),
                timeout_seconds,
            )
            if listed.returncode == 0:
                try:
                    parsed = json.loads(listed.stdout)
                except ValueError:
                    parsed = None
                if isinstance(parsed, list):
                    entries = parsed
        if not any(isinstance(entry, str) and entry.endswith(f"@{digest}") for entry in entries):
            self._run(("docker", "rm", "--force", name), timeout_seconds)
            raise OAKError(
                "OAK-RUNNER-IMAGE",
                "resolved image does not carry the approved digest",
            )

    def verify_present(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        name, _ = self._validated(parameters)
        result = self._run(
            ("docker", "inspect", "--format", "{{.State.Status}}", name), timeout_seconds
        )
        return {
            "container_name": name,
            "present": result.returncode == 0,
            "status": result.stdout.strip() if result.returncode == 0 else None,
        }

    def rollback(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(parameters, timeout_seconds, operation="rollback")

    def destroy(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(parameters, timeout_seconds, operation="destroy")

    def _remove(
        self, parameters: dict[str, Any], timeout_seconds: int, *, operation: str
    ) -> dict[str, Any]:
        name, _ = self._validated(parameters)
        result = self._run(("docker", "rm", "--force", name), timeout_seconds)
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise OAKError("OAK-RUNNER-ROLLBACK", f"fixture container {operation} failed")
        return {"container_name": name, "removed": True}

    def _run(self, argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        if argv[0] not in ALLOWLISTED_EXECUTABLES:
            raise OAKError("OAK-RUNNER-EXECUTABLE", "executable is not allowlisted")
        return self._executor(argv, timeout_seconds)

    @staticmethod
    def _validated(parameters: dict[str, Any]) -> tuple[str, str]:
        name = str(parameters["container_name"])
        reference = str(parameters["image_reference"])
        digest = str(parameters["image_digest"])
        if _NAME_PATTERN.fullmatch(name) is None:
            raise OAKError("OAK-RUNNER-PARAMETERS", "container name is not permitted")
        if _IMAGE_PATTERN.fullmatch(reference) is None or reference.startswith("-"):
            raise OAKError("OAK-RUNNER-PARAMETERS", "image reference is not permitted")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise OAKError("OAK-RUNNER-PARAMETERS", "image digest is not permitted")
        # The approved digest is the only pin that may reach the runtime. A
        # reference that carries its own digest could otherwise smuggle a
        # different image past the approval, so it is refused outright.
        if "@" in reference:
            raise OAKError(
                "OAK-RUNNER-PARAMETERS",
                "image reference must not carry its own digest",
            )
        image = f"{reference}@{digest}"
        if _IMAGE_PATTERN.fullmatch(image) is None:
            raise OAKError("OAK-RUNNER-PARAMETERS", "pinned image reference is not permitted")
        return name, image
