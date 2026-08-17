# SPDX-License-Identifier: Apache-2.0
"""Check that source, CI, container, package, and documentation toolchains agree."""

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read(root: Path, relative: str, failures: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        failures.append(f"{relative}: missing or unreadable")
        return ""


def _match_version(
    text: str,
    pattern: str,
    source: str,
    failures: list[str],
) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        failures.append(f"{source}: expected pinned version with immutable digest")
        return ""
    return match.group("version")


def _load_package(text: str, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        failures.append("package.json: invalid JSON")
        return {}
    if not isinstance(value, dict):
        failures.append("package.json: root must be an object")
        return {}
    return value


def check(root: Path = ROOT) -> list[str]:
    """Return stable descriptions of every toolchain-contract mismatch."""

    failures: list[str] = []
    python_version = _read(root, ".python-version", failures).strip()
    node_version = _read(root, ".node-version", failures).strip()
    package = _load_package(_read(root, "package.json", failures), failures)
    api_dockerfile = _read(root, "deploy/images/api.Dockerfile", failures)
    web_dockerfile = _read(root, "deploy/images/web.Dockerfile", failures)
    workflow = _read(root, ".github/workflows/ci.yml", failures)
    readme = _read(root, "README.md", failures)
    development = _read(root, "docs/development.md", failures)

    uv_version = _match_version(
        api_dockerfile,
        r"^FROM ghcr\.io/astral-sh/uv:(?P<version>\d+\.\d+\.\d+)@sha256:[a-f0-9]{64} AS uv$",
        "deploy/images/api.Dockerfile",
        failures,
    )
    container_python = _match_version(
        api_dockerfile,
        r"^FROM python:(?P<version>\d+\.\d+\.\d+)-slim@sha256:[a-f0-9]{64}$",
        "deploy/images/api.Dockerfile",
        failures,
    )
    container_node = _match_version(
        web_dockerfile,
        r"^FROM node:(?P<version>\d+\.\d+\.\d+)-alpine@sha256:[a-f0-9]{64} AS build$",
        "deploy/images/web.Dockerfile",
        failures,
    )

    if python_version and container_python != python_version:
        failures.append("Python version differs between .python-version and API container")
    if node_version and container_node != node_version:
        failures.append("Node version differs between .node-version and web container")

    engines = package.get("engines")
    if not isinstance(engines, dict):
        failures.append("package.json: engines must be an object")
        engines = {}
    if node_version and engines.get("node") != node_version:
        failures.append("Node version differs between .node-version and package.json")

    package_manager = package.get("packageManager")
    if not isinstance(package_manager, str) or not package_manager.startswith("pnpm@"):
        failures.append("package.json: packageManager must pin pnpm exactly")
        pnpm_version = ""
    else:
        pnpm_version = package_manager.removeprefix("pnpm@")
    if pnpm_version and engines.get("pnpm") != pnpm_version:
        failures.append("pnpm version differs between packageManager and engines")

    if "uses: astral-sh/setup-uv@v6" not in workflow:
        failures.append("CI workflow: setup-uv action is missing")
    if uv_version and f'version: "{uv_version}"' not in workflow:
        failures.append("uv version differs between CI and API container")
    if "node-version-file: .node-version" not in workflow:
        failures.append("CI workflow: Node must come from .node-version")

    if uv_version:
        uv_parts = uv_version.split(".")
        compatible_series = ".".join(uv_parts[:2]) + ".x"
        documentation_fragments = (
            ("README.md", readme),
            ("docs/development.md", development),
        )
        for name, text in documentation_fragments:
            if f"`uv` {compatible_series}" not in text:
                failures.append(f"{name}: local uv compatibility series is stale")
            if f"{uv_version}" not in text:
                failures.append(f"{name}: exact CI/container uv builder is stale")

    for name, text, version, fragment in (
        ("README.md", readme, python_version, f"Python {python_version}"),
        ("README.md", readme, node_version, f"Node.js {node_version}"),
        ("README.md", readme, pnpm_version, f"`pnpm` {pnpm_version}"),
        ("docs/development.md", development, python_version, f"Python {python_version}"),
        ("docs/development.md", development, node_version, f"Node.js {node_version}"),
        ("docs/development.md", development, pnpm_version, f"`pnpm` {pnpm_version}"),
    ):
        if version and fragment not in text:
            failures.append(f"{name}: documented {fragment.split()[0]} version is stale")

    return failures


def main() -> int:
    failures = check()
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
