# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-035 (RR-006): build each image twice and prove the two builds are one image.

A build is reproducible for a platform when a second build of the same commit, with no
cached layer, gives the same image ID. This script does exactly that for each Dockerfile
it is given: the first build may use the cache, the second never does, and the two IDs
must match. What makes the match possible lives in the Dockerfiles (Debian packages from a
dated `snapshot.debian.org` archive in both images, a user whose shadow entry carries a
fixed date) and in the build itself: `SOURCE_DATE_EPOCH` is the source
commit's time, passed as a build argument so that BuildKit stamps the image config with it
and Python compiles hash-based bytecode, and the exporter rewrites every layer's file
timestamps to it (`rewrite-timestamp=true`, BuildKit 0.13 or later).

The claim is per platform: a run proves the platform it built for and nothing else. The
record it writes names the platform, the builder's BuildKit version, the snapshot date,
the source date and both image IDs per image; `scripts/scan_images.py` folds it into the
release's image provenance.

Timestamp rewriting needs a builder that exports a tarball the daemon then loads: the
buildx container driver, as the workflows create it with a pinned BuildKit image. Docker
Desktop's default builder refuses it ("rewrite-timestamp" conflicts with "unpack"), so a
local run names such a builder:

    docker buildx create --name oak-reproduce --driver docker-container \\
        --driver-opt image=moby/buildkit:v0.34.0@sha256:<the digest the workflows pin>
    python3 scripts/reproduce_images.py --builder oak-reproduce --platform linux/arm64 \\
        --output docs/release/0.9.0/image-reproducibility.json \\
        deploy/images/api.Dockerfile deploy/images/web.Dockerfile

Exit codes: 0 every image reproduced, 1 an image did not, 3 a build could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SNAPSHOT = re.compile(r"^ARG DEBIAN_SNAPSHOT=(?P<date>\d{8}T\d{6}Z)$", re.MULTILINE)


def _run(command: list[str], **keywords: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, **keywords)


def _git_output(arguments: list[str]) -> str:
    completed = _run(["git", *arguments], cwd=ROOT)
    return completed.stdout.strip() if completed.returncode == 0 else ""


def source_date_epoch() -> int:
    """The source commit's time: the same for every build of the commit, on any machine."""

    value = _git_output(["log", "-1", "--pretty=%ct"])
    if not value.isdigit():
        raise SystemExit("the source date needs a git commit; pass --source-date-epoch")
    return int(value)


def buildkit_version(builder: str | None) -> str:
    """The BuildKit the builder runs, as `docker buildx inspect` reports it."""

    completed = _run(
        ["docker", "buildx", "inspect", "--bootstrap", *([builder] if builder else [])]
    )
    match = re.search(r"^BuildKit(?: version)?:\s*(\S+)", completed.stdout, re.MULTILINE)
    return match.group(1) if match else "unknown"


def debian_snapshot(dockerfiles: list[Path]) -> str | None:
    for dockerfile in dockerfiles:
        match = SNAPSHOT.search(dockerfile.read_text(encoding="utf-8"))
        if match:
            return match.group("date")
    return None


def _image_id(tag: str) -> str:
    completed = _run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
    if completed.returncode != 0:
        raise SystemExit(f"could not inspect {tag}:\n{completed.stderr[-2000:]}")
    return completed.stdout.strip()


def build(
    dockerfile: Path,
    tag: str,
    *,
    platform: str,
    epoch: int,
    no_cache: bool,
    builder: str | None,
) -> str:
    """One build with every reproducibility flag; returns the image ID."""

    command = [
        "docker",
        "buildx",
        "build",
        *(["--builder", builder] if builder else []),
        "--platform",
        platform,
        "--file",
        str(dockerfile),
        "--build-arg",
        f"SOURCE_DATE_EPOCH={epoch}",
        "--output",
        f"type=docker,name={tag},rewrite-timestamp=true",
        *(["--no-cache"] if no_cache else []),
        ".",
    ]
    print(f"building {tag} for {platform}{' without cache' if no_cache else ''}", file=sys.stderr)
    completed = _run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(f"could not build {tag}:\n{completed.stderr[-3000:]}")
    return _image_id(tag)


def reproduce(
    dockerfiles: list[Path], *, platform: str, epoch: int, prefix: str, builder: str | None
) -> dict[str, Any]:
    images: dict[str, Any] = {}
    for dockerfile in dockerfiles:
        name = dockerfile.name.split(".")[0]
        tag = f"{prefix}/{name}:{VERSION}"
        first = build(
            dockerfile, tag, platform=platform, epoch=epoch, no_cache=False, builder=builder
        )
        rebuild_tag = f"{tag}-rebuild"
        second = build(
            dockerfile, rebuild_tag, platform=platform, epoch=epoch, no_cache=True, builder=builder
        )
        _run(["docker", "image", "rm", "--no-prune", rebuild_tag])
        images[name] = {
            "tag": tag,
            "dockerfile": dockerfile.as_posix(),
            "first_build": first,
            "second_build": second,
            "reproduced": first == second,
        }
        verdict = "reproduced" if first == second else "DIFFERS"
        print(f"{name}: {verdict} ({first} / {second})", file=sys.stderr)
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dockerfiles", nargs="+", type=Path, help="Dockerfiles to build twice")
    parser.add_argument("--platform", default="linux/amd64", help="the platform the claim is for")
    parser.add_argument("--prefix", default="oak-community", help="image name prefix")
    parser.add_argument("--builder", help="the buildx builder to use (a container driver)")
    parser.add_argument("--source-date-epoch", type=int, help="override the commit's time")
    parser.add_argument("--output", type=Path, help="write the JSON record here")
    arguments = parser.parse_args()

    if shutil.which("docker") is None:
        print("docker is required", file=sys.stderr)
        return 3
    try:
        epoch = (
            arguments.source_date_epoch
            if arguments.source_date_epoch is not None
            else source_date_epoch()
        )
        dockerfiles = [
            path if path.is_absolute() else ROOT / path for path in arguments.dockerfiles
        ]
        images = reproduce(
            dockerfiles,
            platform=arguments.platform,
            epoch=epoch,
            prefix=arguments.prefix,
            builder=arguments.builder,
        )
    except SystemExit as error:
        print(str(error), file=sys.stderr)
        return 3

    record = {
        "artifact_version": VERSION,
        "platform": arguments.platform,
        "source_commit": _git_output(["rev-parse", "HEAD"]) or "unknown",
        "source_date_epoch": epoch,
        "buildkit_version": buildkit_version(arguments.builder),
        "debian_snapshot": debian_snapshot(dockerfiles),
        "images": images,
        "reproduced": all(image["reproduced"] for image in images.values()),
    }
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {arguments.output}", file=sys.stderr)
    if not record["reproduced"]:
        print("an image did not reproduce", file=sys.stderr)
        return 1
    print(f"every image reproduced for {arguments.platform}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
