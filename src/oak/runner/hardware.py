# SPDX-License-Identifier: Apache-2.0
"""The hardware scan: the one place OAK runs the tools that describe a machine.

The runner's ``inventory`` operation and the local ``oak scan`` command both call
``scan``. Each tool is an allowlisted executable (``ALLOWLISTED_EXECUTABLES`` in
``oak.runner.adapters``) resolved once from the absolute entries of ``PATH``, run with the
fixed argument vector below, a sanitized environment, a timeout and an output bound, and
never through a shell; nothing a document or a plan says reaches an argument. The output
is handed to the pure parsers in ``oak.domain.hardware``, which keep only the fields a
proposal may hold, so the raw output never leaves this function.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from oak.domain import OAKError
from oak.domain.hardware import (
    LINUX_TOOLS,
    MACOS_TOOLS,
    SYSCTL_NAMES,
    ToolOutcome,
    build_proposal,
    normalize_system,
)
from oak.runner.adapters import (
    MAXIMUM_OUTPUT_BYTES,
    CommandExecutor,
    default_executor,
    resolve_executable,
)

# One fixed argument vector per tool. Machine-readable output only: sysctl's values one
# per line, JSON from system_profiler, lscpu and rocm-smi, CSV from nvidia-smi.
TOOL_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "sysctl": ("sysctl", "-n", *SYSCTL_NAMES),
    # `mini` is system_profiler's level "with no personal information"; it still lists the
    # displays' serial numbers, which the parser never reads.
    "system_profiler": ("system_profiler", "-json", "-detailLevel", "mini", "SPDisplaysDataType"),
    "lscpu": ("lscpu", "-J"),
    "nvidia-smi": (
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ),
    "rocm-smi": ("rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"),
}
# system_profiler can take seconds on a machine with many devices.
TOOL_TIMEOUT_SECONDS = {"system_profiler": 30}
DEFAULT_TOOL_TIMEOUT_SECONDS = 10
DOCKER_VERSION_ARGUMENTS = ("docker", "version", "--format", "{{.Server.Version}}")
DOCKER_TIMEOUT_SECONDS = 10


def _memory_bytes() -> int | None:
    if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return pages * size if pages > 0 and size > 0 else None
    return None


def _storage_bytes() -> int | None:
    try:
        return shutil.disk_usage("/").total
    except OSError:
        return None


def run_tool(
    tool: str,
    *,
    executor: CommandExecutor,
    resolve: Callable[[str], str | None] = resolve_executable,
) -> ToolOutcome:
    """One tool's fate: absent, timed out, failed, too large, or ran with its output."""

    argv = TOOL_ARGUMENTS[tool]
    timeout = TOOL_TIMEOUT_SECONDS.get(tool, DEFAULT_TOOL_TIMEOUT_SECONDS)
    if resolve(argv[0]) is None:
        return ToolOutcome("absent")
    try:
        result = executor(argv, timeout)
    except subprocess.TimeoutExpired:
        return ToolOutcome("timed_out", timeout_seconds=timeout)
    except (OAKError, OSError):
        return ToolOutcome("absent")
    if result.returncode != 0:
        return ToolOutcome("failed", returncode=result.returncode)
    if len(result.stdout) >= MAXIMUM_OUTPUT_BYTES:
        return ToolOutcome("too_large")
    return ToolOutcome("ran", stdout=result.stdout, returncode=0)


def prerequisite_states(
    *,
    executor: CommandExecutor,
    resolve: Callable[[str], str | None] = resolve_executable,
) -> dict[str, str]:
    """Whether Docker (and its daemon) and uv are here. uv is looked up, never run."""

    states = {"uv": "present" if resolve("uv") is not None else "absent"}
    if resolve("docker") is None:
        states["docker"] = "absent"
        return states
    try:
        answered = executor(DOCKER_VERSION_ARGUMENTS, DOCKER_TIMEOUT_SECONDS).returncode == 0
    except (subprocess.TimeoutExpired, OAKError, OSError):
        answered = False
    states["docker"] = "present" if answered else "not_running"
    return states


def scan(
    *,
    executor: CommandExecutor = default_executor,
    resolve: Callable[[str], str | None] = resolve_executable,
    system: str | None = None,
    machine: str | None = None,
    memory_bytes: int | None = None,
    storage_bytes: int | None = None,
) -> dict[str, Any]:
    """Scan this machine and return the proposal; nothing is recorded anywhere."""

    system = system if system is not None else platform.system()
    machine = machine if machine is not None else platform.machine()
    tools = {"macos": MACOS_TOOLS, "linux": LINUX_TOOLS}.get(normalize_system(system) or "", ())
    outcomes = {tool: run_tool(tool, executor=executor, resolve=resolve) for tool in tools}
    return build_proposal(
        system=system,
        machine=machine,
        outcomes=outcomes,
        memory_bytes=memory_bytes if memory_bytes is not None else _memory_bytes(),
        storage_bytes=storage_bytes if storage_bytes is not None else _storage_bytes(),
        prerequisites=prerequisite_states(executor=executor, resolve=resolve),
    )
