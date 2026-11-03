<!-- SPDX-License-Identifier: Apache-2.0 -->

# Hardware scan fixtures

Each file is one tool's output as `oak.runner.hardware` asks for it (the argument vectors
in `TOOL_ARGUMENTS`). The parsers in `oak.domain.hardware` are tested against these, so no
test needs the hardware itself.

| File | Tool and version | Provenance |
|---|---|---|
| `macos-arm64/sysctl.txt` | `sysctl -n hw.memsize hw.physicalcpu hw.logicalcpu machdep.cpu.brand_string`, macOS 26.3.1 (25D2128) | Recorded on an Apple M1 Max, 2026-11-02 |
| `macos-arm64/system_profiler.json` | `system_profiler -json -detailLevel mini SPDisplaysDataType`, macOS 26.3.1 (25D2128) | Recorded on the same machine; the built-in display's serial number replaced by `SERIALFIXTURE01`, which a test proves never reaches a proposal |
| `linux-arm64/lscpu.json` | `lscpu -J`, util-linux 2.41 (Debian trixie) | Recorded in a `python:3.13.12-slim` container under Docker Desktop on Apple silicon: the flat layout, no model name (`-`), cores counted per cluster |
| `linux-arm64-big-little/lscpu.json` | `lscpu -J`, nested layout | Constructed: an RK3588-like board with four Cortex-A55 and four Cortex-A76 cores, one model-name group per kind of core |
| `linux-x86_64/lscpu.json` | `lscpu -J`, util-linux 2.39 layout (Ubuntu 24.04) | Constructed in the nested layout util-linux prints on x86, for the CPU GitHub's `ubuntu-24.04` runners report; not recorded |
| `nvidia/nvidia-smi.csv` | `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits`, driver 550.54.15 | Constructed in the documented format: no NVIDIA GPU was available to record |
| `amd/rocm-smi.json` | `rocm-smi --showproductname --showmeminfo vram --json`, ROCm 6 key spellings | Constructed in the documented format, with a GUID, a unique id and a serial number (`…FIXTURE…`) that a test proves never reach a proposal: no AMD GPU was available to record |

The NVIDIA and AMD paths are therefore verified by fixture only, and `docs/platforms.md`
says so.
