# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-006: report whatever OAK has left on this machine.

An uninstall procedure without a check is a claim, not evidence. This walks every
location OAK writes to and reports what survives, so a reviewer can prove that trying
OAK and removing it leaves nothing behind.

It is strictly read-only: it deletes nothing, and it never runs a Docker command that
could mutate state.

Exit codes: 0 nothing found, 1 residue found, 2 the check could not run.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

EXIT_CLEAN = 0
EXIT_RESIDUE = 1
EXIT_UNAVAILABLE = 2

# Home-directory state. `~/.oak/trust` holds Ed25519 private keys, so it is called out
# separately rather than folded into a generic "state directory" line.
HOME_PATHS: tuple[tuple[str, str], ...] = (
    ("~/.oak/trust", "Ed25519 PRIVATE signing keys and trust anchors"),
    ("~/.oak/mailbox", "outbound dispatch mailbox"),
    ("~/.oak/extensions", "extension quarantine and activations"),
    ("~/.oak/runner", "runner journal, consumed nonces, processed dispatches"),
    ("~/.oak", "OAK home-directory state"),
)

# In-repository build output and caches, relative to the checkout root.
REPOSITORY_PATHS: tuple[tuple[str, str], ...] = (
    (".venv", "Python virtual environment"),
    ("node_modules", "workspace Node modules"),
    ("web/node_modules", "web Node modules"),
    ("web/dist", "built web bundle"),
    ("web/test-results", "Playwright output"),
    ("dist", "built Python artifacts"),
    (".oak", "in-repo workspace or server artifact store (OAK_ARTIFACT_ROOT default)"),
    ("sbom", "generated SBOM"),
    (".uv-cache", "uv cache"),
    ("-.uv-cache", "stray uv cache (mis-quoted UV_CACHE_DIR)"),
    (".mypy_cache", "mypy cache"),
    (".ruff_cache", "ruff cache"),
    (".pytest_cache", "pytest cache"),
)

DOCKER_VOLUMES = ("oak-community_oak-postgres-data", "oak-community_oak-artifacts")
DOCKER_NETWORK = "oak-community_control-plane"
# Compose names images `<project>-<service>` (oak-community-api). A hand-built or
# release-workflow image uses `<org>/<name>` (oak-community/api). Both must be reported:
# checking only the slash form let every compose-built image survive an uninstall while
# the checker still said "clean".
IMAGE_PREFIXES = ("oak-community/", "oak-community-")
FIXTURE_LABEL = "oak.fixture=true"


@dataclass(frozen=True, slots=True)
class Residue:
    kind: str
    name: str
    detail: str


def _directory_size(path: Path) -> str:
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
    except OSError:
        return "size unknown"
    # Integer-divide-then-format under-reported by up to 46%: 2 GB showed as "1.0 GiB",
    # which matters when the number is the argument for cleaning something up.
    size = float(total)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "size unknown"


def _check_paths(base: Path, entries: tuple[tuple[str, str], ...]) -> Iterator[Residue]:
    seen: set[Path] = set()
    for relative, description in entries:
        path = Path(relative).expanduser() if relative.startswith("~") else base / relative
        if not path.exists():
            continue
        # `~/.oak` is listed last as a catch-all. The guard has to look at the candidate's
        # own parents *and* at whether an already-reported entry lives under it; checking
        # only the former reported `~/.oak` a fourth time alongside its three children and
        # re-counted their bytes in its size.
        if any(parent in seen for parent in path.parents):
            continue
        if any(reported.is_relative_to(path) for reported in seen):
            continue
        seen.add(path)
        yield Residue("path", str(path), f"{description} ({_directory_size(path)})")


def _docker(*arguments: str) -> list[str]:
    result = subprocess.run(
        ["docker", *arguments], check=False, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _check_docker() -> Iterator[Residue]:
    if shutil.which("docker") is None:
        return
    volumes = set(_docker("volume", "ls", "--quiet"))
    for name in DOCKER_VOLUMES:
        if name in volumes:
            yield Residue("docker volume", name, "holds design cases or artifact bytes")

    for image in _docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}"):
        if image.startswith(IMAGE_PREFIXES):
            yield Residue("docker image", image, "built OAK image")

    if DOCKER_NETWORK in set(_docker("network", "ls", "--format", "{{.Name}}")):
        yield Residue("docker network", DOCKER_NETWORK, "Compose network")

    for container in _docker(
        "ps", "--all", "--filter", f"label={FIXTURE_LABEL}", "--format", "{{.Names}}"
    ):
        yield Residue("docker container", container, "runner fixture container")


def check(repository_root: Path, *, include_repository: bool) -> list[Residue]:
    residue = list(_check_paths(repository_root, HOME_PATHS))
    if include_repository:
        residue.extend(_check_paths(repository_root, REPOSITORY_PATHS))
    residue.extend(_check_docker())
    return residue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="checkout to inspect for build output and caches",
    )
    parser.add_argument(
        "--home-only",
        action="store_true",
        help="skip in-repository build output; report only home-directory and Docker state",
    )
    arguments = parser.parse_args()

    if shutil.which("docker") is None:
        print("note: docker is not on PATH; container state was not inspected.", file=sys.stderr)

    try:
        residue = check(
            arguments.repository_root.resolve(), include_repository=not arguments.home_only
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"could not complete the check: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_UNAVAILABLE

    if not residue:
        print("clean: no OAK state, Docker resource or build output found.")
        return EXIT_CLEAN

    print(f"{len(residue)} item(s) of OAK state remain on this machine:\n")
    for item in residue:
        print(f"  {item.kind:17s} {item.name}")
        print(f"  {'':17s} └─ {item.detail}")
    print("\nSee docs/operations.md#uninstall for how to remove each of these.")
    print(
        "Global toolchain caches (uv, pnpm, Playwright) are shared with other projects "
        "and are deliberately not reported here.",
        file=sys.stderr,
    )
    return EXIT_RESIDUE


if __name__ == "__main__":
    sys.exit(main())
