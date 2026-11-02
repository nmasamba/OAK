# SPDX-License-Identifier: Apache-2.0
"""The runner's one network module (ADR-0019): artifact downloads and loopback probes.

A native installation fetches each artifact over HTTPS from a host its target profile
acknowledges, and every redirect must lead to such a host too; nothing else in the runner
opens a connection. The environment's proxy settings are ignored, TLS is verified against
the system's trust store, and a body longer than the artifact's acknowledged size is cut
off and refused, never stored whole. The health probe talks to 127.0.0.1 and nowhere else.
"""

from __future__ import annotations

import hashlib
import http.client
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from oak.domain import OAKError

MAXIMUM_REDIRECTS = 5
CHUNK_BYTES = 1 << 20

Opener = Callable[[str, float], Any]


def https_host(url: str) -> str | None:
    """The host of an https URL without credentials in it, lower-cased; None otherwise."""

    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return None
    return parts.hostname


class _AllowedRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to an https URL on an acknowledged host, at most five."""

    max_redirections = MAXIMUM_REDIRECTS

    def __init__(self, allowed: frozenset[str]) -> None:
        self._allowed = allowed

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if https_host(newurl) not in self._allowed:
            raise OAKError(
                "OAK-NATIVE-HOST",
                "a download redirected to a host the target profile does not acknowledge",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(allowed: frozenset[str]) -> Opener:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _AllowedRedirects(allowed),
    )

    def open_url(url: str, timeout: float) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": "oak-runner"})
        return opener.open(request, timeout=timeout)

    return open_url


def fetch(
    source: str,
    destination: Path,
    *,
    allowed_hosts: frozenset[str],
    expected_size: int,
    timeout: float,
    opener: Opener | None = None,
) -> tuple[int, str]:
    """Download ``source`` into a new file at ``destination``.

    Returns the number of bytes written and their SHA-256. The caller compares both with
    what the target profile acknowledges before anything is unpacked or run.
    """

    if https_host(source) not in allowed_hosts:
        raise OAKError(
            "OAK-NATIVE-HOST", "an artifact's host is not one the target profile acknowledges"
        )
    open_url = opener or _opener(allowed_hosts)
    digest = hashlib.sha256()
    written = 0
    try:
        with open_url(source, timeout) as response, destination.open("xb") as output:
            final = response.geturl() if hasattr(response, "geturl") else source
            if https_host(str(final)) not in allowed_hosts:
                raise OAKError(
                    "OAK-NATIVE-HOST",
                    "a download ended on a host the target profile does not acknowledge",
                )
            while True:
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > expected_size:
                    raise OAKError(
                        "OAK-NATIVE-SIZE", "an artifact is larger than its acknowledged size"
                    )
                digest.update(chunk)
                output.write(chunk)
    except (urllib.error.URLError, http.client.HTTPException, ssl.SSLError, OSError) as error:
        raise OAKError("OAK-NATIVE-DOWNLOAD", "an artifact could not be downloaded") from error
    return written, "sha256:" + digest.hexdigest()


def probe(port: int, path: str, timeout: float) -> int | None:
    """The status a GET on 127.0.0.1 answers, or None when nothing answers in time."""

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read(65_536)
        return response.status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()
