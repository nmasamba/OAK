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
   ones the profile acknowledged. An archive is unpacked member by member: a link, an
   absolute path, a `..`, a device or more than the limits is refused.
3. It starts each component from its harness kind's fixed argument template, bound to
   127.0.0.1, with only `PATH`, `HOME` and `LANG` in its environment and its own process
   group; probes its health path; and **stops it**: nothing is left running and no unit
   file is written. The user starts it when they want it.

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
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from collections.abc import Callable
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
DOWNLOAD_TIMEOUT_SECONDS = 60.0
MAXIMUM_ARCHIVE_MEMBERS = 10_000
MAXIMUM_UNPACKED_BYTES = 64 * 2**30
LLAMA_SERVER = "llama-server"
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
        popen: Popen = subprocess.Popen,
        platform_key: tuple[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._root = root
        self._fetch = fetch
        self._probe = probe
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
                self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
                directory.mkdir(mode=0o700)
                created = True
                self._write_marker(directory, installation, state="installing")
            prepared: list[tuple[NativeComponent, Path, tuple[str, ...]]] = []
            for component in installation.components:
                beat()
                self._before(deadline)
                component_directory = directory / component.slug
                component_directory.mkdir(mode=0o700, exist_ok=True)
                files = {
                    artifact.role: self._obtain(
                        artifact, component_directory, installation.allowed_hosts
                    )
                    for artifact in component.artifacts
                }
                argv, working_directory = self._command(component, files)
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
            if not all(row["passed"] for row in tested):
                raise OAKError(
                    "OAK-NATIVE-SMOKE", "a native component did not answer its health probe"
                )
            self._write_marker(directory, installation, state="installed")
        except OAKError as error:
            raise AdapterFailureError(
                error.code,
                error.message,
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
        self, artifact: NativeArtifact, component_directory: Path, allowed: frozenset[str]
    ) -> Path:
        """The verified artifact on disk: the downloaded file, or its unpacked tree."""

        role_directory = component_directory / artifact.role
        role_directory.mkdir(mode=0o700, exist_ok=True)
        download = role_directory / "download"
        if download.is_symlink():
            raise OAKError("OAK-NATIVE-OWNERSHIP", "an artifact path is a link")
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
        if artifact.format == "file":
            return download
        unpacked = role_directory / "unpacked"
        if not unpacked.exists():
            staging = role_directory / "unpacking"
            if os.path.lexists(staging):
                shutil.rmtree(staging)
            staging.mkdir(mode=0o700)
            if artifact.format == "zip":
                _unpack_zip(download, staging)
            else:
                _unpack_tar(download, staging)
            staging.rename(unpacked)
        return unpacked

    @staticmethod
    def _command(
        component: NativeComponent, files: dict[str, Path]
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
            try:
                status, seconds = self._wait_ready(component, process, started, deadline)
            finally:
                exit_code = self._stop(process)
        return {
            "node_id": component.node_id,
            "passed": status == 200,
            "http_status": status,
            "seconds_to_ready": seconds,
            "stopped": True,
            "exit_code": exit_code,
            "resource_limits": {label: pair[0] for label, (_, pair) in limits.items()},
            "not_limited": list(NOT_LIMITED),
        }

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
                if process.poll() is None:
                    settled = self._probe(
                        component.listen_port, component.probe_path, PROBE_TIMEOUT_SECONDS
                    )
                    if settled == 200:
                        return settled, seconds
                    status = settled
                return status, None
            self._sleep(READINESS_POLL_SECONDS)
        return status, None

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> int | None:
        """Stop the whole process group the component started; never leave it running."""

        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(STOP_SECONDS)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(STOP_SECONDS)
        return process.returncode

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
        directory = self._root / installation_id
        removed = False
        if os.path.lexists(directory):
            self._require_owned(directory, installation_id)
            shutil.rmtree(directory)
            removed = True
        if os.path.lexists(directory):
            raise OAKError("OAK-NATIVE-UNINSTALL", "the installation directory is still there")
        return {
            "category": "rollback_result",
            "operation": operation,
            "content": {"installation_id": installation_id, "removed": removed, "absent": True},
        }


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


def _unpack_zip(archive: Path, base: Path) -> None:
    total = 0
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
            if mode not in (0, stat.S_IFREG):
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member is a link or a device")
            total += member.file_size
            if total > MAXIMUM_UNPACKED_BYTES:
                raise OAKError("OAK-NATIVE-ARCHIVE", "the archive unpacks to too many bytes")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, 0o600)


def _unpack_tar(archive: Path, base: Path) -> None:
    total = 0
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
            if not member.isreg():
                raise OAKError("OAK-NATIVE-ARCHIVE", "an archive member is a link or a device")
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
