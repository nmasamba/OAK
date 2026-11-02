# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: the native adapter installs verified artifacts, proves them, stops them,
and removes exactly what it installed."""

from __future__ import annotations

import hashlib
import io
import json
import os
import resource
import socket
import stat
import subprocess
import sys
import tarfile
import zipfile
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

from oak.domain import OAKError
from oak.runner.adapters import AdapterFailureError
from oak.runner.native import (
    MARKER,
    START_FILE,
    NativeArtifact,
    NativeComponent,
    NativeProcessAdapter,
    _unpack_tar,
    _unpack_zip,
    child_limits,
    harness_shape_problem,
)

INSTALLATION = "installation." + "a" * 24
STAND_IN = resources.files("oak.runner.stand_in").joinpath("http_server.py").read_bytes()
STAND_IN_DIGEST = "sha256:" + hashlib.sha256(STAND_IN).hexdigest()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _parameters(
    *, port: int, digest: str = STAND_IN_DIGEST, size: int | None = None
) -> dict[str, Any]:
    return {
        "case_id": "design-case.native",
        "target_id": "target.local-native",
        "installation_id": INSTALLATION,
        "consent_ref": {
            "id": "consent.native-installation",
            "version": "0.1.0",
            "digest": "sha256:" + "0" * 64,
        },
        "allowed_download_hosts": [],
        "components": [
            {
                "node_id": "node.answer",
                "manifest_id": "component.fixture-local-model",
                "harness_kind": "oak_stand_in",
                "artifacts": [
                    {
                        "role": "harness",
                        "source": "oak-stand-in:http-server",
                        "sha256": digest,
                        "size_bytes": size if size is not None else len(STAND_IN),
                        "format": "file",
                    }
                ],
                "listen_port": port,
                "health_probe": {"path": "/health"},
            }
        ],
    }


def test_the_stand_in_is_installed_proven_stopped_and_removed(tmp_path: Path) -> None:
    root = tmp_path / "native"
    canary = tmp_path / "canary.txt"
    canary.write_text("stays", encoding="utf-8")
    port = _free_port()
    adapter = NativeProcessAdapter(root)

    evidence = adapter.apply(_parameters(port=port), 120)

    status, test, metric = evidence
    assert status["content"]["mode"] == "native"
    assert status["content"]["installation"][0]["artifacts"][0]["verified"] is True
    assert test["category"] == "test_result"
    assert (test["content"]["passed"], test["content"]["stopped"]) == (True, True)
    assert test["content"]["smoke_test"][0]["http_status"] == 200
    assert metric["content"]["readiness"][0]["seconds_to_ready"] > 0
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0, "nothing is left listening"
    directory = root / INSTALLATION
    assert stat.S_IMODE(os.lstat(directory).st_mode) == 0o700
    assert json.loads((directory / MARKER).read_text())["state"] == "installed"
    # Nothing is left running, so the user is told how to start each component.
    assert status["content"]["running"] is False
    assert status["content"]["start_instructions"] == START_FILE
    instructions = directory / START_FILE
    assert stat.S_IMODE(os.lstat(instructions).st_mode) == 0o600
    text = instructions.read_text(encoding="utf-8")
    assert text.startswith("Nothing from this installation is running.")
    assert f"node.answer (oak_stand_in) on 127.0.0.1:{port}" in text
    assert f"--port {port}" in text

    again = adapter.apply(_parameters(port=port), 120)
    assert again[1]["content"]["passed"] is True, "a second apply adopts its own installation"

    removed = adapter.destroy(_parameters(port=port), 120)
    assert removed["content"] == {"installation_id": INSTALLATION, "removed": True, "absent": True}
    assert not directory.exists()
    assert canary.read_text(encoding="utf-8") == "stays", "the uninstall removes nothing else"
    assert adapter.destroy(_parameters(port=port), 120)["content"]["removed"] is False


def test_a_digest_or_size_the_profile_did_not_acknowledge_never_runs(tmp_path: Path) -> None:
    started: list[Any] = []

    def popen(*arguments: Any, **keywords: Any) -> Any:
        started.append(arguments)
        raise AssertionError("nothing may start")

    adapter = NativeProcessAdapter(tmp_path / "native", popen=popen)
    for parameters in (
        _parameters(port=_free_port(), digest="sha256:" + "1" * 64),
        _parameters(port=_free_port(), size=len(STAND_IN) + 1),
    ):
        with pytest.raises(AdapterFailureError) as caught:
            adapter.apply(parameters, 120)
        assert caught.value.code == "OAK-NATIVE-DIGEST"
        assert caught.value.created == (INSTALLATION,)
        adapter.compensate(parameters, caught.value.created, 120)
    assert started == []
    assert not (tmp_path / "native" / INSTALLATION).exists()


def test_a_directory_it_did_not_mark_is_never_adopted_or_removed(tmp_path: Path) -> None:
    root = tmp_path / "native"
    foreign = root / INSTALLATION
    foreign.mkdir(parents=True)
    (foreign / "keep.txt").write_text("mine", encoding="utf-8")
    adapter = NativeProcessAdapter(root)

    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(_parameters(port=_free_port()), 120)
    assert caught.value.code == "OAK-NATIVE-OWNERSHIP"
    assert caught.value.created == (), "it created nothing, so compensation removes nothing"
    with pytest.raises(OAKError) as refused:
        adapter.destroy(_parameters(port=_free_port()), 120)
    assert refused.value.code == "OAK-NATIVE-OWNERSHIP"

    (foreign / MARKER).write_text(json.dumps({"installation_id": "installation." + "b" * 24}))
    with pytest.raises(OAKError) as other:
        adapter.destroy(_parameters(port=_free_port()), 120)
    assert other.value.code == "OAK-NATIVE-OWNERSHIP"
    assert (foreign / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_a_link_in_place_of_the_installation_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "native"
    root.mkdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    (root / INSTALLATION).symlink_to(target, target_is_directory=True)
    with pytest.raises(OAKError) as caught:
        NativeProcessAdapter(root).destroy(_parameters(port=_free_port()), 120)
    assert caught.value.code == "OAK-NATIVE-OWNERSHIP"
    assert target.exists()


def test_a_component_that_never_answers_is_stopped_and_fails(tmp_path: Path) -> None:
    clock = iter(float(second) for second in range(0, 1000))
    adapter = NativeProcessAdapter(
        tmp_path / "native",
        probe=lambda port, path, timeout: None,
        sleep=lambda seconds: None,
        clock=lambda: next(clock),
    )
    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(_parameters(port=_free_port()), 120)
    assert caught.value.code == "OAK-NATIVE-SMOKE"
    test = next(item for item in caught.value.evidence if item["category"] == "test_result")
    assert test["content"]["passed"] is False
    assert test["content"]["stopped"] is True, "a failed smoke test still stops the process"


def test_an_unsupported_platform_installs_nothing(tmp_path: Path) -> None:
    adapter = NativeProcessAdapter(tmp_path / "native", platform_key=("windows", "amd64"))
    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(_parameters(port=_free_port()), 120)
    assert caught.value.code == "OAK-NATIVE-PLATFORM"
    assert not (tmp_path / "native").exists()


def _zip(entries: list[tuple[str, bytes, int]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content, mode in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            bundle.writestr(info, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "entries",
    [
        [("../escape", b"x", stat.S_IFREG | 0o644)],
        [("/absolute", b"x", stat.S_IFREG | 0o644)],
        [("bin/link", b"/etc/passwd", stat.S_IFLNK | 0o777)],
        [("bin\\..\\escape", b"x", stat.S_IFREG | 0o644)],
    ],
)
def test_a_zip_member_that_escapes_or_links_is_refused(
    tmp_path: Path, entries: list[tuple[str, bytes, int]]
) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(_zip(entries))
    base = tmp_path / "unpacked"
    base.mkdir()
    with pytest.raises(OAKError) as caught:
        _unpack_zip(archive, base)
    assert caught.value.code == "OAK-NATIVE-ARCHIVE"
    assert not (tmp_path / "escape").exists()


def test_a_tar_member_that_links_is_refused_and_a_plain_one_unpacks(tmp_path: Path) -> None:
    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as bundle:
        link = tarfile.TarInfo("bin/llama-server")
        link.type = tarfile.SYMTYPE
        link.linkname = "/bin/sh"
        bundle.addfile(link)
    base = tmp_path / "linked"
    base.mkdir()
    with pytest.raises(OAKError) as caught:
        _unpack_tar(linked, base)
    assert caught.value.code == "OAK-NATIVE-ARCHIVE"

    plain = tmp_path / "plain.tar.gz"
    with tarfile.open(plain, "w:gz") as bundle:
        member = tarfile.TarInfo("build/bin/llama-server")
        member.size = 4
        bundle.addfile(member, io.BytesIO(b"\x7fELF"))
    out = tmp_path / "plain"
    out.mkdir()
    _unpack_tar(plain, out)
    target = out / "build" / "bin" / "llama-server"
    assert target.read_bytes() == b"\x7fELF"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600, "nothing is executable until chosen"


@pytest.mark.parametrize(
    ("kind", "artifacts", "problem"),
    [
        ("oak_stand_in", [("harness", "oak-stand-in:other", "file")], "a file OAK ships"),
        ("oak_stand_in", [("harness", "oak-stand-in:http-server", "zip")], "is a file"),
        ("llama_cpp_server", [("harness", "https://h/x.zip", "zip")], "one model file"),
        (
            "llama_cpp_server",
            [("harness", "https://h/x", "file"), ("model", "https://h/m.gguf", "file")],
            "release archive",
        ),
        (
            "llama_cpp_server",
            [("harness", "oak-stand-in:http-server", "zip"), ("model", "https://h/m", "file")],
            "downloads",
        ),
    ],
)
def test_each_harness_kind_names_the_artifacts_it_needs(
    kind: str, artifacts: list[tuple[str, str, str]], problem: str
) -> None:
    component = NativeComponent(
        node_id="node.a",
        manifest_id="component.a",
        harness_kind=kind,
        artifacts=tuple(
            NativeArtifact(role, source, "sha256:" + "0" * 64, 1, fmt)
            for role, source, fmt in artifacts
        ),
        listen_port=8090,
        probe_path="/health",
    )
    message = harness_shape_problem(component)
    assert message is not None and problem in message


# Records the limits the child was given, then becomes the component it was asked to run.
RECORDER = """
import json, os, resource, sys
argv = json.loads(sys.argv[1])
names = ("RLIMIT_CORE", "RLIMIT_NOFILE", "RLIMIT_FSIZE")
with open(sys.argv[2], "w") as out:
    json.dump({name: list(resource.getrlimit(getattr(resource, name))) for name in names}, out)
os.execv(argv[0], argv)
"""


def test_each_component_runs_under_the_ceilings_its_evidence_records(tmp_path: Path) -> None:
    record = tmp_path / "limits.json"

    def popen(argv: list[str], **keywords: Any) -> Any:
        recorder = [sys.executable, "-I", "-c", RECORDER, json.dumps(list(argv)), str(record)]
        return subprocess.Popen(recorder, **keywords)

    port = _free_port()
    evidence = NativeProcessAdapter(tmp_path / "native", popen=popen).apply(
        _parameters(port=port), 120
    )

    row = evidence[1]["content"]["smoke_test"][0]
    assert row["passed"] is True, row
    measured = json.loads(record.read_text(encoding="utf-8"))
    assert measured["RLIMIT_CORE"] == [0, 0] and row["resource_limits"]["core_file_bytes"] == 0
    assert measured["RLIMIT_NOFILE"][0] == row["resource_limits"]["open_files"] <= 4096
    assert measured["RLIMIT_FSIZE"][0] == row["resource_limits"]["file_bytes"] <= 2 * 2**30
    assert row["not_limited"] == ["memory", "cpu_time", "processes"]


def test_the_ceilings_only_ever_lower_the_runners_own_limits() -> None:
    planned = child_limits()

    assert set(planned) == {"core_file_bytes", "open_files", "file_bytes"}
    for which, (soft, hard) in planned.values():
        current_soft, current_hard = resource.getrlimit(which)
        assert soft <= hard
        if current_soft != resource.RLIM_INFINITY:
            assert soft <= current_soft
        if current_hard != resource.RLIM_INFINITY:
            assert hard <= current_hard


def _tar(path: Path, members: list[tarfile.TarInfo | tuple[str, bytes]]) -> Path:
    with tarfile.open(path, "w:gz") as bundle:
        for member in members:
            if isinstance(member, tarfile.TarInfo):
                bundle.addfile(member)
            else:
                name, content = member
                info = tarfile.TarInfo(name)
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
    return path


def _link(name: str, target: str, *, hard: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.LNKTYPE if hard else tarfile.SYMTYPE
    info.linkname = target
    return info


def test_a_release_s_library_links_unpack_as_copies_and_never_as_links(tmp_path: Path) -> None:
    """A versioned library and its links, as a release built with CMake ships them; a link
    may come before the file it names."""

    archive = _tar(
        tmp_path / "release.tar.gz",
        [
            _link("./build/bin/libllama.dylib", "libllama.0.dylib"),
            _link("./build/bin/libllama.0.dylib", "../bin/libllama.0.0.1.dylib"),
            ("./build/bin/libllama.0.0.1.dylib", b"library"),
            ("./build/bin/llama-server", b"\x7fELF"),
            _link("build/bin/hard-copy", "build/bin/llama-server", hard=True),
        ],
    )
    out = tmp_path / "unpacked"
    out.mkdir()

    _unpack_tar(archive, out)

    folder = out / "build" / "bin"
    for name, content in (
        ("libllama.dylib", b"library"),
        ("libllama.0.dylib", b"library"),
        ("libllama.0.0.1.dylib", b"library"),
        ("hard-copy", b"\x7fELF"),
    ):
        path = folder / name
        assert not path.is_symlink() and path.read_bytes() == content, name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not any(path.is_symlink() for path in out.rglob("*"))


@pytest.mark.parametrize(
    "members",
    [
        [_link("bin/x", "../../outside")],
        [("real", b"x"), _link("bin/x", "../../real")],
        [_link("bin/x", "/etc/passwd")],
        [_link("bin/x", "missing")],
        [("lib/real", b"x"), _link("bin/lib", "../lib")],
        [_link("bin/a", "b"), _link("bin/b", "a")],
        [_link("bin/x", "../../outside", hard=True)],
    ],
)
def test_a_link_that_leaves_names_nothing_or_loops_is_refused(
    tmp_path: Path, members: list[tarfile.TarInfo | tuple[str, bytes]]
) -> None:
    archive = _tar(tmp_path / "release.tar.gz", members)
    out = tmp_path / "unpacked"
    out.mkdir()

    with pytest.raises(OAKError) as caught:
        _unpack_tar(archive, out)

    assert caught.value.code == "OAK-NATIVE-ARCHIVE"
    assert not (tmp_path / "outside").exists()
    assert not any(path.is_symlink() for path in out.rglob("*"))


def test_a_zip_link_inside_the_archive_unpacks_as_a_copy(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(
        _zip(
            [
                ("bin/libggml.0.dylib", b"library", stat.S_IFREG | 0o644),
                ("bin/libggml.dylib", b"libggml.0.dylib", stat.S_IFLNK | 0o777),
            ]
        )
    )
    out = tmp_path / "unpacked"
    out.mkdir()

    _unpack_zip(archive, out)

    copy = out / "bin" / "libggml.dylib"
    assert not copy.is_symlink() and copy.read_bytes() == b"library"


def test_an_archive_that_cannot_be_unpacked_fails_the_install_it_started(
    tmp_path: Path,
) -> None:
    """A duplicate member, or a truncated archive, is the archive's fault: nothing runs, and
    the install it started is removed."""

    duplicated = _tar(
        tmp_path / "duplicated.tar.gz",
        [("build/bin/llama-server", b"one"), ("build/bin/llama-server", b"two")],
    ).read_bytes()
    truncated = duplicated[: len(duplicated) // 2]
    for content in (duplicated, truncated):
        digest = "sha256:" + hashlib.sha256(content).hexdigest()

        def fetch(
            source: str,
            destination: Path,
            *,
            archive: bytes = content,
            named: str = digest,
            **_: Any,
        ) -> tuple[int, str]:
            destination.write_bytes(archive)
            return len(archive), named

        def popen(*arguments: Any, **keywords: Any) -> Any:
            raise AssertionError("nothing may start")

        parameters = _parameters(port=_free_port())
        parameters["allowed_download_hosts"] = ["example.org"]
        parameters["components"][0].update(
            harness_kind="llama_cpp_server",
            artifacts=[
                {
                    "role": "harness",
                    "source": "https://example.org/llama.tar.gz",
                    "sha256": digest,
                    "size_bytes": len(content),
                    "format": "tar.gz",
                },
                {
                    "role": "model",
                    "source": "https://example.org/model.gguf",
                    "sha256": digest,
                    "size_bytes": len(content),
                    "format": "file",
                },
            ],
        )
        adapter = NativeProcessAdapter(tmp_path / "native", fetch=fetch, popen=popen)
        with pytest.raises(AdapterFailureError) as caught:
            adapter.apply(parameters, 120)
        assert caught.value.code == "OAK-NATIVE-ARCHIVE"
        adapter.compensate(parameters, caught.value.created, 120)
        assert not (tmp_path / "native" / INSTALLATION).exists()
