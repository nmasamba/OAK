# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-039: the real scan on the machine running the suite, on each of CI's three jobs.

This proves the macOS path on `check-macos-arm64` and the Linux path without a GPU on the
two Linux jobs; the NVIDIA and AMD paths are proven by fixture only
(`tests/unit/test_hardware_scan.py`). It asserts nothing a particular machine decides,
only what the scan must always be: allowlisted fields, a reason for each unknown, and no
guess.
"""

from __future__ import annotations

import platform

from oak.domain.hardware import LINUX_TOOLS, MACOS_TOOLS, normalize_system
from oak.runner.hardware import scan

KEYS = {
    "platform",
    "cpu",
    "memory",
    "storage_gib",
    "accelerators",
    "prerequisites",
    "unknown",
    "tools",
}


def test_the_scan_describes_this_machine_and_never_guesses() -> None:
    proposal = scan()
    system = normalize_system(platform.system())

    assert set(proposal) == KEYS
    assert proposal["platform"]["operating_system"] == system
    assert proposal["memory"]["ram_gib"] and proposal["memory"]["ram_gib"] > 0
    assert [entry["name"] for entry in proposal["prerequisites"]] == ["docker", "uv"]
    for entry in proposal["unknown"]:
        assert entry["field"] and entry["reason"], entry
    if system == "macos":
        assert [tool["name"] for tool in proposal["tools"]] == list(MACOS_TOOLS)
        assert proposal["tools"][0] == {"name": "sysctl", "status": "ran"}
        assert proposal["cpu"]["logical_cores"] and proposal["cpu"]["logical_cores"] > 0
    elif system == "linux":
        assert [tool["name"] for tool in proposal["tools"]] == sorted(LINUX_TOOLS)
        assert {"name": "lscpu", "status": "ran"} in proposal["tools"]
        assert proposal["cpu"]["logical_cores"] and proposal["cpu"]["logical_cores"] > 0
        statuses = {tool["name"]: tool["status"] for tool in proposal["tools"]}
        if "absent" in (statuses["nvidia-smi"], statuses["rocm-smi"]):
            # A vendor whose tool is absent is unknown, so "no GPU" is never claimed.
            assert proposal["accelerators"] != []
