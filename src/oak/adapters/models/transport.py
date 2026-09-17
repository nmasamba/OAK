# SPDX-License-Identifier: Apache-2.0
"""The one place OAK opens an outbound connection to a model provider.

Every hosted-provider request goes through ``ModelTransport``. The module is deliberately
narrow so the egress gate in ``tests/integration/test_offline_boundary.py`` can allow exactly
one model module to import a network client:

- the destination host must be in the fixed allowlist the caller passes in, checked before
  any socket call (``OAK-MODEL-EGRESS-DENIED``);
- only ``https`` is spoken, except plain ``http`` to a loopback address for a local server;
- redirects are never followed (a 3xx is a refusal, and ``Location`` is never read);
- environment and system proxies are never consulted: ``http.client`` connects directly;
- the response body is read in bounded chunks against one monotonic deadline;
- every ``socket``/``ssl``/``http.client`` exception becomes an ``OAKError`` with a fixed
  message, so no provider text, header or stack detail reaches a log or an interface.
"""

from __future__ import annotations

import http.client
import ipaddress
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from oak import __version__
from oak.domain import OAKError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEADLINE_MESSAGE = "the provider did not answer within the request deadline"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
MAXIMUM_DEADLINE_SECONDS = 55.0
CHUNK_BYTES = 65_536
USER_AGENT = f"oak-community/{__version__}"


class _DeadlineReader:
    """A file object that refuses to read once the request's clock has run out.

    A socket timeout bounds one receive, not a request. `http.client` reads the status line
    and every header with its own `readline`, so a provider that sends one byte at a time
    keeps each receive inside the timeout and holds the request open for as long as it
    likes. Wrapping the reader the response is built from is the only place a *total* bound
    can be applied, because nothing inside `getresponse` reports progress.
    """

    __slots__ = ("_deadline", "_raw")

    def __init__(self, raw: Any, deadline: float) -> None:
        self._raw = raw
        self._deadline = deadline

    def _check(self) -> None:
        if time.monotonic() >= self._deadline:
            raise TimeoutError(DEADLINE_MESSAGE)

    def read(self, size: int = -1) -> bytes:
        self._check()
        return bytes(self._raw.read(size))

    def read1(self, size: int = -1) -> bytes:
        self._check()
        reader = getattr(self._raw, "read1", None)
        return bytes(reader(size) if reader is not None else self._raw.read(size))

    def readinto(self, buffer: Any) -> int:
        self._check()
        return int(self._raw.readinto(buffer))

    def readline(self, limit: int = -1) -> bytes:
        self._check()
        return bytes(self._raw.readline(limit))

    def close(self) -> None:
        self._raw.close()

    @property
    def closed(self) -> bool:
        return bool(self._raw.closed)

    def flush(self) -> None:
        return None

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def writable(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class TransportRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


def is_loopback_host(hostname: str) -> bool:
    """Whether a URL host is unambiguously this machine.

    A prefix test on the string is not good enough: ``127.evil.example.com`` starts with
    ``127.`` and is an ordinary DNS name whose owner can point it anywhere, so a prefix
    test would let the local family's endpoint leave the machine — in cleartext, because
    plain http is permitted for loopback. Only a literal loopback IP address, or the exact
    name ``localhost``, counts.
    """

    candidate = hostname.strip().strip("[]").lower()
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


class ModelTransport:
    """Send one bounded HTTPS request to an allowlisted host."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        deadline_seconds: float,
        maximum_response_bytes: int,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        allow_plain_http_loopback: bool = False,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if not allowed_hosts:
            raise ValueError("a model transport needs at least one allowed host")
        if not 0 < deadline_seconds <= MAXIMUM_DEADLINE_SECONDS:
            raise ValueError(f"deadline must be within (0, {MAXIMUM_DEADLINE_SECONDS}] seconds")
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self._deadline_seconds = float(deadline_seconds)
        self._maximum_response_bytes = int(maximum_response_bytes)
        self._connect_timeout = min(float(connect_timeout_seconds), self._deadline_seconds)
        self._allow_plain_http_loopback = allow_plain_http_loopback
        # The default context verifies certificates against the system store and checks
        # the hostname; nothing here can weaken it.
        self._ssl_context = ssl_context or ssl.create_default_context()

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return self._allowed_hosts

    @property
    def deadline_seconds(self) -> float:
        return self._deadline_seconds

    def send(
        self, request: TransportRequest, *, deadline_seconds: float | None = None
    ) -> TransportResponse:
        parts = urllib.parse.urlsplit(request.url)
        hostname = (parts.hostname or "").lower()
        if not hostname or hostname not in self._allowed_hosts:
            raise OAKError(
                "OAK-MODEL-EGRESS-DENIED",
                "the request destination is not on the provider's fixed host allowlist",
            )
        if parts.scheme == "https":
            plain = False
        elif (
            parts.scheme == "http"
            and self._allow_plain_http_loopback
            and is_loopback_host(hostname)
        ):
            plain = True
        else:
            raise OAKError(
                "OAK-MODEL-EGRESS-DENIED",
                "only https is spoken to a provider (plain http only to a loopback address)",
            )
        budget = self._deadline_seconds
        if deadline_seconds is not None:
            budget = max(0.05, min(budget, float(deadline_seconds)))
        deadline = time.monotonic() + budget
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Connection": "close",
            **request.headers,
        }
        for name, value in headers.items():
            # `http.client` refuses a header value containing a control character by raising
            # with the value in the message, which for `Authorization` would put the key in
            # an exception chain. A credential taken from the environment never passes
            # through `validate_key_input`, so it is checked here instead.
            if any(character in value for character in "\r\n\x00") or not value.isprintable():
                raise OAKError(
                    "OAK-MODEL-KEY-INVALID",
                    f"the {name} header value contains a character a request cannot carry; "
                    "store the key again without whitespace or control characters",
                )
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        port = parts.port or (80 if plain else 443)
        connection = self._connect(hostname, port, plain=plain, budget=budget)
        try:
            return self._exchange(connection, request, headers, path, deadline)
        finally:
            connection.close()

    # ----- internals -----------------------------------------------------------------

    def _connect(
        self, hostname: str, port: int, *, plain: bool, budget: float
    ) -> http.client.HTTPConnection:
        timeout = min(self._connect_timeout, budget)
        if plain:
            return http.client.HTTPConnection(hostname, port, timeout=timeout)
        return http.client.HTTPSConnection(
            hostname, port, timeout=timeout, context=self._ssl_context
        )

    @staticmethod
    def _remaining(deadline: float) -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise OAKError("OAK-INTERPRETER-UNAVAILABLE", DEADLINE_MESSAGE, retriable=True)
        return left

    @classmethod
    def _arm(cls, connection: http.client.HTTPConnection, deadline: float) -> None:
        """Put the socket on the request's own clock before it blocks again.

        `http.client` keeps the timeout it was constructed with, which is the *connect*
        timeout. Without this, a provider that trickles the status line, or floods trailers
        after the last chunk, holds the request open while every individual receive stays
        comfortably inside that timeout.
        """

        remaining = cls._remaining(deadline)
        if connection.sock is not None:
            connection.sock.settimeout(remaining)

    @staticmethod
    def _bound_reads(connection: http.client.HTTPConnection, deadline: float) -> None:
        """Make every read of this response, headers included, honour the total deadline.

        `socket.makefile` is read-only on a real socket, so the reader is installed through
        the connection's response class: `HTTPResponse.__init__` opens the file, and
        `begin()` — which consumes the status line and the headers — runs afterwards, so a
        wrapper applied in `__init__` covers the whole response.
        """

        class _BoundedResponse(http.client.HTTPResponse):
            def __init__(self, sock: Any, *arguments: Any, **keywords: Any) -> None:
                super().__init__(sock, *arguments, **keywords)
                self.fp = _DeadlineReader(self.fp, deadline)  # type: ignore[assignment]

        connection.response_class = _BoundedResponse

    def _exchange(
        self,
        connection: http.client.HTTPConnection,
        request: TransportRequest,
        headers: dict[str, str],
        path: str,
        deadline: float,
    ) -> TransportResponse:
        try:
            # `http.client` connects lazily, so the socket does not exist until the
            # request has been sent; bounding reads before that would patch nothing.
            self._bound_reads(connection, deadline)
            connection.request(request.method, path, body=request.body, headers=headers)
            self._arm(connection, deadline)
            response = connection.getresponse()
            self._arm(connection, deadline)
            status = int(response.status)
            if 300 <= status < 400:
                # Never read Location, never follow.
                raise OAKError(
                    "OAK-INTERPRETER-UNAVAILABLE",
                    "the provider answered with a redirect, which OAK does not follow",
                )
            body = self._read_bounded(connection, response, deadline)
        except OAKError:
            raise
        except ssl.SSLCertVerificationError as error:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE",
                "the provider's TLS certificate could not be verified",
            ) from error
        except ssl.SSLError as error:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE", "the TLS handshake with the provider failed"
            ) from error
        except TimeoutError as error:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE", DEADLINE_MESSAGE, retriable=True
            ) from error
        except (http.client.HTTPException, OSError, ValueError) as error:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE",
                "the provider could not be reached or answered with an unusable response",
                retriable=True,
            ) from error
        lowered = {str(name).lower(): str(value) for name, value in response.getheaders()}
        return TransportResponse(status=status, headers=lowered, body=body)

    def _read_bounded(
        self,
        connection: http.client.HTTPConnection,
        response: http.client.HTTPResponse,
        deadline: float,
    ) -> bytes:
        chunks: list[bytes] = []
        total = 0
        sock: Any = connection.sock
        while True:
            remaining = self._remaining(deadline)
            if sock is not None:
                sock.settimeout(remaining)
            # `read` would block until it had a whole chunk, so a provider trickling one
            # byte at a time could hold the connection for chunk_size x timeout while every
            # individual recv stayed inside its socket timeout. `read1` returns what one
            # recv produced, so the deadline below is tested against every packet.
            chunk = response.read1(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > self._maximum_response_bytes:
                raise OAKError(
                    "OAK-INTERPRETER-OUTPUT-LIMIT", "provider response exceeds its size limit"
                )
            chunks.append(chunk)
        return b"".join(chunks)
