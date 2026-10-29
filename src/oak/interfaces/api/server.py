# SPDX-License-Identifier: Apache-2.0
"""Loopback-safe ASGI process entrypoint."""

import ipaddress
import logging
import os
import sys
from typing import Any

import uvicorn

from oak.bootstrap import default_credentials_directory, mint_model_token
from oak.domain import OAKError
from oak.interfaces.logs import configure_logging, exit_on, log_event

_LOG = logging.getLogger("oak.api")


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


def bind_warning(host: str, *, allow_non_loopback: bool, allowed_hosts: str) -> str | None:
    """The warning owed for an acknowledged non-loopback bind, or ``None``."""

    if is_loopback_host(host) or not allow_non_loopback:
        return None
    if allowed_hosts.strip():
        return (
            f"OAK-SAFE-BIND: binding {host} publishes an unauthenticated control plane; "
            f"only Host values in OAK_ALLOWED_HOSTS ({allowed_hosts.strip()}) and loopback "
            "names are served"
        )
    return (
        f"OAK-SAFE-BIND: binding {host} publishes an unauthenticated control plane, and "
        "OAK_ALLOWED_HOSTS is empty, so only requests naming a loopback Host will be served"
    )


def run_server(
    host: str,
    port: int,
    *,
    allow_non_loopback: bool = False,
    model_token: str | None = None,
) -> None:
    """Bind the API after minting the per-process model-configuration token.

    Logging is configured here, so `oak serve` writes the same allowlisted lines as
    `oak-api`; an unknown `OAK_LOG_LEVEL` refuses with `OAK-LOG-CONFIG`. The socket is bound
    before serving, through uvicorn (this module imports no network library: it listens, it
    never calls out), so a port in use refuses with `OAK-SERVE-BIND` rather than uvicorn's
    own exit, and a bound one is logged as `api_listening`.
    """

    configure_logging("oak-api")
    ensure_safe_bind(host, allow_non_loopback=allow_non_loopback)
    warning = bind_warning(
        host,
        allow_non_loopback=allow_non_loopback,
        allowed_hosts=os.getenv("OAK_ALLOWED_HOSTS", ""),
    )
    if warning is not None:
        print(warning, file=sys.stderr)
    if not os.getenv("OAK_DATABASE_URL"):
        print(
            "OAK_DATABASE_URL is not set: /version, the health checks and the model settings "
            "answer, but every design-case route refuses with OAK-DATABASE-UNCONFIGURED until "
            "it names the PostgreSQL database (docs/development.md)",
            file=sys.stderr,
        )
    if model_token is None:
        mint_model_token()
    print(
        "Model-configuration token written to "
        f"{default_credentials_directory() / 'api-token'}; run `oak models token` to read it.",
        file=sys.stderr,
    )
    # OAK writes the access line itself, from an allowlist (oak.interfaces.logs); uvicorn's
    # own access log would print the raw path and query string, and its default logging
    # configuration would replace the allowlisted handler.
    # One process: worker processes (`WEB_CONCURRENCY`) would start without this logging.
    config = uvicorn.Config(
        "oak.interfaces.api.app:app",
        host=host,
        port=port,
        workers=1,
        access_log=False,
        log_config=None,
        server_header=False,
    )
    try:
        # uvicorn logs a failed bind (a library line, its text not written) and exits.
        listening = config.bind_socket()
    except SystemExit as error:
        raise OAKError(
            "OAK-SERVE-BIND",
            f"cannot listen on {host}:{port}: the address is in use, is not this "
            "machine's, or needs a privilege this process lacks",
        ) from error
    log_event(_LOG, logging.INFO, "api_listening", host=host, port=port)
    _serve(config, listening)


def _serve(config: uvicorn.Config, listening: Any) -> None:
    uvicorn.Server(config).run(sockets=[listening])


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
    allow_non_loopback = _environment_flag("OAK_ALLOW_NON_LOOPBACK")
    try:
        ensure_safe_bind(host, allow_non_loopback=allow_non_loopback)
    except ValueError as error:
        raise SystemExit(f"OAK-SAFE-BIND: {error}") from error
    try:
        # Before anything can be logged as JSON, so a bad level is said in plain text.
        configure_logging("oak-api")
    except OAKError as error:
        raise SystemExit(f"{error.code}: {error.message}") from error
    try:
        run_server(host=host, port=port, allow_non_loopback=allow_non_loopback)
    except Exception as error:
        exit_on(_LOG, "startup_failed", error)


if __name__ == "__main__":  # pragma: no cover
    main()
