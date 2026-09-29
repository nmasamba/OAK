# SPDX-License-Identifier: Apache-2.0
"""Runner adapters: bounded local inventory and the isolated topology installer.

Adapters map validated typed parameters to fixed allowlisted argument vectors.
The executable comes from a code-level allowlist, never from plan data; no
shell interpreter is involved anywhere, and command output is size-bounded.
What a command prints is parsed into typed values and then discarded: no
container log, environment or raw output ever reaches evidence.
"""

from __future__ import annotations

import atexit
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oak.domain import OAKError
from oak.domain.runner_adapters import (
    CONTAINER_LABEL_CASE,
    CONTAINER_LABEL_FIXTURE,
    CONTAINER_LABEL_NODE,
    CONTAINER_NAME_PATTERN,
    HARDENING_FLAGS,
    IDENTIFIER_PATTERN,
    IMAGE_REFERENCE_PATTERN,
    ISOLATION_NEVER_STARTED,
    ISOLATION_STARTED_HARDENED,
    MAXIMUM_CONTAINERS,
    container_name_for,
)

MAXIMUM_OUTPUT_BYTES = 65_536
ALLOWLISTED_EXECUTABLES = frozenset({"docker"})
# The readiness wait per node, well inside the per-call timeout and the lease: a node
# that is not running (or, with a HEALTHCHECK, healthy) by then fails the smoke test.
READINESS_BUDGET_SECONDS = 15.0
READINESS_POLL_SECONDS = 0.5
# After a node first reads as ready it must still be running this much later, so a
# process that starts and immediately dies is not reported as up.
READINESS_SETTLE_SECONDS = 1.0
_NAME_PATTERN = re.compile(CONTAINER_NAME_PATTERN)
_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)
_IMAGE_PATTERN = re.compile(IMAGE_REFERENCE_PATTERN)
_DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
_CONTAINER_STATES = frozenset(
    {"created", "restarting", "running", "removing", "paused", "exited", "dead"}
)
_HEALTH_STATES = frozenset({"starting", "healthy", "unhealthy"})
_MEMORY_PATTERN = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?i?B)\b")
_MEMORY_UNITS = {
    "B": 1,
    "kB": 1_000,
    "KB": 1_000,
    "KiB": 1_024,
    "MB": 1_000_000,
    "MiB": 1_048_576,
    "GB": 1_000_000_000,
    "GiB": 1_073_741_824,
    "TB": 1_000_000_000_000,
    "TiB": 1_099_511_627_776,
}


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandExecutor = Callable[[tuple[str, ...], int], CommandResult]


@dataclass(slots=True)
class AdapterFailureError(OAKError):
    """A failed operation that says what it changed and what it measured first.

    ``created`` names the containers this invocation created, so compensation removes
    exactly those and never one that was already there; ``evidence`` carries the typed
    results gathered before the failure, so a failed install still reports why.
    """

    created: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()


def isolated_executor(docker_config: Path) -> CommandExecutor:
    """An executor whose child sees only ``PATH`` and an empty runner-owned Docker config.

    The Docker CLI reads the operator's ``~/.docker/config.json`` even with no ``HOME``
    in its environment. That file can name a credential helper that is not on the
    runner's minimal ``PATH`` — Docker Desktop's ``credsStore: desktop`` is one — and then
    every pull fails, even of a public image; it can also select a CLI context pointing
    somewhere other than the default socket. An empty config owned by the runner means
    the operator's registry credentials and helpers are never used, public images are
    pulled anonymously, and only the default socket is reached (RR-013).
    """

    def execute(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        executable = shutil.which(argv[0])
        if executable is None:
            raise OAKError("OAK-RUNNER-EXECUTABLE", f"{argv[0]} is not installed on this host")
        docker_config.mkdir(parents=True, exist_ok=True, mode=0o700)
        completed = subprocess.run(
            (executable, *argv[1:]),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={"PATH": os.defpath, "DOCKER_CONFIG": str(docker_config)},
            check=False,
            shell=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout[:MAXIMUM_OUTPUT_BYTES],
            stderr=completed.stderr[:MAXIMUM_OUTPUT_BYTES],
        )

    return execute


def default_executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
    """The isolated executor over a private, process-lifetime empty Docker config."""

    global _DEFAULT_DOCKER_CONFIG
    if _DEFAULT_DOCKER_CONFIG is None:
        _DEFAULT_DOCKER_CONFIG = Path(tempfile.mkdtemp(prefix="oak-runner-docker-config-"))
        atexit.register(shutil.rmtree, _DEFAULT_DOCKER_CONFIG, ignore_errors=True)
    return isolated_executor(_DEFAULT_DOCKER_CONFIG)(argv, timeout_seconds)


_DEFAULT_DOCKER_CONFIG: Path | None = None


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


@dataclass(frozen=True, slots=True)
class _Container:
    node_id: str
    manifest_id: str
    name: str
    digest: str
    image: str


@dataclass(frozen=True, slots=True)
class _Installation:
    case_id: str
    target_id: str
    isolation: str
    containers: tuple[_Container, ...]

    @property
    def started(self) -> bool:
        return self.isolation == ISOLATION_STARTED_HARDENED


class ContainerFixtureAdapter:
    """Install, smoke-test and remove the selected topology as labelled containers.

    One container per installable node, named for its case, target and node, created
    with ``--network=none`` from an acknowledged digest-pinned image. On a profile that
    acknowledges starting, each is also started under the fixed hardening flags and
    must reach running (or healthy, when the image declares a HEALTHCHECK) within a
    bounded wait. Only containers carrying this case's labels are ever adopted or
    removed; a foreign container with the same name is a denial, never an adoption and
    never a removal.
    """

    def __init__(
        self,
        executor: CommandExecutor = default_executor,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._executor = executor
        self._clock = clock
        self._sleeper = sleeper
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))

    # -- apply -----------------------------------------------------------------------

    def apply(
        self,
        parameters: dict[str, Any],
        timeout_seconds: int,
        *,
        deadline: datetime | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Create (or adopt) every node, then smoke-test the installation.

        Returns the evidence items. Raises ``AdapterFailureError`` naming exactly the
        containers this call created, so the caller compensates for those alone.
        """

        installation = _installation(parameters)
        created: list[str] = []
        installed: list[dict[str, Any]] = []
        tested: list[dict[str, Any]] = []
        measured: list[dict[str, Any]] = []

        def evidence() -> tuple[dict[str, Any], ...]:
            items: list[dict[str, Any]] = [
                {
                    "category": "status",
                    "operation": "apply",
                    "content": {"isolation": installation.isolation, "installation": installed},
                }
            ]
            if tested:
                items.append(
                    {
                        "category": "test_result",
                        "operation": "apply",
                        "content": {
                            "started": installation.started,
                            "passed": all(row["passed"] for row in tested),
                            "smoke_test": tested,
                        },
                    }
                )
            if measured:
                items.append(
                    {
                        "category": "aggregate_metric",
                        "operation": "apply",
                        "content": {"memory": measured},
                    }
                )
            return tuple(items)

        try:
            for container in installation.containers:
                self._before_side_effect(deadline)
                labels = self._labels(container.name, timeout_seconds)
                if labels is None:
                    self._create(container, installation, timeout_seconds)
                    created.append(container.name)
                    outcome = "created"
                else:
                    self._require_owned(labels, installation, container)
                    outcome = "already_present"
                self._verify_resolved_digest(container.name, container.digest, timeout_seconds)
                installed.append(
                    {
                        "node_id": container.node_id,
                        "manifest_id": container.manifest_id,
                        "container_name": container.name,
                        "outcome": outcome,
                        "resolved_image_digest": container.digest,
                    }
                )
            for container in installation.containers:
                if installation.started:
                    self._before_side_effect(deadline)
                    row, memory = self._start_and_test(container, timeout_seconds)
                    tested.append(row)
                    measured.append(memory)
                else:
                    tested.append(self._never_started_check(container, timeout_seconds))
        except AdapterFailureError:
            raise
        except OAKError as error:
            raise AdapterFailureError(
                error.code, error.message, created=tuple(created), evidence=evidence()
            ) from error
        if not all(row["passed"] for row in tested):
            raise AdapterFailureError(
                "OAK-RUNNER-SMOKE-TEST",
                "the installation did not pass its smoke test",
                created=tuple(created),
                evidence=evidence(),
            )
        return evidence()

    def _create(
        self, container: _Container, installation: _Installation, timeout_seconds: int
    ) -> None:
        hardening = HARDENING_FLAGS if installation.started else ()
        argv = (
            "docker",
            "create",
            "--network=none",
            *hardening,
            "--label",
            f"{CONTAINER_LABEL_FIXTURE}=true",
            "--label",
            f"{CONTAINER_LABEL_CASE}={installation.case_id}",
            "--label",
            f"{CONTAINER_LABEL_NODE}={container.node_id}",
            "--name",
            container.name,
            container.image,
        )
        if self._run(argv, timeout_seconds).returncode != 0:
            raise OAKError("OAK-RUNNER-APPLY", "fixture container creation failed")

    def _verify_resolved_digest(self, name: str, digest: str, timeout_seconds: int) -> None:
        """Require the runtime's resolved image to carry the approved repo digest.

        The digest pin in the create argv is an input assertion: it constrains what the
        daemon is asked for, not what it resolved (RR-003, TM-08 time-of-use). This reads
        back the container's image and demands a `RepoDigests` entry ending in the
        approved digest. Anything else — an inspect failure of any kind, an image with no
        repo digest (one loaded from a tarball cannot prove its identity), or a mismatch —
        denies. A container this call created is then removed by compensation; one that
        was already there is left for an operator, never deleted by an install.
        """

        inspected = self._run(
            ("docker", "inspect", "--type=container", "--format", "{{.Image}}", name),
            timeout_seconds,
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
            raise OAKError(
                "OAK-RUNNER-IMAGE",
                "resolved image does not carry the approved digest",
            )

    def _never_started_check(self, container: _Container, timeout_seconds: int) -> dict[str, Any]:
        state, _health, _exit_code = self._state(container.name, timeout_seconds)
        return {
            "node_id": container.node_id,
            "container_name": container.name,
            "state": state,
            "health": "none",
            "exit_code": None,
            "ready": None,
            "startup_seconds": None,
            "passed": state == "created",
            "reason": None if state == "created" else "not_created",
        }

    def _start_and_test(
        self, container: _Container, timeout_seconds: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started_at = self._clock()
        result = self._run(("docker", "start", container.name), timeout_seconds)
        state, health, exit_code = "unknown", "none", None
        reason: str | None = None
        ready_at: float | None = None
        if result.returncode != 0:
            reason = "start_failed"
            state, health, exit_code = self._state(container.name, timeout_seconds)
        else:
            while True:
                state, health, exit_code = self._state(container.name, timeout_seconds)
                if state in {"exited", "dead"}:
                    reason = "exited"
                    break
                if health == "unhealthy":
                    reason = "unhealthy"
                    break
                if state == "running" and health in {"none", "healthy"}:
                    ready_at = self._clock()
                    self._sleeper(READINESS_SETTLE_SECONDS)
                    state, health, exit_code = self._state(container.name, timeout_seconds)
                    if state != "running" or health == "unhealthy":
                        ready_at = None
                        reason = "stopped_after_start"
                    break
                if self._clock() - started_at >= READINESS_BUDGET_SECONDS:
                    reason = "readiness_timeout"
                    break
                self._sleeper(READINESS_POLL_SECONDS)
        ready = ready_at is not None
        memory = self._memory_bytes(container.name, timeout_seconds) if ready else None
        row = {
            "node_id": container.node_id,
            "container_name": container.name,
            "state": state,
            "health": health,
            "exit_code": exit_code if state in {"exited", "dead"} else None,
            "ready": ready,
            "startup_seconds": round(ready_at - started_at, 2) if ready_at is not None else None,
            "passed": ready,
            "reason": reason,
        }
        metric = {
            "node_id": container.node_id,
            "container_name": container.name,
            "memory_bytes": memory,
        }
        return row, metric

    def _state(self, name: str, timeout_seconds: int) -> tuple[str, str, int | None]:
        """The container's status, health and exit code, from a fixed vocabulary.

        Only these three values leave this method; the rest of the inspect output —
        which can include the image's health-probe output — is discarded here.
        """

        result = self._run(
            ("docker", "inspect", "--type=container", "--format", "{{json .State}}", name),
            timeout_seconds,
        )
        if result.returncode != 0:
            return ("absent" if _is_absent(result) else "unknown"), "none", None
        try:
            document = json.loads(result.stdout)
        except ValueError:
            return "unknown", "none", None
        if not isinstance(document, dict):
            return "unknown", "none", None
        status = document.get("Status")
        state = status if isinstance(status, str) and status in _CONTAINER_STATES else "unknown"
        health_block = document.get("Health")
        health = "none"
        if isinstance(health_block, dict):
            value = health_block.get("Status")
            health = value if isinstance(value, str) and value in _HEALTH_STATES else "unknown"
        exit_value = document.get("ExitCode")
        exit_code = exit_value if isinstance(exit_value, int) else None
        return state, health, exit_code

    def _memory_bytes(self, name: str, timeout_seconds: int) -> int | None:
        """One steady-state memory reading, parsed to bytes; None when unreadable."""

        result = self._run(
            ("docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name),
            timeout_seconds,
        )
        if result.returncode != 0:
            return None
        match = _MEMORY_PATTERN.match(result.stdout)
        if match is None or match.group(2) not in _MEMORY_UNITS:
            return None
        return int(float(match.group(1)) * _MEMORY_UNITS[match.group(2)])

    # -- plan / removal ---------------------------------------------------------------

    def verify_present(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        installation = _installation(parameters)
        present = [
            {
                "container_name": container.name,
                "present": self._labels(container.name, timeout_seconds) is not None,
            }
            for container in installation.containers
        ]
        return {"containers": present, "present": all(item["present"] for item in present)}

    def rollback(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(parameters, timeout_seconds, operation="rollback", only=None)

    def destroy(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(parameters, timeout_seconds, operation="destroy", only=None)

    def compensate(
        self, parameters: dict[str, Any], created: tuple[str, ...], timeout_seconds: int
    ) -> dict[str, Any]:
        """Remove exactly the containers a failed apply created, and nothing else."""

        return self._remove(
            parameters, timeout_seconds, operation="compensation", only=frozenset(created)
        )

    def _remove(
        self,
        parameters: dict[str, Any],
        timeout_seconds: int,
        *,
        operation: str,
        only: frozenset[str] | None,
    ) -> dict[str, Any]:
        """Remove only containers this case owns, and prove each is gone afterwards."""

        installation = _installation(parameters)
        rows: list[dict[str, Any]] = []

        def evidence() -> dict[str, Any]:
            return {
                "category": "rollback_result",
                "operation": operation,
                "content": {
                    "removed_all": all(row["absent_after"] for row in rows),
                    "containers": rows,
                },
            }

        try:
            for container in reversed(installation.containers):
                if only is not None and container.name not in only:
                    continue
                labels = self._labels(container.name, timeout_seconds)
                if labels is not None:
                    self._require_owned(labels, installation, container)
                    removed = self._run(
                        ("docker", "rm", "--force", "--volumes", container.name),
                        timeout_seconds,
                    )
                    if removed.returncode != 0 and not _is_absent(removed):
                        raise OAKError(
                            "OAK-RUNNER-ROLLBACK", f"fixture container {operation} failed"
                        )
                absent_after = self._labels(container.name, timeout_seconds) is None
                rows.append(
                    {
                        "node_id": container.node_id,
                        "container_name": container.name,
                        "present_before": labels is not None,
                        "absent_after": absent_after,
                    }
                )
                if not absent_after:
                    raise OAKError(
                        "OAK-RUNNER-ROLLBACK",
                        f"a container is still present after {operation}",
                    )
        except OAKError as error:
            raise AdapterFailureError(error.code, error.message, evidence=(evidence(),)) from error
        return evidence()

    # -- shared -----------------------------------------------------------------------

    def _labels(self, name: str, timeout_seconds: int) -> dict[str, str] | None:
        """The container's labels, or None when no container has the name.

        Any other failure — a daemon that does not answer, unreadable output — is an
        error, never read as "absent": an unverifiable state must not become a create
        or a claim that something was removed.
        """

        result = self._run(
            ("docker", "inspect", "--type=container", "--format", "{{json .Config.Labels}}", name),
            timeout_seconds,
        )
        if result.returncode != 0:
            if _is_absent(result):
                return None
            raise OAKError("OAK-RUNNER-APPLY", "container state could not be read")
        try:
            parsed = json.loads(result.stdout)
        except ValueError as error:
            raise OAKError("OAK-RUNNER-APPLY", "container labels could not be read") from error
        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            raise OAKError("OAK-RUNNER-APPLY", "container labels could not be read")
        return {str(key): str(value) for key, value in parsed.items()}

    @staticmethod
    def _require_owned(
        labels: dict[str, str], installation: _Installation, container: _Container
    ) -> None:
        owned = (
            labels.get(CONTAINER_LABEL_FIXTURE) == "true"
            and labels.get(CONTAINER_LABEL_CASE) == installation.case_id
            and labels.get(CONTAINER_LABEL_NODE) == container.node_id
        )
        if not owned:
            raise OAKError(
                "OAK-RUNNER-FOREIGN",
                "a container this case does not own already has the planned name",
            )

    def _before_side_effect(self, deadline: datetime | None) -> None:
        # The runner does not heartbeat (RR-031): refusing to start another side effect
        # once the lease has lapsed keeps a long install from running on past it.
        if deadline is not None and self._wall_clock() >= deadline:
            raise OAKError("OAK-RUNNER-LEASE", "the lease expired before the next side effect")

    def _run(self, argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        if argv[0] not in ALLOWLISTED_EXECUTABLES:
            raise OAKError("OAK-RUNNER-EXECUTABLE", "executable is not allowlisted")
        # A hung daemon raises subprocess.TimeoutExpired and a broken one OSError;
        # neither is an OAKError, so before this guard they escaped execute_dispatch's
        # handler, skipped the operation's declared failure_action, and killed the
        # runner with a raw traceback instead of a stable `CODE: message`.
        try:
            return self._executor(argv, timeout_seconds)
        except OAKError:
            raise
        except (subprocess.TimeoutExpired, OSError) as error:
            raise OAKError(
                "OAK-RUNNER-SUBPROCESS",
                "docker invocation failed before completing",
            ) from error


def _is_absent(result: CommandResult) -> bool:
    return result.returncode != 0 and "No such" in result.stderr


def _installation(parameters: dict[str, Any]) -> _Installation:
    """Re-validate the parameter set the runner already schema-checked.

    The adapter does not trust that it was called only after verification: every value
    that reaches an argument vector is checked here again, and each container name must
    be the one derived from this case, target and node.
    """

    case_id = str(parameters.get("case_id", ""))
    target_id = str(parameters.get("target_id", ""))
    isolation = parameters.get("isolation")
    entries = parameters.get("containers")
    if _IDENTIFIER.fullmatch(case_id) is None or _IDENTIFIER.fullmatch(target_id) is None:
        raise OAKError("OAK-RUNNER-PARAMETERS", "installation identity is not permitted")
    if isolation not in {ISOLATION_NEVER_STARTED, ISOLATION_STARTED_HARDENED}:
        raise OAKError("OAK-RUNNER-PARAMETERS", "isolation is not permitted")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAXIMUM_CONTAINERS:
        raise OAKError("OAK-RUNNER-PARAMETERS", "container list is not permitted")
    containers: list[_Container] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise OAKError("OAK-RUNNER-PARAMETERS", "container entry is not permitted")
        node_id = str(entry.get("node_id", ""))
        manifest_id = str(entry.get("manifest_id", ""))
        name = str(entry.get("container_name", ""))
        reference = str(entry.get("image_reference", ""))
        digest = str(entry.get("image_digest", ""))
        if _IDENTIFIER.fullmatch(node_id) is None or _IDENTIFIER.fullmatch(manifest_id) is None:
            raise OAKError("OAK-RUNNER-PARAMETERS", "node identity is not permitted")
        if _NAME_PATTERN.fullmatch(name) is None:
            raise OAKError("OAK-RUNNER-PARAMETERS", "container name is not permitted")
        if name != container_name_for(case_id, target_id, node_id):
            raise OAKError(
                "OAK-RUNNER-PARAMETERS", "container name is not the one derived for this case"
            )
        # The approved digest is the only pin that may reach the runtime. A reference
        # that carries its own digest could otherwise smuggle a different image past
        # the approval, so it is refused outright.
        if "@" in reference:
            raise OAKError("OAK-RUNNER-PARAMETERS", "image reference must not carry its own digest")
        if _IMAGE_PATTERN.fullmatch(reference) is None or reference.startswith("-"):
            raise OAKError("OAK-RUNNER-PARAMETERS", "image reference is not permitted")
        if _DIGEST_PATTERN.fullmatch(digest) is None:
            raise OAKError("OAK-RUNNER-PARAMETERS", "image digest is not permitted")
        containers.append(
            _Container(
                node_id=node_id,
                manifest_id=manifest_id,
                name=name,
                digest=digest,
                image=f"{reference}@{digest}",
            )
        )
    if len({container.name for container in containers}) != len(containers) or len(
        {container.node_id for container in containers}
    ) != len(containers):
        raise OAKError("OAK-RUNNER-PARAMETERS", "container names and nodes must be unique")
    return _Installation(
        case_id=case_id,
        target_id=target_id,
        isolation=str(isolation),
        containers=tuple(containers),
    )
