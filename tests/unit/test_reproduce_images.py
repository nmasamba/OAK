# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-038: a failed image build is retried, and a mismatch names its layer and files."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts import reproduce_images as reproduce

EPOCH = 1793309759


def _tar(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = EPOCH
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _saved(path: Path, layers: list[bytes], steps: list[dict[str, Any]]) -> Path:
    """An image as `docker save` writes it: a manifest, a configuration and layer blobs."""

    def diff_id(blob: bytes) -> str:
        plain = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
        return f"sha256:{hashlib.sha256(plain).hexdigest()}"

    config = {"rootfs": {"type": "layers", "diff_ids": [diff_id(b) for b in layers]}}
    config["history"] = steps
    names = [f"blobs/sha256/layer{index}" for index in range(len(layers))]
    manifest = [{"Config": "blobs/sha256/config", "Layers": names}]
    members = {
        "blobs/sha256/config": json.dumps(config).encode(),
        **dict(zip(names, layers, strict=True)),
        "manifest.json": json.dumps(manifest).encode(),
    }
    path.write_bytes(_tar(members))
    return path


STEPS = [
    {"created_by": "COPY base / # buildkit"},
    {"created_by": "ARG DEBIAN_SNAPSHOT=20261029T000000Z", "empty_layer": True},
    {"created_by": "RUN |1 DEBIAN_SNAPSHOT=20261029T000000Z /bin/sh -c apt-get upgrade"},
    {"created_by": "COPY /app/.venv /app/.venv # buildkit"},
]


def test_a_mismatch_names_the_layer_the_step_that_made_it_and_its_files(tmp_path: Path) -> None:
    base = _tar({"etc/os-release": b"trixie"})
    venv = gzip.compress(_tar({"app/.venv/pyvenv.cfg": b"home = /usr/local/bin"}), mtime=0)
    first = _saved(
        tmp_path / "first.tar",
        [base, _tar({"usr/lib/libssl.so.3": b"3.5.6", "var/lib/dpkg/status": b"a"}), venv],
        STEPS,
    )
    second = _saved(
        tmp_path / "second.tar",
        [base, _tar({"usr/lib/libssl.so.3": b"3.5.7", "var/lib/dpkg/status": b"a"}), venv],
        STEPS,
    )

    assert reproduce.differences(first, second) == [
        "layer 1 differs, made by: RUN |1 DEBIAN_SNAPSHOT=20261029T000000Z /bin/sh -c apt-get "
        "upgrade",
        "  usr/lib/libssl.so.3",
    ]


def test_a_file_present_in_one_build_only_and_a_gzip_layer_are_read(tmp_path: Path) -> None:
    first = _saved(
        tmp_path / "first.tar",
        [gzip.compress(_tar({"a": b"1"}), mtime=0)],
        [{"created_by": "COPY a /"}],
    )
    second = _saved(
        tmp_path / "second.tar",
        [gzip.compress(_tar({"a": b"1", "b": b"2"}), mtime=0)],
        [{"created_by": "COPY a /"}],
    )

    assert reproduce.differences(first, second) == ["layer 0 differs, made by: COPY a /", "  b"]


def test_an_unreadable_layer_and_matching_layers_are_said_plainly(tmp_path: Path) -> None:
    same = _saved(tmp_path / "same.tar", [_tar({"a": b"1"})], [{"created_by": "COPY a /"}])
    assert reproduce.differences(same, same) == [
        "every layer matches; the image configurations differ"
    ]
    odd = _saved(tmp_path / "odd.tar", [b"\x28\xb5\x2f\xfd zstd"], [{"created_by": "COPY a /"}])
    assert reproduce.differences(same, odd)[1] == (
        "  (the layer is compressed in a format this script does not read)"
    )


def _runner(codes: list[int], calls: list[list[str]]) -> Any:
    outcomes = iter(codes)

    def run(command: list[str], **keywords: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, next(outcomes), "", "TooManyRequests 503")

    return run


def test_a_failed_build_is_retried_after_one_and_then_three_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    pauses: list[float] = []
    monkeypatch.setattr(reproduce, "_run", _runner([1, 1, 0], calls))
    monkeypatch.setattr(reproduce, "_image_id", lambda tag: "sha256:" + "a" * 64)

    image = reproduce.build(
        Path("deploy/images/api.Dockerfile"),
        "oak-test/api:0",
        platform="linux/arm64",
        epoch=EPOCH,
        no_cache=True,
        builder="oak-reproduce",
        sleep=pauses.append,
    )

    assert image == "sha256:" + "a" * 64
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert pauses == [60, 180]


def test_a_build_that_keeps_failing_stops_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    pauses: list[float] = []
    monkeypatch.setattr(reproduce, "_run", _runner([1, 1, 1], calls))

    with pytest.raises(SystemExit, match="in 3 attempts:\nTooManyRequests 503"):
        reproduce.build(
            Path("deploy/images/api.Dockerfile"),
            "oak-test/api:0",
            platform="linux/arm64",
            epoch=EPOCH,
            no_cache=True,
            builder=None,
            sleep=pauses.append,
        )
    assert len(calls) == 3
    assert pauses == [60, 180]
