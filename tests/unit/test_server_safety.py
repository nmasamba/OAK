# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-006 loopback-safe bind tests."""

import pytest

from oak.interfaces.api.server import ensure_safe_bind, is_loopback_host


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "  LOCALHOST  "])
def test_loopback_hosts_are_recognized(host: str) -> None:
    assert is_loopback_host(host)
    ensure_safe_bind(host, allow_non_loopback=False)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "api.internal", "192.0.2.1"])
def test_non_loopback_bind_fails_closed(host: str) -> None:
    assert not is_loopback_host(host)
    with pytest.raises(ValueError, match="non-loopback binding is disabled"):
        ensure_safe_bind(host, allow_non_loopback=False)


def test_non_loopback_bind_requires_explicit_acknowledgement() -> None:
    ensure_safe_bind("0.0.0.0", allow_non_loopback=True)
