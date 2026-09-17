# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-005: the only outbound path a provider adapter has is allowlisted and bounded.

Every test runs against listeners on 127.0.0.1 that this file starts; nothing here reaches
the public network. The plain-http loopback allowance exists for the local-server family and
is what lets these tests exercise the transport without certificates, except for the one test
that proves certificate verification is on.
"""

from __future__ import annotations

import http.server
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.models import transport as transport_module
from oak.adapters.models.transport import ModelTransport, TransportRequest, is_loopback_host
from oak.domain import OAKError

KEY = "oak-test-key-transport-0123456789abcdef"
SENTINEL = "PROVIDER-BODY-TEXT-THAT-MUST-NOT-LEAK"


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *arguments: object) -> None:  # silence the test server
        return

    def do_GET(self) -> None:
        self._serve()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._serve()

    def _serve(self) -> None:
        server: Any = self.server
        server.seen.append(
            {
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
            }
        )
        mode = server.mode
        if mode == "ok":
            self._send(200, json.dumps({"ok": True, "path": self.path}).encode("utf-8"))
        elif mode == "redirect":
            self.send_response(302)
            self.send_header("Location", server.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif mode == "big":
            self._send(200, b"x" * server.size)
        elif mode == "trickle":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "600")
            self.end_headers()
            for _ in range(600):
                try:
                    self.wfile.write(b"a")
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(0.1)
        elif mode == "status":
            self._send(
                server.status, json.dumps(server.body).encode("utf-8"), extra=server.extra_headers
            )

    def _send(self, status: int, body: bytes, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, mode: str = "ok") -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.mode = mode
        self.seen: list[dict[str, Any]] = []
        self.redirect_to = ""
        self.size = 0
        self.status = 200
        self.body: dict[str, Any] = {}
        self.extra_headers: dict[str, str] = {}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


@pytest.fixture
def server() -> Iterator[_Server]:
    instance = _Server()
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()


def _transport(
    *,
    deadline: float = 5.0,
    maximum: int = 65_536,
    hosts: frozenset[str] = frozenset({"127.0.0.1"}),
    plain: bool = True,
    **keywords: Any,
) -> ModelTransport:
    return ModelTransport(
        allowed_hosts=hosts,
        deadline_seconds=deadline,
        maximum_response_bytes=maximum,
        allow_plain_http_loopback=plain,
        **keywords,
    )


def _closed_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def test_a_host_outside_the_allowlist_is_refused_before_any_socket_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*arguments: object, **keywords: object) -> None:
        raise AssertionError("the transport touched a socket before checking the allowlist")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    transport = _transport(hosts=frozenset({"api.example.test"}), plain=False)
    for url in (
        "https://evil.example.test/v1/models",
        "https://api.example.test.evil.example/v1/models",
        "https://api-example.test/v1/models",
        "http://api.example.test/v1/models",
        "ftp://api.example.test/v1/models",
        "https:///v1/models",
        "/v1/models",
    ):
        with pytest.raises(OAKError) as refused:
            transport.send(TransportRequest(method="GET", url=url))
        assert refused.value.code == "OAK-MODEL-EGRESS-DENIED", url
        assert "example" not in refused.value.message


def test_plain_http_is_allowed_only_to_loopback_and_only_when_enabled(server: _Server) -> None:
    with pytest.raises(OAKError) as refused:
        _transport(plain=False).send(TransportRequest(method="GET", url=f"{server.url}/x"))
    assert refused.value.code == "OAK-MODEL-EGRESS-DENIED"
    assert server.seen == []

    response = _transport().send(TransportRequest(method="GET", url=f"{server.url}/x"))
    assert response.status == 200
    assert json.loads(response.body) == {"ok": True, "path": "/x"}


def test_redirects_are_not_followed_and_the_second_listener_receives_nothing(
    server: _Server,
) -> None:
    victim = _Server()
    thread = threading.Thread(target=victim.serve_forever, daemon=True)
    thread.start()
    try:
        server.mode = "redirect"
        server.redirect_to = f"{victim.url}/steal"
        with pytest.raises(OAKError) as refused:
            _transport().send(
                TransportRequest(
                    method="POST",
                    url=f"{server.url}/chat",
                    headers={"Authorization": f"Bearer {KEY}"},
                    body=b"{}",
                )
            )
        assert refused.value.code == "OAK-INTERPRETER-UNAVAILABLE"
        assert "redirect" in refused.value.message
        assert refused.value.retriable is False
        assert len(server.seen) == 1
        assert victim.seen == []
    finally:
        victim.shutdown()
        victim.server_close()


def test_the_response_body_is_bounded(server: _Server) -> None:
    server.mode = "big"
    server.size = 70_000
    with pytest.raises(OAKError) as refused:
        _transport(maximum=65_536).send(TransportRequest(method="GET", url=f"{server.url}/big"))
    assert refused.value.code == "OAK-INTERPRETER-OUTPUT-LIMIT"


def test_a_trickling_provider_is_cut_off_at_the_deadline(server: _Server) -> None:
    server.mode = "trickle"
    started = time.monotonic()
    with pytest.raises(OAKError) as refused:
        _transport(deadline=1.5).send(TransportRequest(method="GET", url=f"{server.url}/slow"))
    elapsed = time.monotonic() - started
    assert refused.value.code == "OAK-INTERPRETER-UNAVAILABLE"
    assert refused.value.retriable is True
    assert elapsed < 6, elapsed


def test_environment_and_system_proxies_are_ignored(
    server: _Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = f"http://127.0.0.1:{_closed_port()}"
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(variable, proxy)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": proxy, "https": proxy})

    response = _transport().send(TransportRequest(method="GET", url=f"{server.url}/direct"))

    assert response.status == 200
    assert [entry["path"] for entry in server.seen] == ["/direct"]
    source = Path(transport_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("urlopen", "build_opener", "ProxyHandler", "getproxies", "set_tunnel"):
        assert forbidden not in source, forbidden


def test_default_headers_send_no_compression_request_and_name_oak(server: _Server) -> None:
    _transport().send(
        TransportRequest(
            method="POST",
            url=f"{server.url}/chat",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            body=b"{}",
        )
    )
    headers = server.seen[0]["headers"]
    # `http.client` states `identity` for us; what matters is that no compressed encoding
    # is offered, so a provider cannot answer with a body the size bound cannot measure.
    assert headers.get("accept-encoding", "identity") == "identity"
    assert headers["user-agent"].startswith("oak-community/")
    assert headers["authorization"] == f"Bearer {KEY}"
    assert headers["accept"] == "application/json"


def test_the_transport_retains_nothing_from_a_request(server: _Server) -> None:
    transport = _transport()
    transport.send(
        TransportRequest(
            method="GET", url=f"{server.url}/x", headers={"Authorization": f"Bearer {KEY}"}
        )
    )
    state = (
        repr({name: getattr(transport, name) for name in transport.__slots__})
        if hasattr(transport, "__slots__")
        else repr(vars(transport))
    )
    assert KEY not in state
    assert "127.0.0.1" not in state or "allowed_hosts" in state


def test_connection_failures_become_one_retriable_code_without_detail() -> None:
    port = _closed_port()
    with pytest.raises(OAKError) as refused:
        _transport(deadline=2.0).send(
            TransportRequest(method="GET", url=f"http://127.0.0.1:{port}/x")
        )
    assert refused.value.code == "OAK-INTERPRETER-UNAVAILABLE"
    assert refused.value.retriable is True
    assert str(port) not in refused.value.message
    assert not re.search(r"Errno|refused|\[", refused.value.message)


def test_non_success_statuses_are_returned_for_the_profile_to_map(server: _Server) -> None:
    server.mode = "status"
    server.status = 429
    server.body = {"error": {"message": SENTINEL, "type": "rate_limit_error"}}
    server.extra_headers = {"Retry-After": "3"}
    response = _transport().send(TransportRequest(method="GET", url=f"{server.url}/x"))
    assert response.status == 429
    assert response.header("Retry-After") == "3"
    assert SENTINEL.encode("utf-8") in response.body


def test_the_deadline_is_capped_and_hosts_are_required() -> None:
    with pytest.raises(ValueError):
        _transport(deadline=56.0)
    with pytest.raises(ValueError):
        _transport(deadline=0.0)
    with pytest.raises(ValueError):
        ModelTransport(allowed_hosts=frozenset(), deadline_seconds=5.0, maximum_response_bytes=10)


def _self_signed_certificate(directory: Path) -> tuple[Path, Path]:
    cryptography = pytest.importorskip("cryptography")
    del cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "server.pem"
    key_path = directory / "server.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


def test_tls_certificates_are_verified_against_a_trust_store(tmp_path: Path) -> None:
    certificate_path, key_path = _self_signed_certificate(tmp_path)
    instance = _Server()
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certificate_path), str(key_path))
    instance.socket = server_context.wrap_socket(instance.socket, server_side=True)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    url = f"https://127.0.0.1:{instance.server_port}/x"
    try:
        with pytest.raises(OAKError) as refused:
            _transport(plain=False).send(TransportRequest(method="GET", url=url))
        assert refused.value.code == "OAK-INTERPRETER-UNAVAILABLE"
        assert "certificate" in refused.value.message or "TLS" in refused.value.message
        assert instance.seen == []

        trusting = ssl.create_default_context(cafile=str(certificate_path))
        response = _transport(plain=False, ssl_context=trusting).send(
            TransportRequest(method="GET", url=url)
        )
        assert response.status == 200
        assert len(instance.seen) == 1
    finally:
        instance.shutdown()
        instance.server_close()


# ----- regressions found by the Sprint 9 adversarial review -----------------------


@pytest.mark.parametrize(
    "hostname,loopback",
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("LOCALHOST", True),
        # The ones a prefix test used to wave through. Each is an ordinary DNS name whose
        # owner chooses where it resolves, and the local family speaks plain http.
        ("127.evil.example.com", False),
        ("127.0.0.1.evil.example", False),
        ("localhost.evil.example", False),
        ("127-0-0-1.evil.example", False),
        ("0.0.0.0", False),
        ("10.0.0.5", False),
        ("2130706433", False),
        ("", False),
    ],
)
def test_only_a_literal_loopback_address_or_localhost_counts_as_loopback(
    hostname: str, loopback: bool
) -> None:
    assert is_loopback_host(hostname) is loopback


def test_a_provider_that_trickles_its_status_line_is_cut_off_at_the_deadline() -> None:
    """The deadline covers the whole exchange, not only the body.

    The first version armed the socket with the *connect* timeout until the body loop
    started, so a server that dribbled the status line held the request open while every
    individual receive stayed inside that timeout.
    """

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = int(listener.getsockname()[1])
    stop = threading.Event()

    def dribble() -> None:
        connection, _ = listener.accept()
        try:
            connection.recv(65536)
            for character in b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi":
                if stop.is_set():
                    return
                connection.sendall(bytes([character]))
                time.sleep(0.4)
        except OSError:
            return
        finally:
            connection.close()

    server = threading.Thread(target=dribble, daemon=True)
    server.start()
    started = time.monotonic()
    try:
        with pytest.raises(OAKError) as refused:
            _transport(deadline=1.0).send(
                TransportRequest(method="GET", url=f"http://127.0.0.1:{port}/slow")
            )
        elapsed = time.monotonic() - started
        assert refused.value.code == "OAK-INTERPRETER-UNAVAILABLE"
        assert refused.value.retriable is True
        assert elapsed < 8, elapsed
    finally:
        stop.set()
        listener.close()
        server.join(timeout=5)
