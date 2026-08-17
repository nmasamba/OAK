# SPDX-License-Identifier: Apache-2.0
"""Loopback-safe ASGI process entrypoint."""

import ipaddress
import os

import uvicorn


def is_loopback_host(host: str) -> bool:
    """Return true only for explicit loopback names or addresses."""

    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def ensure_safe_bind(host: str, *, allow_non_loopback: bool) -> None:
    if not is_loopback_host(host) and not allow_non_loopback:
        raise ValueError(
            "non-loopback binding is disabled; pass the explicit acknowledgement only in "
            "an isolated development environment"
        )


def run_server(host: str, port: int, *, allow_non_loopback: bool = False) -> None:
    ensure_safe_bind(host, allow_non_loopback=allow_non_loopback)
    uvicorn.run(
        "oak.interfaces.api.app:app",
        host=host,
        port=port,
        access_log=False,
        server_header=False,
    )


def _environment_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    host = os.getenv("OAK_HOST", "127.0.0.1")
    port_text = os.getenv("OAK_PORT", "8080")
    try:
        port = int(port_text)
    except ValueError as error:
        raise SystemExit("OAK_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise SystemExit("OAK_PORT must be between 1 and 65535")
    try:
        run_server(
            host=host,
            port=port,
            allow_non_loopback=_environment_flag("OAK_ALLOW_NON_LOOPBACK"),
        )
    except ValueError as error:
        raise SystemExit(f"OAK-SAFE-BIND: {error}") from error


if __name__ == "__main__":  # pragma: no cover
    main()
