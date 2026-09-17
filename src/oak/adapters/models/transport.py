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
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from oak import __version__
from oak.domain import OAKError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
MAXIMUM_DEADLINE_SECONDS = 55.0
CHUNK_BYTES = 65_536
USER_AGENT = f"oak-community/{__version__}"


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
    return hostname.lower() in LOOPBACK_HOSTS or hostname.startswith("127.")


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

    def _exchange(
        self,
        connection: http.client.HTTPConnection,
        request: TransportRequest,
        headers: dict[str, str],
        path: str,
        deadline: float,
    ) -> TransportResponse:
        try:
            connection.request(request.method, path, body=request.body, headers=headers)
            response = connection.getresponse()
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
                "OAK-INTERPRETER-UNAVAILABLE",
                "the provider did not answer within the request deadline",
                retriable=True,
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
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OAKError(
                    "OAK-INTERPRETER-UNAVAILABLE",
                    "the provider did not answer within the request deadline",
                    retriable=True,
                )
            if sock is not None:
                sock.settimeout(max(0.05, min(remaining, self._connect_timeout)))
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
