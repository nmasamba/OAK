# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-039: the hardware scan reads fixed tools, keeps allowlisted fields, never guesses."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from oak.domain import OAKError
from oak.domain.hardware import (
    ToolOutcome,
    bounded_model,
    build_proposal,
    intent_hardware,
    parse_lscpu,
    parse_nvidia_smi,
    parse_rocm_smi,
    parse_sysctl,
    parse_system_profiler,
    recommendations,
)
from oak.runner import hardware
from oak.runner.adapters import ALLOWLISTED_EXECUTABLES, MAXIMUM_OUTPUT_BYTES, CommandResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hardware"
IDENTIFIERS = ("SERIALFIXTURE", "GUIDFIXTURE", "UNIQUEFIXTURE")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _assert_no_identifier(document: Any) -> None:
    text = json.dumps(document)
    for marker in IDENTIFIERS:
        assert marker not in text, marker


# ----- the parsers ---------------------------------------------------------------------


def test_sysctl_gives_memory_cores_and_model() -> None:
    assert parse_sysctl(_fixture("macos-arm64/sysctl.txt")) == {
        "ram_gib": 64.0,
        "physical_cores": 10,
        "logical_cores": 10,
        "cpu_model": "Apple M1 Max",
    }
    assert parse_sysctl("68719476736\n10\n") == {}, "a missing value is not read positionally"


def test_system_profiler_reads_the_gpu_and_never_a_display() -> None:
    gpus = parse_system_profiler(_fixture("macos-arm64/system_profiler.json"))
    assert gpus == [
        {
            "vendor": "apple",
            "model": "Apple M1 Max",
            "memory_gib": None,
            "unified_memory": True,
            "runtime": "metal",
            "driver_version": None,
        }
    ]
    assert "SERIALFIXTURE01" in _fixture("macos-arm64/system_profiler.json")
    _assert_no_identifier(gpus)


def test_lscpu_flat_and_nested_layouts() -> None:
    assert parse_lscpu(_fixture("linux-arm64/lscpu.json")) == {
        "architecture": "arm64",
        "cpu_model": None,
        "logical_cores": 10,
        "physical_cores": 10,
    }
    assert parse_lscpu(_fixture("linux-x86_64/lscpu.json")) == {
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 7763 64-Core Processor",
        "logical_cores": 4,
        "physical_cores": 2,
    }


def test_nvidia_smi_reads_each_gpu() -> None:
    gpus = parse_nvidia_smi(_fixture("nvidia/nvidia-smi.csv"))
    assert [(gpu["model"], gpu["memory_gib"], gpu["driver_version"]) for gpu in gpus] == [
        ("NVIDIA GeForce RTX 4090", 24.0, "550.54.15"),
        ("NVIDIA RTX A2000 12GB", 12.0, "550.54.15"),
    ]
    assert {gpu["runtime"] for gpu in gpus} == {"cuda"}
    with pytest.raises(ValueError):
        parse_nvidia_smi("NVIDIA GeForce RTX 4090, 24564\n")


def test_rocm_smi_reads_each_card_and_never_its_identifiers() -> None:
    gpus = parse_rocm_smi(_fixture("amd/rocm-smi.json"))
    assert gpus == [
        {
            "vendor": "amd",
            "model": "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]",
            "memory_gib": 24.0,
            "unified_memory": False,
            "runtime": "rocm",
            "driver_version": None,
        }
    ]
    _assert_no_identifier(gpus)


@pytest.mark.parametrize(
    ("printed", "kept"),
    [
        ("Apple M1 Max", "Apple M1 Max"),
        ("  Intel(R)   Core(TM) i7-1185G7 @ 3.00GHz ", "Intel(R) Core(TM) i7-1185G7 @ 3.00GHz"),
        ("a\x1b[31mred\x1b[0m model", None),
        ("x" * 81, None),
        ("-", None),
        ("", None),
        ("名前", None),
        (42, None),
    ],
)
def test_a_model_name_is_kept_only_as_short_plain_text(printed: Any, kept: str | None) -> None:
    assert bounded_model(printed) == kept


# ----- the scanner, with a fake executor ------------------------------------------------


class _Machine:
    """Answers the fixed argument vectors with fixture output; records every call."""

    def __init__(self, answers: dict[str, Any], installed: set[str]) -> None:
        self.answers = answers
        self.installed = installed
        self.calls: list[tuple[str, ...]] = []

    def resolve(self, name: str) -> str | None:
        return f"/usr/bin/{name}" if name in self.installed else None

    def execute(self, argv: tuple[str, ...], timeout: int) -> CommandResult:
        self.calls.append(argv)
        answer = self.answers.get(argv[0], CommandResult(0, "", ""))
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _scan(machine: _Machine, system: str, architecture: str) -> dict[str, Any]:
    return hardware.scan(
        executor=machine.execute,
        resolve=machine.resolve,
        system=system,
        machine=architecture,
        memory_bytes=32 * 2**30,
        storage_bytes=500 * 2**30,
    )


def test_an_apple_silicon_scan_reports_unified_memory_and_metal() -> None:
    machine = _Machine(
        {
            "sysctl": CommandResult(0, _fixture("macos-arm64/sysctl.txt"), ""),
            "system_profiler": CommandResult(0, _fixture("macos-arm64/system_profiler.json"), ""),
            "docker": CommandResult(0, "28.5.1\n", ""),
        },
        {"sysctl", "system_profiler", "docker", "uv"},
    )
    proposal = _scan(machine, "Darwin", "arm64")

    assert proposal["platform"] == {"operating_system": "macos", "architecture": "arm64"}
    assert proposal["memory"] == {"ram_gib": 64.0, "unified": True}
    assert proposal["unknown"] == []
    assert [tool["status"] for tool in proposal["tools"]] == ["ran", "ran"]
    assert proposal["prerequisites"] == [
        {"name": "docker", "state": "present"},
        {"name": "uv", "state": "present"},
    ]
    assert machine.calls == [
        hardware.TOOL_ARGUMENTS["sysctl"],
        hardware.TOOL_ARGUMENTS["system_profiler"],
        hardware.DOCKER_VERSION_ARGUMENTS,
    ], "only the fixed argument vectors, and uv is never run"
    assert intent_hardware(proposal) == {
        "cpu_architectures": ["arm64"],
        "ram_gib": 64.0,
        "storage_gib": 500.0,
        "accelerators": ["apple-metal"],
    }, "no vram_gib is invented for unified memory"
    _assert_no_identifier(proposal)


def test_a_linux_machine_without_gpu_tools_says_its_gpus_are_unknown() -> None:
    machine = _Machine(
        {"lscpu": CommandResult(0, _fixture("linux-x86_64/lscpu.json"), "")}, {"lscpu"}
    )
    proposal = _scan(machine, "Linux", "x86_64")

    assert proposal["accelerators"] is None
    assert proposal["unknown"] == [
        {"field": "accelerators.nvidia", "reason": "nvidia-smi is not installed"},
        {"field": "accelerators.amd", "reason": "rocm-smi is not installed"},
    ]
    assert proposal["memory"] == {"ram_gib": 32.0, "unified": False}
    assert "accelerators" not in intent_hardware(proposal), "unknown is not declared none"
    assert machine.calls == [hardware.TOOL_ARGUMENTS["lscpu"]]
    assert recommendations(proposal) == [
        "Docker is not installed. OAK's container installation needs it (the native "
        "installation does not): https://docs.docker.com/get-started/get-docker/",
        "uv is not installed. It installs OAK and the Python tools a design may need: "
        "https://docs.astral.sh/uv/getting-started/installation/",
    ]


def test_nvidia_gpus_are_listed_and_the_missing_vendor_stays_unknown() -> None:
    machine = _Machine(
        {
            "lscpu": CommandResult(0, _fixture("linux-x86_64/lscpu.json"), ""),
            "nvidia-smi": CommandResult(0, _fixture("nvidia/nvidia-smi.csv"), ""),
        },
        {"lscpu", "nvidia-smi"},
    )
    proposal = _scan(machine, "Linux", "x86_64")

    assert [gpu["model"] for gpu in proposal["accelerators"]] == [
        "NVIDIA GeForce RTX 4090",
        "NVIDIA RTX A2000 12GB",
    ]
    assert proposal["unknown"] == [
        {"field": "accelerators.amd", "reason": "rocm-smi is not installed"}
    ]
    assert intent_hardware(proposal) == {
        "cpu_architectures": ["x86_64"],
        "ram_gib": 32.0,
        "storage_gib": 500.0,
        "accelerators": ["nvidia-cuda"],
        "vram_gib": 24.0,
        "drivers": ["nvidia-driver-550.54.15"],
    }


def test_no_gpu_is_claimed_only_when_both_vendors_answered() -> None:
    both = _Machine(
        {
            "lscpu": CommandResult(0, _fixture("linux-arm64/lscpu.json"), ""),
            "nvidia-smi": CommandResult(6, "", "No devices were found"),
            "rocm-smi": CommandResult(0, "{}", ""),
        },
        {"lscpu", "nvidia-smi", "rocm-smi"},
    )
    assert _scan(both, "Linux", "aarch64")["accelerators"] == []
    assert intent_hardware(_scan(both, "Linux", "aarch64"))["accelerators"] == []

    one = _Machine(
        {
            "lscpu": CommandResult(0, _fixture("linux-arm64/lscpu.json"), ""),
            "nvidia-smi": CommandResult(6, "", "No devices were found"),
        },
        {"lscpu", "nvidia-smi"},
    )
    assert _scan(one, "Linux", "aarch64")["accelerators"] is None


def test_an_amd_gpu_is_read_without_its_identifiers() -> None:
    machine = _Machine(
        {
            "lscpu": CommandResult(0, _fixture("linux-x86_64/lscpu.json"), ""),
            "nvidia-smi": CommandResult(9, "", "NVIDIA driver is not loaded"),
            "rocm-smi": CommandResult(0, _fixture("amd/rocm-smi.json"), ""),
        },
        {"lscpu", "nvidia-smi", "rocm-smi"},
    )
    proposal = _scan(machine, "Linux", "x86_64")

    assert [gpu["vendor"] for gpu in proposal["accelerators"]] == ["amd"]
    assert proposal["unknown"] == [
        {"field": "accelerators.nvidia", "reason": "nvidia-smi exited 9"}
    ]
    assert intent_hardware(proposal)["accelerators"] == ["amd-rocm"]
    _assert_no_identifier(proposal)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (subprocess.TimeoutExpired(("lscpu",), 10), "lscpu did not finish within 10 s"),
        (
            CommandResult(0, "x" * MAXIMUM_OUTPUT_BYTES, ""),
            "lscpu printed more than the scanner reads",
        ),
        (CommandResult(1, "", "boom"), "lscpu exited 1"),
        (CommandResult(0, "{not json", ""), "lscpu printed output the scanner could not read"),
        (
            OAKError("OAK-RUNNER-EXECUTABLE", "lscpu is not installed on this host"),
            "lscpu is not installed",
        ),
    ],
)
def test_a_tool_that_cannot_be_read_is_an_unknown_with_its_reason(answer: Any, reason: str) -> None:
    machine = _Machine({"lscpu": answer}, {"lscpu"})
    proposal = _scan(machine, "Linux", "x86_64")

    assert {"field": "cpu", "reason": reason} in proposal["unknown"]
    assert proposal["cpu"] == {"model": None, "physical_cores": None, "logical_cores": None}
    assert proposal["platform"]["architecture"] == "x86_64", "the runtime still names it"


def test_docker_that_does_not_answer_is_not_running() -> None:
    machine = _Machine(
        {"docker": CommandResult(1, "", "Cannot connect to the Docker daemon")}, {"docker"}
    )
    proposal = _scan(machine, "Linux", "x86_64")
    assert proposal["prerequisites"][0] == {"name": "docker", "state": "not_running"}
    assert recommendations(proposal)[0].startswith("Docker is installed but its daemon")


def test_an_unscanned_platform_runs_nothing() -> None:
    machine = _Machine({}, {"sysctl", "lscpu"})
    proposal = _scan(machine, "Windows", "AMD64")
    assert proposal["platform"] == {"operating_system": None, "architecture": "x86_64"}
    assert proposal["unknown"][0] == {
        "field": "platform",
        "reason": "Windows is not a scanned platform",
    }
    assert machine.calls == []


def test_each_scan_tool_is_allowlisted_with_one_fixed_argument_vector() -> None:
    assert set(hardware.TOOL_ARGUMENTS) <= ALLOWLISTED_EXECUTABLES
    for tool, argv in hardware.TOOL_ARGUMENTS.items():
        assert argv[0] == tool
        assert all(isinstance(part, str) and part for part in argv)
    assert "uv" not in ALLOWLISTED_EXECUTABLES, "uv is looked up, never run"


def test_build_proposal_fills_memory_from_the_runtime_when_no_tool_does() -> None:
    proposal = build_proposal(
        system="Linux",
        machine="aarch64",
        outcomes={"lscpu": ToolOutcome("absent")},
        memory_bytes=8 * 2**30,
        storage_bytes=None,
        prerequisites={},
    )
    assert proposal["memory"]["ram_gib"] == 8.0
    assert proposal["storage_gib"] is None
    assert {"field": "cpu", "reason": "lscpu is not installed"} in proposal["unknown"]
