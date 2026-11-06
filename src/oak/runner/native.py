# SPDX-License-Identifier: Apache-2.0
"""The native process adapter (ADR-0019): install each component as the user, prove it
answers, and stop it.

What a native install does, in order, for a plan the runner has already verified (its
signature, its approvals including the `native_consent`, and its parameters against this
runner's own target profile):

1. It creates the installation's directory under the runner's home, owner-only, and writes
   an ownership marker naming the installation; a directory it did not create and mark is
   never adopted, stopped or removed.
2. For each artifact it fetches the bytes over HTTPS from an acknowledged host (or copies
   the stand-in from inside OAK), and refuses them unless their size and SHA-256 are the
   ones the profile acknowledged. An archive is unpacked member by member: a link to a
   file inside it is written as a copy of that file, and a link that leaves it or names
   nothing in it, an absolute path, a `..`, a device or more than the limits is refused.
3. It starts each component from its harness kind's fixed argument template, bound to
   127.0.0.1, with only `PATH`, `HOME` and `LANG` in its environment and its own process
   group; probes its health path; and **stops it**: nothing is left running and no unit
   file is written. The user starts it when they want it.

A model server takes the installation's own API key, which the runner generates into a file
only the user can read and hands over by path, so the key is in no argument vector and no
record. The server's check also proves that it refuses a request without the key.

Uninstalling removes exactly the installation's directory, after checking its marker.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import re
import resource
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from oak.domain import OAKError
from oak.domain.runner_adapters import NATIVE_RELAXED_CONTROLS, STAND_IN_NAMES
from oak.domain.runner_adapters import harness_shape_problem as domain_harness_shape_problem
from oak.runner import native_network
from oak.runner.adapters import AdapterFailureError

MARKER = ".oak-installation.json"
# Written beside the marker once every component has passed its check: how the user starts
# each one, since the install leaves nothing running (the owner's Q4d answer).
START_FILE = "START.txt"
SUPPORTED_PLATFORMS = frozenset({("darwin", "arm64"), ("linux", "x86_64"), ("linux", "aarch64")})
# The file inside OAK for each stand-in name the domain admits.
STAND_IN_FILES = {"http-server": "http_server.py"}
assert frozenset(STAND_IN_FILES) == STAND_IN_NAMES
# How long a component has to answer its health path after it starts.
READINESS_SECONDS = {"oak_stand_in": 20.0, "llama_cpp_server": 240.0}
READINESS_POLL_SECONDS = 0.25
SETTLE_SECONDS = 0.5
PROBE_TIMEOUT_SECONDS = 2.0
STOP_SECONDS = 10.0
# How long the stop waits, after the group's SIGKILL, for its last member to be gone.
GONE_SECONDS = 2.0
DOWNLOAD_TIMEOUT_SECONDS = 60.0
MAXIMUM_ARCHIVE_MEMBERS = 10_000
MAXIMUM_UNPACKED_BYTES = 64 * 2**30
# A link inside a release archive (a library's versioned name, say) is unpacked as a copy of
# the file it names, never as a link; a chain of links longer than this is refused.
MAXIMUM_LINK_HOPS = 8
MAXIMUM_LINK_TARGET_BYTES = 4096
LLAMA_SERVER = "llama-server"
# The file in an installation that holds its API key: one key on one line, as
# `--api-key-file` reads it. A server is given the path, never the value, so the key is in no
# argument vector and no record, and the installation's folder is the only place it lives.
API_KEY_FILE = "api-key.txt"
API_KEY_BYTES = 32
API_KEY_LINE = re.compile(rb"[0-9a-f]{64}\n")
# Each harness kind that takes that key, and the path its check asks for without it: the one
# that generates text, by a GET that route does not take, so no model ever runs for the
# check. The server refuses before it routes, which proves the key is in force.
KEYED_PATHS = {"llama_cpp_server": "/v1/chat/completions"}
REFUSED_WITHOUT_KEY = 401
# The ceilings a component's check runs under, as far as this platform applies them
# (ADR-0019; the consent names `resource_ceilings` among what a native install relaxes):
# no core files, a bounded number of open files, and a bounded size for any file it writes.
# Each only ever lowers the runner's own limit. Memory, CPU time and the number of
# processes are deliberately not limited: macOS does not enforce an address-space limit, a
# CPU-time limit would stop a model server loading on many threads, and a process-count
# limit counts every process the user already runs. The evidence records both lists.
CHILD_LIMITS: tuple[tuple[str, str, int], ...] = (
    ("core_file_bytes", "RLIMIT_CORE", 0),
    ("open_files", "RLIMIT_NOFILE", 4096),
    ("file_bytes", "RLIMIT_FSIZE", 2 * 2**30),
)
NOT_LIMITED = ("memory", "cpu_time", "processes")

Popen = Callable[..., subprocess.Popen[bytes]]
Fetch = Callable[..., tuple[int, str]]
Probe = Callable[[int, str, float], int | None]
PortFree = Callable[[int], bool]


@dataclass(frozen=True, slots=True)
class NativeArtifact:
    role: str
    source: str
    sha256: str
    size_bytes: int
    format: str


@dataclass(frozen=True, slots=True)
class NativeComponent:
    node_id: str
    manifest_id: str
    harness_kind: str
    artifacts: tuple[NativeArtifact, ...]
    listen_port: int
    probe_path: str

    @property
    def slug(self) -> str:
        """A directory name for the node that cannot escape the installation."""

        readable = re.sub(r"[^a-z0-9]+", "-", self.node_id.casefold()).strip("-")[:40] or "node"
        identity = hashlib.sha256(self.node_id.encode("utf-8")).hexdigest()[:12]
        return f"{readable}-{identity}"

    def artifact(self, role: str) -> NativeArtifact:
        matches = [artifact for artifact in self.artifacts if artifact.role == role]
        if len(matches) != 1:
            raise OAKError(
                "OAK-NATIVE-HARNESS", f"{self.harness_kind} needs exactly one {role} artifact"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class NativeInstallation:
    installation_id: str
    case_id: str
    target_id: str
    allowed_hosts: frozenset[str]
    components: tuple[NativeComponent, ...]

    @classmethod
    def from_parameters(cls, parameters: dict[str, Any]) -> NativeInstallation:
        """The installation a schema-valid parameter document describes."""

        components = tuple(
            NativeComponent(
                node_id=str(entry["node_id"]),
                manifest_id=str(entry["manifest_id"]),
                harness_kind=str(entry["harness_kind"]),
                artifacts=tuple(
                    NativeArtifact(
                        role=str(item["role"]),
                        source=str(item["source"]),
                        sha256=str(item["sha256"]),
                        size_bytes=int(item["size_bytes"]),
                        format=str(item["format"]),
                    )
                    for item in entry["artifacts"]
                ),
                listen_port=int(entry["listen_port"]),
                probe_path=str(entry["health_probe"]["path"]),
            )
            for entry in parameters["components"]
        )
        return cls(
            installation_id=str(parameters["installation_id"]),
            case_id=str(parameters["case_id"]),
            target_id=str(parameters["target_id"]),
            allowed_hosts=frozenset(str(host) for host in parameters["allowed_download_hosts"]),
            components=components,
        )


def harness_shape_problem(component: NativeComponent) -> str | None:
    """The domain's harness-shape rule, applied to an installation's component."""

    return domain_harness_shape_problem(
        component.harness_kind,
        [
            {"role": item.role, "source": item.source, "format": item.format}
            for item in component.artifacts
        ],
    )


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def child_limits() -> dict[str, tuple[int, tuple[int, int]]]:
    """Each ceiling this platform can apply, by label: the limit and its (soft, hard) pair.

    Computed in the runner, so the evidence records exactly what the child is given; the
    child applies the pairs before it executes, and a pair it cannot apply fails the start.
    """

    planned: dict[str, tuple[int, tuple[int, int]]] = {}
    for label, name, ceiling in CHILD_LIMITS:
        which = getattr(resource, name, None)
        if not isinstance(which, int):
            continue
        soft, hard = resource.getrlimit(which)

        def lowered(current: int, ceiling: int = ceiling) -> int:
            return ceiling if current == resource.RLIM_INFINITY else min(ceiling, current)

        planned[label] = (which, (lowered(soft), lowered(hard)))
    return planned


class NativeProcessAdapter:
    """Installs, smoke-tests, stops and uninstalls native components under ``root``."""

    def __init__(
        self,
        root: Path,
        *,
        fetch: Fetch = native_network.fetch,
        probe: Probe = native_network.probe,
        port_free: PortFree = native_network.port_free,
        popen: Popen = subprocess.Popen,
        platform_key: tuple[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._root = root
        self._fetch = fetch
        self._probe = probe
        self._port_free = port_free
        self._popen = popen
        self._platform = platform_key or (platform.system().lower(), platform.machine().lower())
        self._sleep = sleep
        self._clock = clock

    # ----- install ------------------------------------------------------------------

    def apply(
        self,
        parameters: dict[str, Any],
        timeout_seconds: int,
        *,
        deadline: datetime | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Install every component, start each once to probe it, and stop it again.

        Returns the evidence items. Raises ``AdapterFailureError`` naming the installation
        when this call created its directory, so the caller removes exactly that.
        """

        installation = NativeInstallation.from_parameters(parameters)
        directory = self._root / installation.installation_id
        created = False
        installed: list[dict[str, Any]] = []
        tested: list[dict[str, Any]] = []
        started_file = False

        def evidence() -> tuple[dict[str, Any], ...]:
            items: list[dict[str, Any]] = [
                {
                    "category": "status",
                    "operation": "apply",
                    "content": {
                        "mode": "native",
                        "installation_id": installation.installation_id,
                        "relaxed_controls": list(NATIVE_RELAXED_CONTROLS),
                        "installation": installed,
                        "running": False,
                        "start_instructions": START_FILE if started_file else None,
                    },
                }
            ]
            if tested:
                complete = len(tested) == len(installation.components)
                items.append(
                    {
                        "category": "test_result",
                        "operation": "apply",
                        "content": {
                            "started": True,
                            "complete": complete,
                            "passed": complete and all(row["passed"] for row in tested),
                            "stopped": all(row["stopped"] for row in tested),
                            "smoke_test": tested,
                        },
                    }
                )
                ready = [
                    {"node_id": row["node_id"], "seconds_to_ready": row["seconds_to_ready"]}
                    for row in tested
                    if row["seconds_to_ready"] is not None
                ]
                if ready:
                    items.append(
                        {
                            "category": "aggregate_metric",
                            "operation": "apply",
                            "content": {"readiness": ready},
                        }
                    )
            return tuple(items)

        beat = heartbeat or (lambda: None)
        try:
            self._require_platform()
            for component in installation.components:
                problem = harness_shape_problem(component)
                if problem is not None:
                    raise OAKError("OAK-NATIVE-HARNESS", problem)
            if os.path.lexists(directory):
                self._require_owned(directory, installation.installation_id)
            else:
                # Built under a name of its own and renamed into place with its marker, so
                # the installation's path never exists without one.
                self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
                creating = self._root / f".{installation.installation_id}.creating"
                if os.path.lexists(creating):
                    _delete_tree(creating)
                creating.mkdir(mode=0o700)
                self._write_marker(creating, installation, state="installing")
                creating.rename(directory)
                created = True
            if any(component.harness_kind in KEYED_PATHS for component in installation.components):
                _ensure_api_key(directory)
            prepared: list[tuple[NativeComponent, Path, tuple[str, ...]]] = []
            verified: dict[str, Path] = {}
            for component in installation.components:
                beat()
                self._before(deadline)
                component_directory = directory / component.slug
                component_directory.mkdir(mode=0o700, exist_ok=True)
                files = {
                    artifact.role: self._obtain(
                        artifact,
                        component_directory,
                        installation.allowed_hosts,
                        deadline=deadline,
                        verified=verified,
                    )
                    for artifact in component.artifacts
                }
                argv, working_directory = self._command(component, files, directory / API_KEY_FILE)
                prepared.append((component, working_directory, argv))
                installed.append(
                    {
                        "node_id": component.node_id,
                        "manifest_id": component.manifest_id,
                        "harness_kind": component.harness_kind,
                        "listen_port": component.listen_port,
                        "artifacts": [
                            {
                                "role": artifact.role,
                                "sha256": artifact.sha256,
                                "size_bytes": artifact.size_bytes,
                                "verified": True,
                            }
                            for artifact in component.artifacts
                        ],
                    }
                )
            for component, working_directory, argv in prepared:
                beat()
                self._before(deadline)
                tested.append(
                    self._start_probe_stop(
                        component, argv, working_directory, directory / component.slug, deadline
                    )
                )
            if not all(row["stopped"] for row in tested):
                raise OAKError(
                    "OAK-NATIVE-STOP", "a process a native component started is still running"
                )
            if any(
                row.get("status_without_key") not in (None, REFUSED_WITHOUT_KEY) for row in tested
            ):
                raise OAKError(
                    "OAK-NATIVE-KEY", "a model server answered a request that carried no key"
                )
            if not all(row["passed"] for row in tested):
                raise OAKError(
                    "OAK-NATIVE-SMOKE", "a native component did not answer its health probe"
                )
            _write_start_instructions(directory, prepared)
            started_file = True
            self._write_marker(directory, installation, state="installed")
        except OAKError as error:
            raise AdapterFailureError(
                error.code,
                error.message,
                created=(installation.installation_id,) if created else (),
                evidence=evidence(),
            ) from error
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            # Never a traceback with the user's paths, and never without compensation.
            raise AdapterFailureError(
                "OAK-NATIVE-IO",
                "a file of the installation could not be written or read",
                created=(installation.installation_id,) if created else (),
                evidence=evidence(),
            ) from error
        return evidence()

    def _require_platform(self) -> None:
        if self._platform not in SUPPORTED_PLATFORMS:
            raise OAKError(
                "OAK-NATIVE-PLATFORM",
                "native installation runs on macOS on Apple silicon and on Linux x86_64 and "
                "aarch64",
            )

    @staticmethod
    def _before(deadline: datetime | None) -> None:
        if deadline is not None and datetime.now(deadline.tzinfo) >= deadline:
            raise OAKError("OAK-RUNNER-LEASE-EXPIRED", "the lease expired before the next step")

    def _obtain(
        self,
        artifact: NativeArtifact,
        component_directory: Path,
        allowed: frozenset[str],
        *,
        deadline: datetime | None = None,
        verified: dict[str, Path] | None = None,
    ) -> Path:
        """The verified artifact on disk: the downloaded file, or its unpacked tree.

        A file another component of this installation already verified is linked rather than
        downloaded again. An archive is unpacked afresh from its verified bytes every time,
        so what runs is never a tree left from before.
        """

        role_directory = component_directory / artifact.role
        role_directory.mkdir(mode=0o700, exist_ok=True)
        download = role_directory / "download"
        if download.is_symlink():
            raise OAKError("OAK-NATIVE-OWNERSHIP", "an artifact path is a link")
        known = (verified or {}).get(artifact.sha256)
        if not download.exists() and known is not None:
            try:
                os.link(known, download)
            except OSError:
                shutil.copyfile(known, download)
        if download.exists():
            size, digest = _file_digest(download)
        elif artifact.source.startswith("oak-stand-in:"):
            name = STAND_IN_FILES.get(artifact.source.removeprefix("oak-stand-in:"))
            if name is None:
                raise OAKError("OAK-NATIVE-HARNESS", "the stand-in names no file OAK ships")
            content = resources.files("oak.runner.stand_in").joinpath(name).read_bytes()
            with download.open("xb") as output:
                output.write(content)
            size, digest = len(content), "sha256:" + hashlib.sha256(content).hexdigest()
        else:
            try:
                size, digest = self._fetch(
                    artifact.source,
                    download,
                    allowed_hosts=allowed,
                    expected_size=artifact.size_bytes,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                    deadline=deadline,
                )
            except OAKError:
                download.unlink(missing_ok=True)
                raise
        if size != artifact.size_bytes or digest != artifact.sha256:
            download.unlink(missing_ok=True)
            raise OAKError(
                "OAK-NATIVE-DIGEST",
                "an artifact's size or SHA-256 differs from what the target profile acknowledges",
            )
        os.chmod(download, 0o600)
        if verified is not None:
            verified[artifact.sha256] = download
        if artifact.format == "file":
            return download
        unpacked = role_directory / "unpacked"
        staging = role_directory / "unpacking"
        if os.path.lexists(staging):
            _delete_tree(staging)
        staging.mkdir(mode=0o700)
        try:
            if artifact.format == "zip":
                _unpack_zip(download, staging)
            else:
                _unpack_tar(download, staging)
        except (OSError, EOFError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
            raise OAKError("OAK-NATIVE-ARCHIVE", "the archive could not be unpacked") from error
        if os.path.lexists(unpacked):
            _delete_tree(unpacked)
        staging.rename(unpacked)
        return unpacked

    @staticmethod
    def _command(
        component: NativeComponent, files: dict[str, Path], key_file: Path
    ) -> tuple[tuple[str, ...], Path]:
        """The harness kind's argument template, filled from typed values only."""

        port = str(component.listen_port)
        if component.harness_kind == "oak_stand_in":
            script = files["harness"]
            return (sys.executable, "-I", "-B", str(script), "--port", port), script.parent
        if component.harness_kind == "llama_cpp_server":
            executable = _single_executable(files["harness"], LLAMA_SERVER)
            return (
                str(executable),
                "--host",
                "127.0.0.1",
                "--port",
                port,
                "--model",
                str(files["model"]),
                "--api-key-file",
                str(key_file),
            ), executable.parent
        raise OAKError("OAK-NATIVE-HARNESS", "the harness kind has no argument template")

    def _start_probe_stop(
        self,
        component: NativeComponent,
        argv: tuple[str, ...],
        working_directory: Path,
        component_directory: Path,
        deadline: datetime | None,
    ) -> dict[str, Any]:
        log_path = component_directory / "run.log"
        environment = {
            "PATH": os.defpath,
            "HOME": str(component_directory),
            "LANG": "C.UTF-8",
        }
        if not self._port_free(component.listen_port):
            # Another listener would answer the probe in the component's place.
            raise OAKError(
                "OAK-NATIVE-START",
                f"port {component.listen_port} on 127.0.0.1 is already in use",
            )
        limits = child_limits()

        def apply_limits() -> None:
            # Runs in the child between fork and exec; the runner starts no threads.
            for which, pair in limits.values():
                resource.setrlimit(which, pair)

        started = self._clock()
        with log_path.open("ab") as log:
            os.chmod(log_path, 0o600)
            try:
                process = self._popen(
                    list(argv),
                    cwd=working_directory,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                    shell=False,
                    preexec_fn=apply_limits,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise OAKError(
                    "OAK-NATIVE-START", f"{component.node_id} could not be started"
                ) from error
            keyed_path = KEYED_PATHS.get(component.harness_kind)
            without_key: int | None = None
            try:
                with _stop_on_signal():
                    status, seconds = self._wait_ready(component, process, started, deadline)
                    if keyed_path is not None and status == 200:
                        without_key = self._probe(
                            component.listen_port, keyed_path, PROBE_TIMEOUT_SECONDS
                        )
            finally:
                exit_code, stopped = _stop(process)
        row: dict[str, Any] = {
            "node_id": component.node_id,
            "passed": status == 200 and (keyed_path is None or without_key == REFUSED_WITHOUT_KEY),
            "http_status": status,
            "seconds_to_ready": seconds,
            "stopped": stopped,
            "exit_code": exit_code,
            "resource_limits": {label: pair[0] for label, (_, pair) in limits.items()},
            "not_limited": list(NOT_LIMITED),
        }
        if keyed_path is not None:
            row["status_without_key"] = without_key
        return row

    def _wait_ready(
        self,
        component: NativeComponent,
        process: subprocess.Popen[bytes],
        started: float,
        deadline: datetime | None,
    ) -> tuple[int | None, float | None]:
        budget = READINESS_SECONDS[component.harness_kind]
        status: int | None = None
        while self._clock() - started < budget:
            if process.poll() is not None:
                return status, None
            if deadline is not None and datetime.now(deadline.tzinfo) >= deadline:
                return status, None
            status = self._probe(component.listen_port, component.probe_path, PROBE_TIMEOUT_SECONDS)
            if status == 200:
                seconds = round(self._clock() - started, 3)
                self._sleep(SETTLE_SECONDS)
                settled = (
                    self._probe(component.listen_port, component.probe_path, PROBE_TIMEOUT_SECONDS)
                    if process.poll() is None
                    else None
                )
                # Only the component itself, still running after answering twice, passes: a
                # process that died, or another listener on its port, never does.
                if settled == 200 and process.poll() is None:
                    return settled, seconds
                return (None if settled == 200 else settled), None
            self._sleep(READINESS_POLL_SECONDS)
        return status, None

    # ----- ownership ----------------------------------------------------------------

    @staticmethod
    def _write_marker(directory: Path, installation: NativeInstallation, *, state: str) -> None:
        marker = directory / MARKER
        document = {
            "installation_id": installation.installation_id,
            "case_id": installation.case_id,
            "target_id": installation.target_id,
            "state": state,
            "updated_at": _now(),
            "components": [component.node_id for component in installation.components],
        }
        temporary = directory / f"{MARKER}.tmp"
        temporary.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(marker)

    @staticmethod
    def _require_owned(directory: Path, installation_id: str) -> None:
        """Refuse a directory this runner did not create and mark for this installation."""

        details = os.lstat(directory)
        if not stat.S_ISDIR(details.st_mode):
            raise OAKError("OAK-NATIVE-OWNERSHIP", "the installation path is not a directory")
        marker = directory / MARKER
        try:
            marker_details = os.lstat(marker)
            if not stat.S_ISREG(marker_details.st_mode):
                raise OAKError("OAK-NATIVE-OWNERSHIP", "the ownership marker is not a file")
            document = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise OAKError(
                "OAK-NATIVE-OWNERSHIP", "the installation directory carries no ownership marker"
            ) from error
        if not isinstance(document, dict) or document.get("installation_id") != installation_id:
            raise OAKError(
                "OAK-NATIVE-OWNERSHIP", "the installation directory belongs to another installation"
            )

    # ----- uninstall ----------------------------------------------------------------

    def verify_present(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        directory = self._root / str(parameters["installation_id"])
        present = os.path.lexists(directory)
        return {"installation_id": str(parameters["installation_id"]), "present": present}

    def rollback(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(str(parameters["installation_id"]), operation="rollback")

    def destroy(self, parameters: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        return self._remove(str(parameters["installation_id"]), operation="destroy")

    def compensate(
        self, parameters: dict[str, Any], created: tuple[str, ...], timeout_seconds: int
    ) -> dict[str, Any]:
        """Remove the installation only when the failed apply created it."""

        installation_id = str(parameters["installation_id"])
        if installation_id not in created:
            return {
                "category": "rollback_result",
                "operation": "compensation",
                "content": {"installation_id": installation_id, "removed": False, "kept": True},
            }
        return self._remove(installation_id, operation="compensation")

    def _remove(self, installation_id: str, *, operation: str) -> dict[str, Any]:
        """Remove exactly the installation, after checking its marker.

        The directory is renamed out of the way first, so a removal that fails part-way
        leaves the installation's path absent and a leftover a later removal finishes,
        never a directory without its marker.
        """

        directory = self._root / installation_id
        leftovers = (
            self._root / f".{installation_id}.removing",
            self._root / f".{installation_id}.creating",
        )
        removed = False
        try:
            if os.path.lexists(directory):
                self._require_owned(directory, installation_id)
                if os.path.lexists(leftovers[0]):
                    _delete_tree(leftovers[0])
                directory.rename(leftovers[0])
                removed = True
            for leftover in leftovers:
                if os.path.lexists(leftover):
                    _delete_tree(leftover)
        except OSError as error:
            raise OAKError(
                "OAK-NATIVE-UNINSTALL", "the installation could not be removed"
            ) from error
        if os.path.lexists(directory):
            raise OAKError("OAK-NATIVE-UNINSTALL", "the installation directory is still there")
        return {
            "category": "rollback_result",
            "operation": operation,
            "content": {"installation_id": installation_id, "removed": removed, "absent": True},
        }


def _ensure_api_key(directory: Path) -> None:
    """Keep the key a past install wrote, or write a new one. Nothing here returns it.

    A key someone else could have read is no longer a secret, and a file holding anything
    but the line OAK writes may leave a server with no key at all: `--api-key-file` skips
    empty lines and comments, and a server with no keys asks for none. Either is removed. A
    new key is written aside and renamed into place, so a write that fails leaves no file,
    which the server refuses to start without, and never an empty one.
    """

    path = directory / API_KEY_FILE
    if os.path.lexists(path):
        details = os.lstat(path)
        if not stat.S_ISREG(details.st_mode):
            raise OAKError("OAK-NATIVE-OWNERSHIP", "the installation's key file is not a file")
        # Its owner can read it and nobody else can, however the owner set that.
        if stat.S_IMODE(details.st_mode) & 0o477 == 0o400:
            with path.open("rb") as held:
                if API_KEY_LINE.fullmatch(held.read(2 * API_KEY_BYTES + 2)):
                    return
        path.unlink()
    temporary = directory / f"{API_KEY_FILE}.tmp"
    temporary.unlink(missing_ok=True)
    # Created owner-only and exclusively, so it is never readable by anyone else, and never
    # written through a link.
    created = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(created, "w", encoding="ascii") as output:
        output.write(secrets.token_hex(API_KEY_BYTES) + "\n")
    temporary.replace(path)


def _delete_tree(path: Path) -> None:
    """Delete a directory the runner made, refusing a link in its place."""

    if os.path.islink(path) or not os.path.isdir(path):
        raise OAKError("OAK-NATIVE-OWNERSHIP", "a path the runner made is not its directory")
    shutil.rmtree(path)


@contextlib.contextmanager
def _stop_on_signal() -> Iterator[None]:
    """While a component runs, SIGTERM or SIGHUP to the runner still stops it.

    Python's default for both ends the process without running `finally`, which would
    leave the component running; this turns them into an exit that unwinds through the
    stop. Only the main thread can install handlers, and the runner has no other.
    """

    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def interrupted(signum: int, frame: Any) -> None:
        raise SystemExit(128 + signum)

    previous = {
        number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGHUP)
    }
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _stop(process: subprocess.Popen[bytes]) -> tuple[int | None, bool]:
    """Stop the component's whole process group, and say whether any of it is left.

    The group is signalled whether or not its first process is still alive: a child it
    started stays in the group after it exits, and a child that ignores SIGTERM is killed.

    macOS answers EPERM, not ESRCH, for a group whose remaining members are all zombies
    waiting for their new parent to reap them, so EPERM is neither a failure to signal nor
    proof that something runs: the stop waits for the group to be gone either way.
    """

    group = process.pid
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(STOP_SECONDS)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(STOP_SECONDS)
    give_up = time.monotonic() + GONE_SECONDS
    while True:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return process.returncode, True
        except PermissionError:
            pass
        if time.monotonic() >= give_up:
            return process.returncode, False
        time.sleep(0.05)


def _write_start_instructions(
    directory: Path, prepared: list[tuple[NativeComponent, Path, tuple[str, ...]]]
) -> None:
    """How to start each installed component by hand: the same command the check ran.

    A file in the installation, never a record: its paths name the user's home. It says
    where the key is and how a client sends it, and does not hold the key itself.
    """

    key_file = shlex.quote(str(directory / API_KEY_FILE))
    lines = [
        "Nothing from this installation is running. OAK started each program once to check",
        "that it answers on this computer, then stopped it. To start one yourself, run its",
        "commands in a terminal, and stop it with Ctrl-C. While one runs, other programs on",
        "this computer can reach its port, and so can a web page open in your browser, so",
        "stop it when you are done. Removing the installation (oak approve destroy, then oak",
        "dispatch destroy) deletes this folder.",
    ]
    if any(component.harness_kind in KEYED_PATHS for component, _, _ in prepared):
        lines += [
            "",
            "A model server here runs its model only for a client that sends this",
            "installation's key. Without the key, a program or a web page can tell a server",
            "is there but cannot use it. The key is in this file, which only your user",
            "account can read, though any program you run can read it too:",
            f"  {key_file}",
        ]
    for component, working_directory, argv in prepared:
        origin = f"http://127.0.0.1:{component.listen_port}"
        lines += [
            "",
            f"{component.node_id} ({component.harness_kind}) on 127.0.0.1:"
            f"{component.listen_port}, health {component.probe_path}",
            f"  cd {shlex.quote(str(working_directory))}",
            f"  {shlex.join(argv)}",
        ]
        if component.harness_kind in KEYED_PATHS:
            lines += [
                "  A client sends the key in its Authorization header. This one hands it to curl",
                "  on its input, not on its command line, where other users could see it:",
                f"""  sed 's/.*/header = "Authorization: Bearer &"/' {key_file} |""",
                f"    curl --noproxy '*' -K - {origin}/v1/models",
                f"  The server's own web page, {origin}/, asks for it: choose Enter API Key.",
            ]
    path = directory / START_FILE
    temporary = directory / f"{START_FILE}.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, "sha256:" + digest.hexdigest()


def _member_path(base: Path, name: str) -> Path:
    """Where an archive member goes; refuses anything that would leave ``base``."""

    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or "\\" in name:
        raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member leaves its directory")
    return base.joinpath(*pure.parts)


def _archive_name(name: str) -> str:
    """A member's name inside its archive, normalized (`./` dropped)."""

    return "/".join(PurePosixPath(name).parts)


def _link_target(name: str, linkname: str, *, hard: bool) -> str:
    """The member a link names, normalized inside the archive; refuses one that leaves it.

    A symbolic link is read from its own directory, a hard link from the archive's root.
    """

    if not linkname or linkname.startswith("/") or "\\" in linkname:
        raise OAKError("OAK-NATIVE-ARCHIVE", "an archive link leaves its directory")
    parts = [] if hard else list(PurePosixPath(_archive_name(name)).parent.parts)
    for part in PurePosixPath(linkname).parts:
        if part == "..":
            if not parts:
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive link leaves its directory")
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    if not parts:
        raise OAKError("OAK-NATIVE-ARCHIVE", "an archive link leaves its directory")
    return "/".join(parts)


def _copy_links(links: dict[str, str], written: dict[str, Path], base: Path, total: int) -> None:
    """Each link as a copy of the regular file it names, once every file is unpacked.

    Nothing on disk is ever a link, so no later member can be written through one.
    """

    for name, target in links.items():
        final = target
        hops = 0
        while final in links:
            hops += 1
            if hops > MAXIMUM_LINK_HOPS:
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive link chain is too long")
            final = links[final]
        source = written.get(final)
        if source is None:
            raise OAKError(
                "OAK-NATIVE-ARCHIVE", "an archive link names nothing the archive holds as a file"
            )
        total += source.stat().st_size
        if total > MAXIMUM_UNPACKED_BYTES:
            raise OAKError("OAK-NATIVE-ARCHIVE", "the archive unpacks to too many bytes")
        destination = _member_path(base, name)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with source.open("rb") as reader, destination.open("xb") as output:
            shutil.copyfileobj(reader, output)
        os.chmod(destination, 0o600)


def _unpack_zip(archive: Path, base: Path) -> None:
    total = 0
    written: dict[str, Path] = {}
    links: dict[str, str] = {}
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAXIMUM_ARCHIVE_MEMBERS:
            raise OAKError("OAK-NATIVE-ARCHIVE", "the archive holds too many members")
        for member in members:
            mode = (member.external_attr >> 16) & 0o170000
            target = _member_path(base, member.filename)
            if member.is_dir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if mode == stat.S_IFLNK:
                if member.file_size > MAXIMUM_LINK_TARGET_BYTES:
                    raise OAKError("OAK-NATIVE-ARCHIVE", "an archive link is too long")
                linkname = bundle.read(member).decode("utf-8", errors="strict")
                links[_archive_name(member.filename)] = _link_target(
                    member.filename, linkname, hard=False
                )
                continue
            if mode not in (0, stat.S_IFREG):
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member is a device or a pipe")
            total += member.file_size
            if total > MAXIMUM_UNPACKED_BYTES:
                raise OAKError("OAK-NATIVE-ARCHIVE", "the archive unpacks to too many bytes")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, 0o600)
            written[_archive_name(member.filename)] = target
    _copy_links(links, written, base, total)


def _unpack_tar(archive: Path, base: Path) -> None:
    total = 0
    written: dict[str, Path] = {}
    links: dict[str, str] = {}
    with tarfile.open(archive, mode="r:gz") as bundle:
        count = 0
        for member in bundle:
            count += 1
            if count > MAXIMUM_ARCHIVE_MEMBERS:
                raise OAKError("OAK-NATIVE-ARCHIVE", "the archive holds too many members")
            target = _member_path(base, member.name)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if member.issym() or member.islnk():
                links[_archive_name(member.name)] = _link_target(
                    member.name, member.linkname, hard=member.islnk()
                )
                continue
            if not member.isreg():
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member is a device or a pipe")
            total += member.size
            if total > MAXIMUM_UNPACKED_BYTES:
                raise OAKError("OAK-NATIVE-ARCHIVE", "the archive unpacks to too many bytes")
            source = bundle.extractfile(member)
            if source is None:
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member could not be read")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, 0o600)
            written[_archive_name(member.name)] = target
    _copy_links(links, written, base, total)


def _single_executable(tree: Path, name: str) -> Path:
    """The one regular file named ``name`` in an unpacked release, made owner-executable."""

    matches = [
        path
        for path in tree.rglob(name)
        if not path.is_symlink() and path.is_file() and path.name == name
    ]
    if len(matches) != 1:
        raise OAKError(
            "OAK-NATIVE-HARNESS", f"the release holds {len(matches)} files named {name}, not one"
        )
    os.chmod(matches[0], 0o700)
    return matches[0]
