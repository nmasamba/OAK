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

A build that fails is retried twice, after one and then three minutes: the snapshot
archive refuses requests when it is busy, and an index apt cannot fetch fails the build
rather than being skipped (`OAK-V1-038`). When two builds differ, the script names each
layer that differs, the Dockerfile step that made it and the files in it.

Exit codes: 0 every image reproduced, 1 an image did not, 3 a build could not run.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SNAPSHOT = re.compile(r"^ARG DEBIAN_SNAPSHOT=(?P<date>\d{8}T\d{6}Z)$", re.MULTILINE)
BUILD_ATTEMPTS = 3
RETRY_PAUSES_SECONDS = (60, 180)
DIFFERING_FILES_SHOWN = 20


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
    """The one snapshot date the Dockerfiles name; two dates are no claim at all."""

    dates = {
        match.group("date")
        for dockerfile in dockerfiles
        if (match := SNAPSHOT.search(dockerfile.read_text(encoding="utf-8")))
    }
    if len(dates) > 1:
        raise SystemExit(f"the Dockerfiles name different DEBIAN_SNAPSHOT dates: {sorted(dates)}")
    return next(iter(dates), None)


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
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """One build with every reproducibility flag, retried twice; returns the image ID."""

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
    for attempt in range(1, BUILD_ATTEMPTS + 1):
        completed = _run(command, cwd=ROOT)
        if completed.returncode == 0:
            return _image_id(tag)
        if attempt < BUILD_ATTEMPTS:
            pause = RETRY_PAUSES_SECONDS[attempt - 1]
            print(
                f"the build of {tag} failed (attempt {attempt} of {BUILD_ATTEMPTS}); "
                f"retrying in {pause} s:\n{completed.stderr[-1500:]}",
                file=sys.stderr,
            )
            sleep(pause)
    raise SystemExit(
        f"could not build {tag} in {BUILD_ATTEMPTS} attempts:\n{completed.stderr[-3000:]}"
    )


def _saved_image(path: Path) -> tuple[dict[str, Any], list[bytes]]:
    """The configuration and the layer blobs of an image `docker save` wrote."""

    with tarfile.open(path) as archive:
        manifest = json.load(_member(archive, "manifest.json"))[0]
        config = json.load(_member(archive, manifest["Config"]))
        layers = [_member(archive, name).read() for name in manifest["Layers"]]
    return config, layers


def _member(archive: tarfile.TarFile, name: str) -> IO[bytes]:
    member = archive.extractfile(name)
    if member is None:
        raise SystemExit(f"the saved image has no file {name}")
    return member


def _layer_entries(blob: bytes) -> dict[str, tuple[Any, ...]] | None:
    """Each path in a layer with what makes it differ; None for a format not read here."""

    if blob[:2] == b"\x1f\x8b":
        blob = gzip.decompress(blob)
    entries: dict[str, tuple[Any, ...]] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            for member in archive.getmembers():
                handle = archive.extractfile(member) if member.isfile() else None
                content = handle.read() if handle is not None else b""
                entries[member.name] = (
                    member.type,
                    member.mode,
                    member.uid,
                    member.gid,
                    member.mtime,
                    member.linkname,
                    hashlib.sha256(content).hexdigest(),
                )
    except tarfile.ReadError:
        return None
    return entries


def differences(first: Path, second: Path) -> list[str]:
    """Each differing layer of two saved images, the step that made it and its files."""

    first_config, first_layers = _saved_image(first)
    second_config, second_layers = _saved_image(second)
    steps = [
        str(entry.get("created_by", ""))
        for entry in first_config.get("history", [])
        if not entry.get("empty_layer")
    ]
    first_ids = first_config["rootfs"]["diff_ids"]
    second_ids = second_config["rootfs"]["diff_ids"]
    lines: list[str] = []
    if len(first_ids) != len(second_ids):
        lines.append(f"the images have {len(first_ids)} and {len(second_ids)} layers")
    for index, (one, other) in enumerate(zip(first_ids, second_ids, strict=False)):
        if one == other:
            continue
        step = steps[index] if index < len(steps) else "an unknown step"
        lines.append(f"layer {index} differs, made by: {' '.join(step.split())[:240]}")
        first_entries = _layer_entries(first_layers[index])
        second_entries = _layer_entries(second_layers[index])
        if first_entries is None or second_entries is None:
            lines.append("  (the layer is compressed in a format this script does not read)")
            continue
        changed = [
            name
            for name in sorted(first_entries.keys() | second_entries.keys())
            if first_entries.get(name) != second_entries.get(name)
        ]
        lines.extend(f"  {name}" for name in changed[:DIFFERING_FILES_SHOWN])
        if len(changed) > DIFFERING_FILES_SHOWN:
            lines.append(f"  and {len(changed) - DIFFERING_FILES_SHOWN} more")
    if not lines:
        lines.append("every layer matches; the image configurations differ")
    return lines


def explain(first_tag: str, second_tag: str) -> list[str]:
    """Save both images and say where they differ; a failure to save is said, not raised."""

    with tempfile.TemporaryDirectory(prefix="oak-reproduce-") as scratch:
        paths = []
        for tag in (first_tag, second_tag):
            path = Path(scratch) / (re.sub(r"[^A-Za-z0-9_.-]", "_", tag) + ".tar")
            completed = _run(["docker", "save", "--output", str(path), tag])
            if completed.returncode != 0:
                return [f"could not save {tag} to compare: {completed.stderr[-500:]}"]
            paths.append(path)
        return differences(paths[0], paths[1])


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
        if first != second:
            for line in explain(tag, rebuild_tag):
                print(f"{name}: {line}", file=sys.stderr)
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
        snapshot = debian_snapshot(dockerfiles)
        buildkit = buildkit_version(arguments.builder)
        if buildkit == "unknown":
            raise SystemExit(
                "the builder's BuildKit version could not be read, so no claim can name it; "
                "pass --builder for a buildx builder"
            )
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
        "buildkit_version": buildkit,
        "debian_snapshot": snapshot,
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
