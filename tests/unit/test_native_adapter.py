# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: the native adapter installs verified artifacts, proves them, stops them,
and removes exactly what it installed."""

from __future__ import annotations

import hashlib
import io
import json
import os
import resource
import shutil
import signal
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


# -- what the closing review found (OAK-V1-043) ------------------------------------------

ONE_ANSWER = """
import http.server, sys
port = int(sys.argv[sys.argv.index("--port") + 1])
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def log_message(self, *args):
        pass
http.server.HTTPServer(("127.0.0.1", port), Handler).handle_request()
"""

# Starts a child that ignores SIGTERM, records its pid, then becomes the real component.
FORKER = """
import os, signal, sys, time
record, argv = sys.argv[1], sys.argv[2:]
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(60)
    os._exit(0)
with open(record, "w") as out:
    out.write(str(child))
os.execv(argv[0], argv)
"""

# Starts a child, records its pid, and exits at once, leaving the child in its group.
LEAVER = """
import os, sys, time
child = os.fork()
if child == 0:
    time.sleep(60)
    os._exit(0)
with open(sys.argv[1], "w") as out:
    out.write(str(child))
"""


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_component_that_dies_after_answering_never_passes(tmp_path: Path) -> None:
    def popen(argv: list[str], **keywords: Any) -> Any:
        return subprocess.Popen([sys.executable, "-I", "-c", ONE_ANSWER, *argv[1:]], **keywords)

    adapter = NativeProcessAdapter(tmp_path / "native", popen=popen)
    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(_parameters(port=_free_port()), 120)

    assert caught.value.code == "OAK-NATIVE-SMOKE"
    row = caught.value.evidence[1]["content"]["smoke_test"][0]
    assert row["passed"] is False and row["stopped"] is True


def test_a_port_already_in_use_is_refused_before_anything_starts(tmp_path: Path) -> None:
    def popen(*arguments: Any, **keywords: Any) -> Any:
        raise AssertionError("nothing may start")

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        with pytest.raises(AdapterFailureError) as caught:
            NativeProcessAdapter(tmp_path / "native", popen=popen).apply(
                _parameters(port=port), 120
            )

    assert caught.value.code == "OAK-NATIVE-START"
    assert f"port {port}" in caught.value.message


def test_a_child_that_ignores_sigterm_is_killed_with_its_group(tmp_path: Path) -> None:
    record = tmp_path / "child.pid"

    def popen(argv: list[str], **keywords: Any) -> Any:
        wrapped = [sys.executable, "-I", "-c", FORKER, str(record), *argv]
        return subprocess.Popen(wrapped, **keywords)

    evidence = NativeProcessAdapter(tmp_path / "native", popen=popen).apply(
        _parameters(port=_free_port()), 120
    )

    assert evidence[1]["content"]["passed"] is True
    assert evidence[1]["content"]["stopped"] is True
    assert _gone(int(record.read_text()))


def test_a_child_left_behind_by_a_component_that_exits_is_killed(tmp_path: Path) -> None:
    record = tmp_path / "child.pid"

    def popen(argv: list[str], **keywords: Any) -> Any:
        return subprocess.Popen([sys.executable, "-I", "-c", LEAVER, str(record)], **keywords)

    with pytest.raises(AdapterFailureError) as caught:
        NativeProcessAdapter(tmp_path / "native", popen=popen).apply(
            _parameters(port=_free_port()), 120
        )

    assert caught.value.code == "OAK-NATIVE-SMOKE"
    assert caught.value.evidence[1]["content"]["stopped"] is True
    assert _gone(int(record.read_text()))


SIGNALLED = """
import json, os, signal, subprocess, sys
from pathlib import Path
from oak.runner.native import NativeProcessAdapter

record, parameters, root = Path(sys.argv[1]), json.loads(sys.argv[2]), Path(sys.argv[3])

def popen(argv, **keywords):
    process = subprocess.Popen(argv, **keywords)
    record.write_text(str(process.pid))
    return process

def sleep(seconds):
    os.kill(os.getpid(), signal.SIGTERM)

adapter = NativeProcessAdapter(root, popen=popen, sleep=sleep, probe=lambda *args: None)
adapter.apply(parameters, 120)
"""


def test_a_runner_told_to_stop_during_a_check_stops_the_component_first(tmp_path: Path) -> None:
    """SIGTERM's default would end the runner without its `finally`, and leave the
    component running: it is turned into an exit that stops the component on the way."""

    record = tmp_path / "component.pid"
    parameters = _parameters(port=_free_port())
    ran = subprocess.run(
        [
            sys.executable,
            "-c",
            SIGNALLED,
            str(record),
            json.dumps(parameters),
            str(tmp_path / "native"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert ran.returncode == 128 + signal.SIGTERM, ran.stderr
    assert _gone(int(record.read_text()))


def test_a_re_apply_runs_a_fresh_unpack_of_the_verified_archive(tmp_path: Path) -> None:
    archive = _tar(tmp_path / "release.tar.gz", [("bin/llama-server", b"original")])
    content = archive.read_bytes()
    digest = "sha256:" + hashlib.sha256(content).hexdigest()

    def fetch(source: str, destination: Path, **_: Any) -> tuple[int, str]:
        destination.write_bytes(content)
        return len(content), digest

    adapter = NativeProcessAdapter(tmp_path / "native", fetch=fetch)
    artifact = NativeArtifact(
        role="harness",
        source="https://example.org/release.tar.gz",
        sha256=digest,
        size_bytes=len(content),
        format="tar.gz",
    )
    component = tmp_path / "component"
    component.mkdir()
    tree = adapter._obtain(artifact, component, frozenset({"example.org"}))
    (tree / "bin" / "llama-server").write_bytes(b"changed after the check")

    again = adapter._obtain(artifact, component, frozenset({"example.org"}))

    assert (again / "bin" / "llama-server").read_bytes() == b"original"


def test_an_installation_never_exists_without_its_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "native"
    original = NativeProcessAdapter._write_marker
    calls: list[str] = []

    def failing(directory: Path, installation: Any, *, state: str) -> None:
        calls.append(state)
        if len(calls) == 1:
            raise OSError("no space left on device")
        original(directory, installation, state=state)

    monkeypatch.setattr(NativeProcessAdapter, "_write_marker", staticmethod(failing))
    adapter = NativeProcessAdapter(root)
    parameters = _parameters(port=_free_port())

    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(parameters, 120)
    assert caught.value.code == "OAK-NATIVE-IO" and caught.value.created == ()
    assert not (root / INSTALLATION).exists()

    adapter.apply(parameters, 120)
    assert json.loads((root / INSTALLATION / MARKER).read_text())["state"] == "installed"
    assert not (root / f".{INSTALLATION}.creating").exists()


def test_a_removal_that_fails_part_way_is_finished_by_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "native"
    adapter = NativeProcessAdapter(root)
    parameters = _parameters(port=_free_port())
    adapter.apply(parameters, 120)
    real = shutil.rmtree
    failures = [OSError("device busy")]

    def flaky(path: Any, *arguments: Any, **keywords: Any) -> None:
        if failures:
            raise failures.pop()
        real(path, *arguments, **keywords)

    monkeypatch.setattr("oak.runner.native.shutil.rmtree", flaky)
    with pytest.raises(OAKError) as caught:
        adapter.destroy(parameters, 120)
    assert caught.value.code == "OAK-NATIVE-UNINSTALL"
    assert not (root / INSTALLATION).exists(), "the installation's path is already free"

    finished = adapter.destroy(parameters, 120)
    assert finished["content"]["absent"] is True
    assert list(root.iterdir()) == []


FAKE_LLAMA = """
import http.server, sys
arguments = sys.argv[1:]
assert arguments[arguments.index("--host") + 1] == "127.0.0.1"
port = int(arguments[arguments.index("--port") + 1])
with open(arguments[arguments.index("--model") + 1], "rb") as model:
    assert model.read() == b"GGUF model"
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def log_message(self, *args):
        pass
http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def test_a_llama_cpp_release_installs_offline_and_each_file_downloads_once(
    tmp_path: Path,
) -> None:
    """The `llama_cpp_server` kind end to end, with a release shaped like llama.cpp's (a
    versioned library and its link) and two nodes sharing the harness and the model."""

    release = _tar(
        tmp_path / "llama.tar.gz",
        [
            ("build/bin/llama-server", FAKE_LLAMA.encode("utf-8")),
            ("build/bin/libllama.0.0.1.dylib", b"library"),
            _link("build/bin/libllama.dylib", "libllama.0.0.1.dylib"),
        ],
    ).read_bytes()
    files = {
        "https://example.org/llama.tar.gz": release,
        "https://example.org/model.gguf": b"GGUF model",
    }
    fetched: list[str] = []

    def fetch(source: str, destination: Path, **_: Any) -> tuple[int, str]:
        fetched.append(source)
        destination.write_bytes(files[source])
        return len(files[source]), "sha256:" + hashlib.sha256(files[source]).hexdigest()

    def popen(argv: list[str], **keywords: Any) -> Any:
        return subprocess.Popen([sys.executable, "-I", *argv], **keywords)

    def artifact(role: str, source: str, format_: str) -> dict[str, Any]:
        content = files[source]
        return {
            "role": role,
            "source": source,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "format": format_,
        }

    parameters = _parameters(port=_free_port())
    parameters["allowed_download_hosts"] = ["example.org"]
    template = parameters["components"][0]
    parameters["components"] = [
        {
            **template,
            "node_id": node,
            "harness_kind": "llama_cpp_server",
            "artifacts": [
                artifact("harness", "https://example.org/llama.tar.gz", "tar.gz"),
                artifact("model", "https://example.org/model.gguf", "file"),
            ],
            "listen_port": _free_port(),
        }
        for node in ("node.generation", "node.review")
    ]

    evidence = NativeProcessAdapter(tmp_path / "native", fetch=fetch, popen=popen).apply(
        parameters, 120
    )

    tested = evidence[1]["content"]
    assert tested["passed"] is True and tested["stopped"] is True
    assert sorted(fetched) == sorted(files), "each file downloads once per installation"
    trees = list((tmp_path / "native" / INSTALLATION).glob("*/harness/unpacked/build/bin"))
    assert len(trees) == 2
    for tree in trees:
        assert (tree / "libllama.dylib").read_bytes() == b"library"
        assert not (tree / "libllama.dylib").is_symlink()
