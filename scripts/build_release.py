# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-004: build the release artifacts and the evidence that describes them.

This produces, into one output directory:

* `oak_community-<version>.tar.gz` and `oak_community-<version>-py3-none-any.whl`
* `oak-community-<version>.cdx.json` — a CycloneDX SBOM of the **released runtime
  closure**, not of a developer virtualenv
* `THIRD-PARTY-LICENCES.md` — the licence inventory, generated from that SBOM
* `SHA256SUMS` — a checksum manifest covering every artifact above
* `build-provenance.json` — how, where and from what commit the build ran

Two properties are enforced rather than asserted. The build runs twice into separate
directories and the digests must match, so a regression in reproducibility fails the
release instead of being discovered by a consumer. And the wheel is installed into a
throwaway environment containing only the locked runtime closure, then exercised from a
working directory outside this checkout, so an artifact that cannot resolve its own
packaged schemas never gets a checksum.

Artifacts are **not signed**. No maintainer signing key exists, and this release does not
invent one. See docs/release-process.md for what the checksums do and do not prove.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "release"
CHECKSUM_MANIFEST = "SHA256SUMS"
PROVENANCE = "build-provenance.json"
LICENCE_INVENTORY = "THIRD-PARTY-LICENCES.md"
# Everything a consumer verifies. `build-provenance.json` is deliberately absent: it
# records wall-clock facts about one build, so including it would make the manifest
# differ between two otherwise identical builds.
UNCHECKSUMMED = frozenset({CHECKSUM_MANIFEST, PROVENANCE})


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Run a command, failing loudly with its own diagnostics."""

    result = subprocess.run(
        command,
        cwd=cwd or ROOT,
        env={**os.environ, **(env or {})},
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"release step failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_into(destination: Path) -> dict[str, str]:
    """Build the sdist and wheel, returning artifact name to digest."""

    destination.mkdir(parents=True, exist_ok=True)
    _run(
        ["uv", "build", "--no-build-isolation", "--out-dir", str(destination)],
        env={"UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(ROOT / ".uv-cache"))},
    )
    # uv drops a `.gitignore` containing `*` beside the artifacts. It is build-tool
    # bookkeeping, not something a consumer downloads, so it must not become a
    # checksummed release artifact.
    marker = destination / ".gitignore"
    if marker.is_file():
        marker.unlink()
    return {
        path.name: _digest(path)
        for path in sorted(destination.iterdir())
        if path.suffix == ".whl" or path.name.endswith(".tar.gz")
    }


def _export_runtime_closure(destination: Path) -> Path:
    """Write the locked runtime closure — no development groups, no project."""

    # Hashes are kept: `uv pip install -r` verifies them, so the environment the SBOM
    # and licence inventory describe is the locked one rather than whatever the index
    # served at build time.
    requirements = destination / "requirements-release.txt"
    exported = _run(
        [
            "uv",
            "export",
            "--no-default-groups",
            "--no-emit-project",
            "--format",
            "requirements-txt",
        ]
    )
    requirements.write_text(exported, encoding="utf-8")
    return requirements


def _install_release_environment(wheel: Path, requirements: Path, home: Path) -> Path:
    """Install exactly the locked runtime closure plus the built wheel."""

    environment = home / "release-venv"
    _run(
        ["uv", "venv", "--python", (ROOT / ".python-version").read_text().strip(), str(environment)]
    )
    _run(["uv", "pip", "install", "--python", str(environment), "-r", str(requirements)])
    _run(["uv", "pip", "install", "--python", str(environment), "--no-deps", str(wheel)])
    return environment


def _smoke_test(environment: Path, home: Path) -> dict[str, str]:
    """Run the installed artifact from outside the checkout.

    An editable development install always finds schemas in the source tree, so this
    is the only place the packaged-data path is exercised against a real install.
    """

    outside = home / "outside"
    outside.mkdir(exist_ok=True)
    interpreter = environment / "bin" / "python"
    console_script = environment / "bin" / "oak"

    reported = _run([str(console_script), "--version"], cwd=outside).strip()
    expected = _version()
    if reported != expected:
        raise SystemExit(f"installed console script reports {reported!r}, expected {expected!r}")

    resolved = _run(
        [
            str(interpreter),
            "-c",
            "import json;"
            "from oak.bootstrap import canonical_schema_directory,"
            " canonical_catalogue_directory, canonical_policy_pack_directory;"
            "print(json.dumps({"
            "'schemas': str(canonical_schema_directory()),"
            "'catalogue': str(canonical_catalogue_directory()),"
            "'policy_packs': str(canonical_policy_pack_directory())}))",
        ],
        cwd=outside,
    )
    paths: dict[str, str] = json.loads(resolved)
    # Both sides are resolved: on macOS the temporary directory is reached through a
    # /var -> /private/var symlink, so an unresolved comparison reports a false miss.
    installed_root = environment.resolve()
    for name, value in paths.items():
        if not Path(value).resolve().is_relative_to(installed_root):
            raise SystemExit(f"installed {name} resolved outside the release environment: {value}")
    return paths


def _build_sbom(environment: Path, output: Path, version: str) -> Path:
    """Generate a CycloneDX SBOM describing the released runtime closure."""

    sbom_path = output / f"oak-community-{version}.cdx.json"
    _run(
        [
            "uv",
            "run",
            "cyclonedx-py",
            "environment",
            "--output-reproducible",
            "--pyproject",
            str(ROOT / "pyproject.toml"),
            "--output-format",
            "JSON",
            "--output-file",
            str(sbom_path),
            str(environment),
        ]
    )
    return sbom_path


def _stamp_sbom_subject(sbom_path: Path, artifacts: dict[str, str]) -> None:
    """Bind the SBOM to the exact bytes it describes.

    A bill of materials that does not name the artifact it belongs to can be paired
    with any build. Recording the wheel and sdist digests on the subject component
    makes substitution detectable.
    """

    document: dict[str, Any] = json.loads(sbom_path.read_text(encoding="utf-8"))
    metadata = document.setdefault("metadata", {})
    component = metadata.setdefault("component", {})
    component["hashes"] = [
        {"alg": "SHA-256", "content": digest}
        for _, digest in sorted(artifacts.items())
        if _.endswith((".whl", ".tar.gz"))
    ]
    component.setdefault("properties", []).extend(
        {"name": "oak:artifact", "value": f"{name}=sha256:{digest}"}
        for name, digest in sorted(artifacts.items())
        if name.endswith((".whl", ".tar.gz"))
    )
    sbom_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _locked_runtime_names(requirements: Path) -> set[str]:
    """Every package the lock names for the runtime closure, markers included."""

    names: set[str] = set()
    for line in requirements.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        # A hashed export continues each requirement over several `--hash=` lines.
        if not stripped or stripped.startswith(("#", "-", "\\")):
            continue
        name, separator, _ = stripped.partition("==")
        if separator:
            names.add(name.strip().lower().replace("_", "-").rstrip("\\").strip())
    return names


def _licence_inventory(sbom_path: Path, output: Path, version: str, locked: set[str]) -> Path:
    """Generate the third-party licence inventory from the release SBOM."""

    document = json.loads(sbom_path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str]] = []
    for component in document.get("components", []):
        name = str(component.get("name", "?"))
        component_version = str(component.get("version", "?"))
        licences: list[str] = []
        for licence in component.get("licenses", []):
            if "expression" in licence:
                licences.append(str(licence["expression"]))
            elif "license" in licence:
                entry = licence["license"]
                licences.append(str(entry.get("id") or entry.get("name") or "?"))
        rows.append((name, component_version, ", ".join(sorted(set(licences))) or "not declared"))

    # The SBOM scans an environment, so a package whose environment marker excludes this
    # platform never appears in it. Naming those explicitly keeps the inventory complete
    # rather than quietly platform-specific.
    installed = {name.lower().replace("_", "-") for name, _, _ in rows}
    unresolved = sorted(locked - installed)

    lines = [
        "<!-- SPDX-License-Identifier: Apache-2.0 -->",
        "",
        f"# Third-party licences — OAK Community {version}",
        "",
        "OAK Community is licensed under Apache-2.0 (see `LICENSE`). The table below is",
        "generated from the release SBOM and lists every package in the **runtime**",
        "dependency closure of the released wheel. Development, test, lint and build",
        "tooling is not included, because it is not distributed.",
        "",
        "Licence strings are the ones the packages declare about themselves. They are",
        "reproduced, not adjudicated: this inventory is a starting point for a licence",
        "review, not the outcome of one.",
        "",
        "| Package | Version | Declared licence |",
        "|---|---|---|",
    ]
    lines.extend(f"| {name} | {ver} | {lic} |" for name, ver, lic in sorted(rows))
    lines.extend(
        [
            "",
            f"Built on `{platform.platform()}` ({platform.machine()}). The SBOM is a scan of a",
            "real installed environment, so packages whose environment markers exclude this",
            "platform are not in the table above.",
            "",
        ]
    )
    if unresolved:
        lines.extend(
            [
                "The lockfile also names the following runtime packages, which this platform's",
                "markers exclude. They ship to consumers whose platform does select them, and",
                "their licences must be reviewed on a platform that resolves them:",
                "",
                *(f"- `{name}`" for name in unresolved),
                "",
            ]
        )
    lines.extend(
        [
            f"Generated from `oak-community-{version}.cdx.json`. Regenerate with `make release`.",
            "",
        ]
    )
    inventory = output / LICENCE_INVENTORY
    inventory.write_text("\n".join(lines), encoding="utf-8")
    return inventory


def _write_checksums(output: Path) -> Path:
    """Write a coreutils-compatible checksum manifest."""

    manifest = output / CHECKSUM_MANIFEST
    entries = [
        f"{_digest(path)}  {path.name}"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in UNCHECKSUMMED
    ]
    manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return manifest


def _write_provenance(output: Path, version: str, extra: dict[str, Any]) -> Path:
    """Record how this build ran. Not reproducible, and not checksummed."""

    try:
        commit = _run(["git", "rev-parse", "HEAD"]).strip()
        dirty = bool(_run(["git", "status", "--porcelain"]).strip())
    except SystemExit:
        commit, dirty = "unknown", True

    provenance = {
        "artifact_version": version,
        "source_commit": commit,
        "source_tree_dirty": dirty,
        "builder": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "uv": _run(["uv", "--version"]).strip(),
        },
        "signed": False,
        "signing_note": (
            "Release artifacts are unsigned. Checksums establish that the bytes you "
            "have match the bytes this build produced; they do not establish who "
            "produced them. See docs/release-process.md."
        ),
        **extra,
    }
    path = output / PROVENANCE
    path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build(output: Path) -> int:
    version = _version()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    print(f"building OAK Community {version}")
    artifacts = _build_into(output)

    with tempfile.TemporaryDirectory() as scratch:
        home = Path(scratch)

        print("verifying the build reproduces")
        again = _build_into(home / "rebuild")
        if again != artifacts:
            differing = sorted(
                name
                for name in set(artifacts) | set(again)
                if artifacts.get(name) != again.get(name)
            )
            raise SystemExit(
                "the build is not reproducible; two builds of the same tree differ for: "
                + ", ".join(differing)
            )

        wheel = next(path for path in output.iterdir() if path.suffix == ".whl")
        requirements = _export_runtime_closure(home)
        print("installing the built wheel into a clean environment")
        environment = _install_release_environment(wheel, requirements, home)

        print("exercising the installed artifact outside the checkout")
        resolved = _smoke_test(environment, home)

        print("generating the release SBOM")
        sbom_path = _build_sbom(environment, output, version)
        _stamp_sbom_subject(sbom_path, artifacts)
        _licence_inventory(sbom_path, output, version, _locked_runtime_names(requirements))

    manifest = _write_checksums(output)
    _write_provenance(
        output,
        version,
        {
            "reproducible_rebuild_verified": True,
            "clean_environment_install_verified": True,
            "packaged_data_resolved_from": {
                name: Path(value).name for name, value in resolved.items()
            },
        },
    )

    print(f"\nrelease artifacts in {output}")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        print(f"  {line}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"directory to write release artifacts into (default: {DEFAULT_OUTPUT})",
    )
    arguments = parser.parse_args()
    return build(arguments.output.resolve())


if __name__ == "__main__":
    sys.exit(main())
