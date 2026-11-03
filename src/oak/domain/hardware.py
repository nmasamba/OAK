# SPDX-License-Identifier: Apache-2.0
"""What a hardware scan may say about a machine, read from fixed tools' output.

Pure: each function takes text a tool printed and returns data; nothing here runs a
process or reads a file. A parser keeps only the fields named below, so a serial number,
a GPU UUID, a host name or a user name a tool printed never reaches a proposal (the
data-minimization invariant), and every kept string is bounded and drawn from a narrow
character set. A tool that is absent, failed, timed out or printed too much is an
``unknown`` with its reason, never a guess.

The proposal this builds is what the user is shown and may confirm; the raw output never
leaves the machine it was read on.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

ToolStatus = Literal["ran", "absent", "failed", "timed_out", "too_large"]

MACOS_TOOLS = ("sysctl", "system_profiler")
LINUX_TOOLS = ("lscpu", "nvidia-smi", "rocm-smi")
SCAN_TOOLS = MACOS_TOOLS + LINUX_TOOLS
PREREQUISITES = ("docker", "uv")
# The fields a scan result carries, as `build_proposal` returns them.
PROPOSAL_FIELDS = (
    "platform",
    "cpu",
    "memory",
    "storage_gib",
    "accelerators",
    "prerequisites",
    "unknown",
    "tools",
)
INSTALL_PAGES = {
    "docker": "https://docs.docker.com/get-started/get-docker/",
    "uv": "https://docs.astral.sh/uv/getting-started/installation/",
}
# The order sysctl prints its values in, one per line, for the names the scanner asks for.
SYSCTL_NAMES = ("hw.memsize", "hw.physicalcpu", "hw.logicalcpu", "machdep.cpu.brand_string")
# nvidia-smi exits 6 when it finds no device: a known absence, not an unknown.
NVIDIA_NO_DEVICE = 6
MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 ()@.,+/_\[\]-]{0,79}$"
DRIVER_PATTERN = r"^[0-9][0-9.]{0,31}$"
_MODEL = re.compile(MODEL_PATTERN)
_DRIVER = re.compile(DRIVER_PATTERN)
_GIB = 2**30
_MIB_PER_GIB = 1024
_APPLE_VENDORS = {
    "sppci_vendor_apple": "apple",
    "sppci_vendor_amd": "amd",
    "sppci_vendor_ati": "amd",
}
_APPLE_VENDORS |= {"sppci_vendor_intel": "intel", "sppci_vendor_nvidia": "nvidia"}
_ARCHITECTURES = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
_SYSTEMS = {"darwin": "macos", "linux": "linux"}
_RUNTIME_TOKENS = {"metal": "apple-metal", "cuda": "nvidia-cuda", "rocm": "amd-rocm"}


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """What running one tool gave: its status, its output when it ran, and its exit code."""

    status: ToolStatus
    stdout: str = ""
    returncode: int | None = None
    timeout_seconds: int | None = None


def normalize_architecture(machine: str) -> str | None:
    """The catalogue's spelling of a machine's architecture: ``x86_64`` or ``arm64``."""

    return _ARCHITECTURES.get(machine.strip().casefold())


def normalize_system(system: str) -> str | None:
    return _SYSTEMS.get(system.strip().casefold())


def bounded_model(value: Any) -> str | None:
    """A model name a tool printed, kept only when it is short plain text."""

    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text if _MODEL.fullmatch(text) and text != "-" else None


def _count(value: Any) -> int | None:
    text = str(value).strip() if isinstance(value, (str, int)) else ""
    return int(text) if text.isdigit() and 0 < int(text) <= 4096 else None


def _gib(byte_count: int | None) -> float | None:
    return None if byte_count is None or byte_count <= 0 else round(byte_count / _GIB, 1)


def parse_sysctl(stdout: str) -> dict[str, Any]:
    """``sysctl -n`` over ``SYSCTL_NAMES``: one value per line, in that order."""

    lines = stdout.splitlines()
    if len(lines) != len(SYSCTL_NAMES):
        return {}
    memory, physical, logical, brand = lines
    memory_bytes = int(memory) if memory.strip().isdigit() else None
    return {
        "ram_gib": _gib(memory_bytes),
        "physical_cores": _count(physical),
        "logical_cores": _count(logical),
        "cpu_model": bounded_model(brand),
    }


def parse_system_profiler(stdout: str) -> list[dict[str, Any]]:
    """``system_profiler -json -detailLevel mini SPDisplaysDataType``: the GPUs alone.

    Each entry also lists the displays attached to it (``spdisplays_ndrvs``), with their
    serial numbers; only the GPU's own fields are read, so a display never reaches a
    proposal.
    """

    document = json.loads(stdout)
    entries = document.get("SPDisplaysDataType") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise ValueError("system_profiler printed no display data")
    gpus: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("sppci_device_type") != "spdisplays_gpu":
            continue
        vendor = _APPLE_VENDORS.get(str(entry.get("spdisplays_vendor", "")).casefold(), "other")
        unified = vendor == "apple"
        memory = None if unified else _gib(_size_bytes(entry.get("spdisplays_vram")))
        gpus.append(
            {
                "vendor": vendor,
                "model": bounded_model(entry.get("sppci_model")),
                "memory_gib": memory,
                "unified_memory": unified,
                "runtime": "metal" if entry.get("spdisplays_mtlgpufamilysupport") else None,
                "driver_version": None,
            }
        )
    return gpus


def _size_bytes(value: Any) -> int | None:
    """``"8 GB"`` as system_profiler prints a discrete GPU's memory."""

    match = re.fullmatch(r"\s*([0-9]+)\s*(MB|GB)\s*", value) if isinstance(value, str) else None
    if match is None:
        return None
    return int(match.group(1)) * (2**20 if match.group(2) == "MB" else _GIB)


def _lscpu_entries(items: Any, found: list[tuple[str, str]]) -> None:
    """Every field and value, in the order lscpu prints them, children after their parent."""

    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        data = item.get("data")
        if isinstance(field, str) and isinstance(data, str):
            found.append((field.strip().rstrip(":").casefold(), data.strip()))
        _lscpu_entries(item.get("children"), found)


def _cores(group: dict[str, str]) -> int | None:
    # x86 counts cores per socket; Arm machines often per cluster, with sockets as "-".
    for per_key, unit_key in (
        ("core(s) per socket", "socket(s)"),
        ("core(s) per cluster", "cluster(s)"),
    ):
        per_unit, units = _count(group.get(per_key)), _count(group.get(unit_key))
        if per_unit and units:
            return per_unit * units
    return None


def parse_lscpu(stdout: str) -> dict[str, Any]:
    """``lscpu -J``: flat in some util-linux releases, nested under the vendor in others.

    A machine with two kinds of core (Arm's big.LITTLE) lists one model-name group per
    kind, each with its own counts: the cores are summed over the groups, and the model
    names joined.
    """

    document = json.loads(stdout)
    entries: list[tuple[str, str]] = []
    _lscpu_entries(document.get("lscpu") if isinstance(document, dict) else None, entries)
    if not entries:
        raise ValueError("lscpu printed no fields")
    fields: dict[str, str] = {}
    groups: list[dict[str, str]] = []
    for key, value in entries:
        fields.setdefault(key, value)
        if key == "model name":
            groups.append({key: value})
        elif groups:
            groups[-1].setdefault(key, value)
    counted = [cores for cores in map(_cores, groups or [fields]) if cores is not None]
    names = list(dict.fromkeys(group["model name"] for group in groups))
    return {
        "architecture": normalize_architecture(fields.get("architecture", "")),
        "cpu_model": bounded_model(" + ".join(names)) if names else None,
        "logical_cores": _count(fields.get("cpu(s)")),
        "physical_cores": sum(counted) if counted else _cores(fields),
    }


def parse_nvidia_smi(stdout: str) -> list[dict[str, Any]]:
    """``nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits``."""

    gpus: list[dict[str, Any]] = []
    for row in csv.reader(io.StringIO(stdout)):
        if not row:
            continue
        if len(row) != 3:
            raise ValueError("nvidia-smi printed an unexpected row")
        name, memory_mib, driver = (cell.strip() for cell in row)
        memory = round(int(memory_mib) / _MIB_PER_GIB, 1) if memory_mib.isdigit() else None
        gpus.append(
            {
                "vendor": "nvidia",
                "model": bounded_model(name),
                "memory_gib": memory if memory else None,
                "unified_memory": False,
                "runtime": "cuda",
                "driver_version": driver if _DRIVER.fullmatch(driver) else None,
            }
        )
    return gpus


def parse_rocm_smi(stdout: str) -> list[dict[str, Any]]:
    """``rocm-smi --showproductname --showmeminfo vram --json``: one object per card.

    Key spellings differ across ROCm releases ("Card series", "Card Series"), so keys are
    compared without case; a card's GUID, serial or unique id is never read.
    """

    document = json.loads(stdout)
    if not isinstance(document, dict):
        raise ValueError("rocm-smi printed no cards")
    gpus: list[dict[str, Any]] = []
    for name, card in sorted(document.items()):
        if not name.startswith("card") or not isinstance(card, dict):
            continue
        fields = {str(key).strip().casefold(): value for key, value in card.items()}
        total = str(fields.get("vram total memory (b)", "")).strip()
        model = bounded_model(fields.get("card series")) or bounded_model(fields.get("card model"))
        gpus.append(
            {
                "vendor": "amd",
                "model": model,
                "memory_gib": _gib(int(total)) if total.isdigit() else None,
                "unified_memory": False,
                "runtime": "rocm",
                "driver_version": None,
            }
        )
    return gpus


def _reason(tool: str, outcome: ToolOutcome) -> str:
    if outcome.status == "absent":
        return f"{tool} is not installed"
    if outcome.status == "timed_out":
        return f"{tool} did not finish within {outcome.timeout_seconds} s"
    if outcome.status == "too_large":
        return f"{tool} printed more than the scanner reads"
    if outcome.status == "failed":
        return f"{tool} exited {outcome.returncode}"
    return f"{tool} printed output the scanner could not read"


def build_proposal(
    *,
    system: str,
    machine: str,
    outcomes: dict[str, ToolOutcome],
    memory_bytes: int | None,
    storage_bytes: int | None,
    prerequisites: dict[str, str],
) -> dict[str, Any]:
    """The proposal a scan makes: allowlisted fields, ``unknown`` reasons, the tools' fates.

    ``memory_bytes`` and ``storage_bytes`` come from the runtime (not from a tool) and fill
    what a tool could not; ``prerequisites`` maps ``docker`` and ``uv`` to ``present``,
    ``absent`` or (Docker only) ``not_running``. Each ``unknown`` entry names what is
    unknown (``cpu``, ``memory``, ``accelerators``, ``accelerators.nvidia``,
    ``accelerators.amd``, ``platform``) and why.
    """

    operating_system = normalize_system(system)
    unknown: list[dict[str, str]] = []
    reader = _Reader(outcomes, unknown)
    cpu: dict[str, Any] = {"model": None, "physical_cores": None, "logical_cores": None}
    ram_gib = _gib(memory_bytes)
    architecture = normalize_architecture(machine)
    accelerators: list[dict[str, Any]] | None = None
    if operating_system == "macos":
        values = reader.read("sysctl", parse_sysctl, ("cpu", "memory"))
        if values:
            cpu = {key: values[source] for key, source in _CPU_KEYS}
            ram_gib = values["ram_gib"] or ram_gib
        accelerators = reader.read("system_profiler", parse_system_profiler, ("accelerators",))
    elif operating_system == "linux":
        values = reader.read("lscpu", parse_lscpu, ("cpu",))
        if values:
            cpu = {key: values[source] for key, source in _CPU_KEYS}
            architecture = values["architecture"] or architecture
        accelerators = _linux_accelerators(outcomes, reader)
    else:
        unknown.append({"field": "platform", "reason": f"{system} is not a scanned platform"})
    if ram_gib is not None:
        # The runtime's figure stands in for a tool that failed: memory is known.
        unknown[:] = [entry for entry in unknown if entry["field"] != "memory"]
    known = {entry["field"] for entry in unknown}
    if cpu["model"] is None and "cpu" not in known:
        unknown.append({"field": "cpu", "reason": "the tool did not name the CPU model"})
    if ram_gib is None and "memory" not in known:
        unknown.append({"field": "memory", "reason": "neither a tool nor the runtime reported it"})
    explained = any(field == "platform" or field.startswith("accelerators") for field in known)
    if accelerators is None and not explained:
        unknown.append({"field": "accelerators", "reason": "no GPU tool could be read"})
    unified = any(gpu["unified_memory"] for gpu in accelerators or [])
    tools = [
        {"name": tool, "status": outcome.status}
        for tool, outcome in sorted(outcomes.items())
        if tool in SCAN_TOOLS
    ]
    return {
        "platform": {"operating_system": operating_system, "architecture": architecture},
        "cpu": cpu,
        "memory": {"ram_gib": ram_gib, "unified": unified},
        "storage_gib": _gib(storage_bytes),
        "accelerators": accelerators,
        "prerequisites": [
            {"name": name, "state": prerequisites.get(name, "absent")} for name in PREREQUISITES
        ],
        "unknown": unknown,
        "tools": tools,
    }


_CPU_KEYS = (
    ("model", "cpu_model"),
    ("physical_cores", "physical_cores"),
    ("logical_cores", "logical_cores"),
)


@dataclass(slots=True)
class _Reader:
    """Runs a parser over a tool's output, recording an unknown for each field it leaves."""

    outcomes: dict[str, ToolOutcome]
    unknown: list[dict[str, str]]

    def read(self, tool: str, parser: Any, fields: tuple[str, ...]) -> Any:
        outcome = self.outcomes.get(tool, ToolOutcome("absent"))
        reason = None
        result = None
        if outcome.status != "ran":
            reason = _reason(tool, outcome)
        else:
            try:
                result = parser(outcome.stdout)
            except (ValueError, TypeError, KeyError, AttributeError):
                reason = _reason(tool, ToolOutcome("ran"))
        if reason is not None:
            self.unknown.extend({"field": field, "reason": reason} for field in fields)
        return result


def _linux_accelerators(
    outcomes: dict[str, ToolOutcome], reader: _Reader
) -> list[dict[str, Any]] | None:
    """Every GPU the vendors' tools report, or ``None`` when that list cannot be known.

    A GPU without its vendor's tool cannot be seen. So the GPUs found are listed (a vendor
    whose tool did not answer is recorded as unknown beside them), but "no GPU" is claimed
    only when both NVIDIA's and AMD's tools answered; otherwise the list is ``None``.
    """

    found: list[dict[str, Any]] = []
    answered = 0
    nvidia = outcomes.get("nvidia-smi", ToolOutcome("absent"))
    if nvidia.status == "failed" and nvidia.returncode == NVIDIA_NO_DEVICE:
        answered += 1
    else:
        gpus = reader.read("nvidia-smi", parse_nvidia_smi, ("accelerators.nvidia",))
        if gpus is not None:
            answered += 1
            found.extend(gpus)
    gpus = reader.read("rocm-smi", parse_rocm_smi, ("accelerators.amd",))
    if gpus is not None:
        answered += 1
        found.extend(gpus)
    if found or answered == 2:
        return found
    return None


def intent_hardware(proposal: dict[str, Any]) -> dict[str, Any]:
    """The ``spec.hardware`` values a confirmed proposal sets; an unknown sets nothing.

    Once the scan has measured the accelerators, the values that describe them are
    replaced together, so nothing the brief said about another GPU survives: ``vram_gib``
    is the largest discrete GPU's memory or, for unified memory (Apple silicon), the system
    memory the GPU shares, and ``None`` (cleared) when neither is known; ``drivers`` is the
    measured list, empty when the GPUs report none.
    """

    values: dict[str, Any] = {}
    architecture = proposal["platform"]["architecture"]
    if architecture:
        values["cpu_architectures"] = [architecture]
    if proposal["memory"]["ram_gib"] is not None:
        values["ram_gib"] = proposal["memory"]["ram_gib"]
    if proposal["storage_gib"] is not None:
        values["storage_gib"] = proposal["storage_gib"]
    accelerators = proposal["accelerators"]
    if accelerators is not None:
        values["accelerators"] = sorted(
            {
                _RUNTIME_TOKENS.get(gpu["runtime"] or "", f"{gpu['vendor']}-gpu")
                for gpu in accelerators
            }
        )
        discrete = [gpu["memory_gib"] for gpu in accelerators if gpu["memory_gib"] is not None]
        unified = any(gpu["unified_memory"] for gpu in accelerators)
        if discrete:
            values["vram_gib"] = max(discrete)
        elif unified and proposal["memory"]["ram_gib"] is not None:
            # The GPU addresses the same memory as the CPU, so what fits in one fits in the
            # other: the weight-floor check and the research hardware class read this.
            values["vram_gib"] = proposal["memory"]["ram_gib"]
        else:
            values["vram_gib"] = None
        values["drivers"] = sorted(
            {
                f"{gpu['vendor']}-driver-{gpu['driver_version']}"
                for gpu in accelerators
                if gpu["driver_version"]
            }
        )
    return values


def recommendations(proposal: dict[str, Any]) -> list[str]:
    """What the user may want to install, with each tool's official page; never done for them."""

    states = {entry["name"]: entry["state"] for entry in proposal["prerequisites"]}
    advice: list[str] = []
    if states.get("docker") == "absent":
        advice.append(
            "Docker is not installed. OAK's container installation needs it (the native "
            f"installation does not): {INSTALL_PAGES['docker']}"
        )
    elif states.get("docker") == "not_running":
        advice.append(
            "Docker is installed but its daemon did not answer. Start Docker before a "
            "container installation."
        )
    if states.get("uv") == "absent":
        advice.append(
            "uv is not installed. It installs OAK and the Python tools a design may need: "
            f"{INSTALL_PAGES['uv']}"
        )
    return advice
