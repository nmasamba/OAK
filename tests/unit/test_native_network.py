# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-041: the runner's one network module reaches only the hosts a profile names."""

from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from oak.domain import OAKError
from oak.runner import native_network
from oak.runner.native_network import _AllowedRedirects, artifact_name, fetch, https_host

ALLOWED = frozenset({"github.com", "objects.githubusercontent.com"})


class _Response(io.BytesIO):
    def __init__(self, body: bytes, final: str) -> None:
        super().__init__(body)
        self._final = final

    def geturl(self) -> str:
        return self._final


def _opener(body: bytes, final: str | None = None) -> Any:
    calls: list[str] = []

    def open_url(url: str, timeout: float) -> _Response:
        calls.append(url)
        return _Response(body, final or url)

    open_url.calls = calls  # type: ignore[attr-defined]
    return open_url


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://github.com/x", "github.com"),
        ("https://GitHub.com/x", "github.com"),
        ("http://github.com/x", None),
        ("https://user:secret@github.com/x", None),
        ("file:///etc/passwd", None),
        ("https://", None),
    ],
)
def test_only_an_https_url_without_credentials_has_a_host(url: str, host: str | None) -> None:
    assert https_host(url) == host


def test_a_host_the_profile_does_not_name_is_never_contacted(tmp_path: Path) -> None:
    opener = _opener(b"x")
    with pytest.raises(OAKError) as caught:
        fetch(
            "https://example.com/model.gguf",
            tmp_path / "f",
            allowed_hosts=ALLOWED,
            expected_size=1,
            timeout=1,
            opener=opener,
        )
    assert caught.value.code == "OAK-NATIVE-HOST"
    assert opener.calls == [], "refused before any connection"


def test_a_download_that_ends_elsewhere_is_refused(tmp_path: Path) -> None:
    opener = _opener(b"x", final="https://evil.example/x")
    with pytest.raises(OAKError) as caught:
        fetch(
            "https://github.com/x",
            tmp_path / "f",
            allowed_hosts=ALLOWED,
            expected_size=1,
            timeout=1,
            opener=opener,
        )
    assert caught.value.code == "OAK-NATIVE-HOST"


def test_a_body_longer_than_acknowledged_is_cut_off_and_refused(tmp_path: Path) -> None:
    with pytest.raises(OAKError) as caught:
        fetch(
            "https://github.com/x",
            tmp_path / "f",
            allowed_hosts=ALLOWED,
            expected_size=3,
            timeout=1,
            opener=_opener(b"four"),
        )
    assert caught.value.code == "OAK-NATIVE-SIZE"


def test_a_download_reports_its_size_and_digest(tmp_path: Path) -> None:
    size, digest = fetch(
        "https://github.com/x",
        tmp_path / "f",
        allowed_hosts=ALLOWED,
        expected_size=4,
        timeout=1,
        opener=_opener(b"four"),
    )
    assert (size, digest) == (4, "sha256:" + hashlib.sha256(b"four").hexdigest())
    assert (tmp_path / "f").read_bytes() == b"four"


@pytest.mark.parametrize(
    "target",
    ["https://evil.example/x", "http://objects.githubusercontent.com/x", "file:///etc/passwd"],
)
def test_a_redirect_is_followed_only_to_an_acknowledged_https_host(target: str) -> None:
    handler = _AllowedRedirects(ALLOWED)
    request = urllib.request.Request("https://github.com/release")
    with pytest.raises(OAKError) as caught:
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, target)  # type: ignore[arg-type]
    assert caught.value.code == "OAK-NATIVE-HOST"
    followed = handler.redirect_request(
        request,
        io.BytesIO(),
        302,
        "Found",
        {},  # type: ignore[arg-type]
        "https://objects.githubusercontent.com/x",
    )
    assert followed is not None and followed.full_url == "https://objects.githubusercontent.com/x"
    assert handler.max_redirections == native_network.MAXIMUM_REDIRECTS


@pytest.mark.parametrize(
    ("target", "named"),
    [
        ("https://eu.aws.cdn.hf.co/x", "eu.aws.cdn.hf.co"),
        ("http://objects.githubusercontent.com/x", "a host that is not https or not a plain name"),
        ("https://bad‮host.example/x", "a host that is not https or not a plain name"),
    ],
)
def test_a_refused_redirect_names_the_host_when_it_is_a_plain_name(target: str, named: str) -> None:
    handler = _AllowedRedirects(ALLOWED)
    request = urllib.request.Request("https://github.com/release")
    with pytest.raises(OAKError) as caught:
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, target)  # type: ignore[arg-type]
    assert f"redirected to {named}," in caught.value.message


def test_a_host_the_idna_codec_refuses_is_a_download_failure_not_a_crash(tmp_path: Path) -> None:
    """A profile can no longer name such a host, but the runner fails closed regardless."""

    with pytest.raises(OAKError) as caught:
        fetch(
            "https://x..invalid/a",
            tmp_path / "f",
            allowed_hosts=frozenset({"x..invalid"}),
            expected_size=4,
            timeout=1,
        )
    assert caught.value.code == "OAK-NATIVE-DOWNLOAD"


def test_a_download_stops_when_the_lease_ends(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    with pytest.raises(OAKError) as caught:
        fetch(
            "https://github.com/release",
            tmp_path / "f",
            allowed_hosts=ALLOWED,
            expected_size=4,
            timeout=1,
            opener=_opener(b"four"),
            deadline=datetime.now(UTC) - timedelta(seconds=1),
        )
    assert caught.value.code == "OAK-RUNNER-LEASE-EXPIRED"


def test_a_download_reports_the_bytes_written_after_each_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_network, "CHUNK_BYTES", 2)
    reported: list[int] = []
    size, _ = fetch(
        "https://github.com/x",
        tmp_path / "f",
        allowed_hosts=ALLOWED,
        expected_size=5,
        timeout=1,
        opener=_opener(b"hello"),
        progress=reported.append,
    )
    assert size == 5
    assert reported == [2, 4, 5]


def test_progress_never_runs_past_the_acknowledged_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_network, "CHUNK_BYTES", 2)
    reported: list[int] = []
    with pytest.raises(OAKError) as caught:
        fetch(
            "https://github.com/x",
            tmp_path / "f",
            allowed_hosts=ALLOWED,
            expected_size=3,
            timeout=1,
            opener=_opener(b"hello"),
            progress=reported.append,
        )
    assert caught.value.code == "OAK-NATIVE-SIZE"
    assert reported == [2], "the chunk that overran is refused before it is counted"


@pytest.mark.parametrize(
    ("source", "name"),
    [
        (
            "https://github.com/o/r/releases/download/b1/llama-b1-bin-macos-arm64.tar.gz",
            "llama-b1-bin-macos-arm64.tar.gz",
        ),
        ("https://example.org/m/tiny-q4.gguf?token=abc&expires=1", "tiny-q4.gguf"),
        # Printed as written: decoding it could turn it into anything.
        ("https://example.org/m/a%1b%5b2Jb.gguf", "a%1b%5b2Jb.gguf"),
        ("https://example.org/", None),
        ("https://example.org/m/", None),
        ("https://example.org/m/..", None),
        ("https://example.org/m/-rf", None),
        ("https://example.org/m/" + "a" * 121, None),
        ("https://example.org/m/a\x1b[2Jb", None),
        ("https://example.org/m/caf\u00e9.gguf", None),
        ("https://[/x", None),
    ],
)
def test_a_file_is_named_by_the_end_of_its_url_when_that_is_plain(
    source: str, name: str | None
) -> None:
    assert artifact_name(source) == name


def test_a_port_with_a_listener_is_not_free() -> None:
    import socket

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        assert native_network.port_free(port) is False
    assert native_network.port_free(port) is True
