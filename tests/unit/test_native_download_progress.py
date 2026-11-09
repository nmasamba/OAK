# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-044: a native install says which file it is fetching and how far along it is, on a
terminal and nowhere else. `tests/integration/test_native_install.py` runs it through the
real runner."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import io
import itertools
import json
import os
import pty
import signal
import subprocess
import sys
import tarfile
import termios
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from oak.runner import native_network
from oak.runner.adapters import AdapterFailureError
from oak.runner.main import _size, _terminal_progress, _TerminalProgress
from oak.runner.native import DownloadProgress, NativeProcessAdapter

INSTALLATION = "installation." + "b" * 24
RELEASE_URL = "https://example.org/releases/download/b1/llama-b1-bin.tar.gz"
MODEL_URL = "https://example.org/models/tiny-q4.gguf?token=query-secret"
MODEL = b"GGUF" * 1000


def _release() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        member = tarfile.TarInfo("build/bin/llama-server")
        member.size = 4
        bundle.addfile(member, io.BytesIO(b"\x7fELF"))
    return buffer.getvalue()


FILES = {RELEASE_URL: _release(), MODEL_URL: MODEL}


def _artifact(role: str, source: str, format_: str) -> dict[str, Any]:
    content = FILES.get(source, MODEL)
    return {
        "role": role,
        "source": source,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "format": format_,
    }


def _component(node: str, port: int, *, model_url: str = MODEL_URL) -> dict[str, Any]:
    return {
        "node_id": node,
        "manifest_id": "component.fixture-local-model",
        "harness_kind": "llama_cpp_server",
        "artifacts": [
            _artifact("harness", RELEASE_URL, "tar.gz"),
            _artifact("model", model_url, "file"),
        ],
        "listen_port": port,
        "health_probe": {"path": "/health"},
    }


def _parameters(*components: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": "design-case.native",
        "target_id": "target.local-native",
        "installation_id": INSTALLATION,
        "consent_ref": {
            "id": "consent.native-installation",
            "version": "0.1.0",
            "digest": "sha256:" + "0" * 64,
        },
        "allowed_download_hosts": ["example.org"],
        "components": list(components) or [_component("node.answer", 18432)],
    }


def _keyed_probe(port: int, path: str, timeout: float) -> int:
    """`llama-server` with the installation's key (OAK-V1-045): its health path answers, and
    nothing else does for a request without the key."""

    return 200 if path == "/health" else 401


class _Response(io.BytesIO):
    def __init__(self, body: bytes, url: str) -> None:
        super().__init__(body)
        self._url = url

    def geturl(self) -> str:
        return self._url


def _adapter(root: Path, files: dict[str, bytes] = FILES, **keywords: Any) -> NativeProcessAdapter:
    """The real download loop over bytes held here, and a process that only stays alive."""

    def popen(argv: list[str], **options: Any) -> Any:
        return subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"], **options
        )

    ticks = itertools.count()
    return NativeProcessAdapter(
        root,
        fetch=functools.partial(
            native_network.fetch, opener=lambda url, timeout: _Response(files[url], url)
        ),
        popen=popen,
        probe=_keyed_probe,
        port_free=lambda port: True,
        sleep=lambda seconds: None,
        clock=lambda: float(next(ticks)),
        **keywords,
    )


def test_each_download_says_which_file_and_how_far_along_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_network, "CHUNK_BYTES", 1000)
    updates: list[DownloadProgress] = []

    _adapter(tmp_path / "native", progress=updates.append).apply(_parameters(), 120)

    assert [update.role for update in updates if update.finished] == ["harness", "model"]
    model = [update for update in updates if update.role == "model"]
    assert {(update.name, update.total) for update in model} == {("tiny-q4.gguf", len(MODEL))}
    assert [(update.written, update.finished) for update in model] == [
        (0, False),
        (1000, False),
        (2000, False),
        (3000, False),
        (4000, False),
        (4000, True),
    ]
    assert updates[0] == DownloadProgress(
        "harness", "llama-b1-bin.tar.gz", 0, len(FILES[RELEASE_URL])
    )


def test_reporting_progress_changes_nothing_the_runner_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_network, "CHUNK_BYTES", 1000)
    updates: list[DownloadProgress] = []

    unwatched = _adapter(tmp_path / "unwatched").apply(_parameters(), 120)
    watched = _adapter(tmp_path / "watched", progress=updates.append).apply(_parameters(), 120)

    assert updates, "the comparison means nothing unless progress was reported"
    assert watched == unwatched
    recorded = json.dumps(watched)
    for private in ("tiny-q4.gguf", "llama-b1-bin", "query-secret", "example.org", str(tmp_path)):
        assert private not in recorded


def test_a_download_that_fails_still_ends_its_report(tmp_path: Path) -> None:
    """The terminal's line is closed before whatever is printed next, and no update claims
    more than the profile acknowledged."""

    updates: list[DownloadProgress] = []
    oversized = {**FILES, MODEL_URL: MODEL + b"x"}

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(tmp_path / "native", oversized, progress=updates.append).apply(_parameters(), 120)

    assert caught.value.code == "OAK-NATIVE-SIZE"
    assert (updates[-1].role, updates[-1].finished) == ("model", True)
    assert all(update.written <= update.total for update in updates)


def test_a_download_refused_before_it_starts_ends_its_report_too(tmp_path: Path) -> None:
    updates: list[DownloadProgress] = []
    parameters = _parameters()
    parameters["allowed_download_hosts"] = ["elsewhere.example"]

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(tmp_path / "native", progress=updates.append).apply(parameters, 120)

    assert caught.value.code == "OAK-NATIVE-HOST"
    assert [(update.written, update.finished) for update in updates] == [(0, False), (0, True)]


@pytest.mark.parametrize(
    "failure", [BrokenPipeError(), OSError("the terminal is gone"), ValueError("a closed file")]
)
def test_a_reporter_that_cannot_write_fails_no_install(tmp_path: Path, failure: Exception) -> None:
    """Without this, `fetch` would call a lost terminal a failed download."""

    calls: list[DownloadProgress] = []

    def reporter(update: DownloadProgress) -> None:
        calls.append(update)
        raise failure

    evidence = _adapter(tmp_path / "native", progress=reporter).apply(_parameters(), 120)

    assert len(calls) > 2, "it is asked every time, and every failure is dropped"
    assert evidence[1]["content"]["passed"] is True


def test_only_a_real_download_is_reported(tmp_path: Path) -> None:
    """A second node links what the first verified, and a second apply finds the files."""

    updates: list[DownloadProgress] = []
    parameters = _parameters(_component("node.one", 18432), _component("node.two", 18433))
    adapter = _adapter(tmp_path / "native", progress=updates.append)

    adapter.apply(parameters, 120)
    adapter.apply(parameters, 120)

    assert [update.name for update in updates if update.finished] == [
        "llama-b1-bin.tar.gz",
        "tiny-q4.gguf",
    ]


class _Terminal(io.StringIO):
    """Keeps what it is shown, and always has room for more."""

    _room = os.open(os.devnull, os.O_WRONLY)

    def fileno(self) -> int:
        return self._room


def test_a_file_with_no_plain_name_is_shown_by_its_role(tmp_path: Path) -> None:
    source = "https://example.org/models/" + "x" * 121
    updates: list[DownloadProgress] = []

    _adapter(tmp_path / "native", {**FILES, source: MODEL}, progress=updates.append).apply(
        _parameters(_component("node.answer", 18432, model_url=source)), 120
    )

    terminal = _Terminal()
    show = _TerminalProgress(terminal)
    show(next(update for update in updates if update.role == "model"))
    assert terminal.getvalue() == "downloading the model (4,000 bytes)\n"


def test_a_terminal_sees_the_file_then_one_line_that_repaints() -> None:
    terminal = _Terminal()
    show = _TerminalProgress(terminal)
    update = DownloadProgress("model", "tiny-q4.gguf", 0, 491_400_032)

    show(update)
    show(replace(update, written=245_700_016))
    show(replace(update, written=491_400_032))
    show(replace(update, written=491_400_032, finished=True))

    assert terminal.getvalue() == (
        "downloading tiny-q4.gguf, the model (491.4 MB)\n"
        "\r  245.7 MB of 491.4 MB (50%)"
        "\r  491.4 MB of 491.4 MB (100%)"
        "\n"
    )


class _Buffered(_Terminal):
    """Shows only what was flushed."""

    def __init__(self) -> None:
        super().__init__()
        self.shown = ""

    def flush(self) -> None:
        self.shown = self.getvalue()


def test_each_repaint_is_flushed() -> None:
    """Python's line buffering also flushes a write holding a carriage return, so this is
    not what makes a repaint appear on stdout today; it only keeps that from being assumed."""

    terminal = _Buffered()
    show = _TerminalProgress(terminal)

    show(DownloadProgress("model", "tiny-q4.gguf", 1_000_000, 2_000_000))

    assert terminal.shown == "\r  1.0 MB of 2.0 MB (50%)"


@contextlib.contextmanager
def _within(seconds: float) -> Iterator[None]:
    """Fails a write that blocks, rather than hanging the whole suite on it."""

    def expired(signum: int, frame: Any) -> None:
        raise TimeoutError("a write to the terminal blocked")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def test_a_paused_terminal_does_not_stop_the_download() -> None:
    """A terminal paused with Ctrl-S stops taking output, and a write to it then blocks until
    Ctrl-Q. The reporter runs inside the download's loop, so that would stop the download,
    and the lease check with it: what the terminal cannot take at once is dropped instead."""

    leader, follower = pty.openpty()
    terminal = os.fdopen(follower, "w")
    show = _TerminalProgress(terminal)
    update = DownloadProgress("model", "tiny-q4.gguf", 0, 5000)
    termios.tcflow(follower, termios.TCOOFF)
    try:
        with _within(seconds=20):
            show(update)
            for written in range(1, 5000):
                show(replace(update, written=written))
            show(replace(update, written=5000, finished=True))
    finally:
        # The terminal's far end first: closing the near end could wait for it to drain.
        os.close(leader)
        with contextlib.suppress(OSError):
            terminal.close()


def test_a_shorter_line_leaves_nothing_of_the_longer_one_behind() -> None:
    terminal = _Terminal()
    show = _TerminalProgress(terminal)
    update = DownloadProgress("model", "big.gguf", 1, 1_200_000_000)

    show(replace(update, written=999_900_000))
    terminal.truncate(0)
    terminal.seek(0)
    show(replace(update, written=1_000_100_000))

    assert terminal.getvalue() == "\r  1.0 GB of 1.2 GB (83%)  "


def test_a_download_that_never_moved_adds_no_blank_line() -> None:
    terminal = _Terminal()
    show = _TerminalProgress(terminal)
    update = DownloadProgress("model", "tiny-q4.gguf", 0, 4000)

    show(update)
    show(replace(update, finished=True))

    assert terminal.getvalue() == "downloading tiny-q4.gguf, the model (4,000 bytes)\n"


def test_each_download_on_a_terminal_starts_a_fresh_line() -> None:
    terminal = _Terminal()
    show = _TerminalProgress(terminal)
    first = DownloadProgress("harness", "llama.tar.gz", 0, 2_000_000)
    second = DownloadProgress("model", "m.gguf", 0, 2_000_000)

    show(first)
    show(replace(first, written=2_000_000))
    show(replace(first, written=2_000_000, finished=True))
    show(second)
    show(replace(second, written=1_000_000))

    assert terminal.getvalue().endswith("\n\r  1.0 MB of 2.0 MB (50%)"), "no padding left over"


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (0, "0 bytes"),
        (999_999, "999,999 bytes"),
        (1_000_000, "1.0 MB"),
        (491_400_032, "491.4 MB"),
        (1_000_000_000, "1.0 GB"),
        (68_719_476_736, "68.7 GB"),
    ],
)
def test_sizes_read_the_way_the_examples_write_them(count: int, text: str) -> None:
    assert _size(count) == text


class _Stdout(io.StringIO):
    def __init__(self, *, terminal: bool) -> None:
        super().__init__()
        self._terminal = terminal

    def isatty(self) -> bool:
        return self._terminal


def test_progress_is_only_for_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Stdout(terminal=True))
    assert isinstance(_terminal_progress(), _TerminalProgress)
    monkeypatch.setattr(sys, "stdout", _Stdout(terminal=False))
    assert _terminal_progress() is None


def test_a_stdout_that_is_closed_or_absent_is_no_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """`oak-runner run-once >&-` leaves `sys.stdout` as None, and `print` copes with that."""

    monkeypatch.setattr(sys, "stdout", None)
    assert _terminal_progress() is None
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stdout", closed)
    assert _terminal_progress() is None
