# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: scan the container images OAK ships, and fail on anything fixable.

`make audit` covers the Python and web dependency closures. Neither looks inside a built
image, so the OS packages in the shipped layers went unassessed until this existed — the
gap recorded as `RR-035`. The first run of this scan found 6 CRITICAL and 72 HIGH in the
API image, including `uv` and `uvx` shipping in the runtime layer with advisories in their
vendored Rust dependencies.

Two deliberate choices:

* **The scanner never gets the Docker socket.** Images are exported with `docker save` and
  the scanner reads the tarball. A scanner container holding the daemon socket holds the
  daemon, which is a poor trade for a tool whose job is to tell you about risk.
* **Only *fixable* findings fail the run.** A CRITICAL with no vendor fix is information,
  not an action; failing on it would mean either pinning to a scanner's mood or suppressing
  findings wholesale. Fixable findings are the ones someone can do something about, so they
  are the ones that block.

    python scripts/scan_images.py --build
    python scripts/scan_images.py --output docs/release/0.7.0/container-scan.json

Exit codes: 0 nothing fixable, 2 fixable findings present, 3 the scan could not run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
# Pinned: a scanner is a dependency like any other, and "latest" would make the gate's
# verdict depend on when it ran.
SCANNER = "aquasec/trivy:0.74.0"
BLOCKING = ("CRITICAL", "HIGH")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")

IMAGES: tuple[tuple[str, str, str], ...] = (
    ("api", f"oak-community/api:{VERSION}", "deploy/images/api.Dockerfile"),
    ("web", f"oak-community/web:{VERSION}", "deploy/images/web.Dockerfile"),
)


def _run(command: list[str], **keywords: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, **keywords)


def _require_docker() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("docker is required to scan images")
    if _run(["docker", "info"]).returncode != 0:
        raise SystemExit("the Docker daemon is not reachable")


def _build(tag: str, dockerfile: str, platform: str) -> None:
    print(f"building {tag} for {platform}", file=sys.stderr)
    result = _run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            platform,
            "--file",
            dockerfile,
            "--tag",
            tag,
            "--load",
            ".",
        ],
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(f"could not build {tag}:\n{result.stderr[-2000:]}")


def _scan(tag: str, workspace: Path, cache: Path) -> dict[str, Any]:
    archive = workspace / f"{tag.replace('/', '_').replace(':', '_')}.tar"
    saved = _run(["docker", "save", tag, "-o", str(archive)])
    if saved.returncode != 0:
        raise SystemExit(f"could not export {tag}:\n{saved.stderr[-2000:]}")

    cache.mkdir(parents=True, exist_ok=True)
    scanned = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace}:/work",
            "-v",
            f"{cache}:/root/.cache/trivy",
            SCANNER,
            "image",
            "--input",
            f"/work/{archive.name}",
            "--scanners",
            "vuln",
            "--format",
            "json",
            "--no-progress",
            "--quiet",
        ]
    )
    if scanned.returncode != 0 or not scanned.stdout.strip():
        raise SystemExit(f"the scanner failed for {tag}:\n{scanned.stderr[-2000:]}")
    document: dict[str, Any] = json.loads(scanned.stdout)
    return document


def _classify(document: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    fixable: list[dict[str, str]] = []
    unfixable: dict[str, list[str]] = defaultdict(list)
    for result in document.get("Results") or []:
        for finding in result.get("Vulnerabilities") or []:
            severity = str(finding.get("Severity", "UNKNOWN"))
            counts[severity] += 1
            if severity not in BLOCKING:
                continue
            entry = {
                "severity": severity,
                "package": str(finding.get("PkgName", "?")),
                "installed": str(finding.get("InstalledVersion", "?")),
                "id": str(finding.get("VulnerabilityID", "?")),
                "target": str(result.get("Target", "?")),
            }
            fixed = finding.get("FixedVersion")
            if fixed:
                fixable.append({**entry, "fixed_in": str(fixed)})
            else:
                unfixable[entry["package"]].append(f"{severity} {entry['id']}")
    return {
        "counts": {severity: counts.get(severity, 0) for severity in SEVERITIES},
        "fixable": fixable,
        "unfixable": {package: sorted(items) for package, items in sorted(unfixable.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="rebuild the images first")
    parser.add_argument("--platform", default="linux/amd64", help="platform to build and scan")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    arguments = parser.parse_args()

    try:
        _require_docker()
    except SystemExit as error:
        print(str(error), file=sys.stderr)
        return 3

    report: dict[str, Any] = {
        "artifact_version": VERSION,
        "scanner": SCANNER,
        "platform": arguments.platform,
        "images": {},
    }
    cache = ROOT / ".uv-cache" / "trivy"

    try:
        with tempfile.TemporaryDirectory() as scratch:
            workspace = Path(scratch)
            for name, tag, dockerfile in IMAGES:
                if arguments.build:
                    _build(tag, dockerfile, arguments.platform)
                print(f"scanning {tag}", file=sys.stderr)
                report["images"][name] = {"tag": tag, **_classify(_scan(tag, workspace, cache))}
    except SystemExit as error:
        print(str(error), file=sys.stderr)
        return 3

    blocking = 0
    for name, image in report["images"].items():
        counts = image["counts"]
        summary = " ".join(f"{s.lower()}={counts[s]}" for s in SEVERITIES if counts[s])
        print(f"\n{name} ({image['tag']}): {summary or 'no findings'}")
        for package, items in image["unfixable"].items():
            print(f"  no vendor fix  {package}: {', '.join(items)}")
        for finding in image["fixable"]:
            blocking += 1
            print(
                f"  FIXABLE  [{finding['severity']}] {finding['package']} "
                f"{finding['installed']} -> {finding['fixed_in']}  {finding['id']}",
                file=sys.stderr,
            )

    report["fixable_total"] = blocking
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {arguments.output}", file=sys.stderr)

    if blocking:
        print(
            f"\n{blocking} fixable CRITICAL/HIGH finding(s). Rebuild picks up distro "
            "updates; a language-package finding needs a lock change.",
            file=sys.stderr,
        )
        return 2
    print("\nno fixable CRITICAL or HIGH findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
