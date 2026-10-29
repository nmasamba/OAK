# SPDX-License-Identifier: Apache-2.0
"""One logging setup for `oak-api`, `oak-worker` and `oak-mcp`: JSON lines on stderr.

A line is built from an allowlist, never by redacting a free-form message (RR-015). Each
line carries the time, the level, the process, the logger and an event name; OAK's own
records add only the fields in `ALLOWED_FIELDS`, and only values made of identifier
characters. A record's message arguments, its traceback and the text of an exception are
never written, because exception messages and library log lines can quote a brief, an
answer, a header or a query string. An exception is written as its type and, for an
`OAKError`, its code. A library's record (uvicorn, SQLAlchemy) is written as its logger,
level and exception type only.

Never to stdout: `oak-mcp` speaks JSON-RPC there, and a stray line corrupts the protocol.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
import time
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from typing import IO, Any, NoReturn

from oak.domain import OAKError

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# The fields an OAK record may add. Tenant, actor, case and brief identifiers are not here:
# a tenant or actor name can be a person's or an organisation's, a case id is named from
# the brief, and the request ID joins a line to the audit trail where they are recorded.
ALLOWED_FIELDS = frozenset(
    {
        "attempt",
        "code",
        "duration_ms",
        "error_type",
        "host",
        "method",
        "operation_id",
        "operation_kind",
        "outcome",
        "port",
        "request_id",
        "route",
        "status",
    }
)
_EVENT = re.compile(r"[a-z][a-z0-9_]{0,63}")
_SAFE_TEXT = re.compile(r"[A-Za-z0-9_.:/{}-]{1,200}")
_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})


def _safe(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int | float):
        return True
    return isinstance(value, str) and _SAFE_TEXT.fullmatch(value) is not None


class AllowlistFormatter(logging.Formatter):
    """Render a record as one JSON object made only of allowlisted fields."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self._component = component

    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "component": self._component,
            "logger": record.name if _SAFE_TEXT.fullmatch(record.name) else "unnamed",
        }
        if record.name == "oak" or record.name.startswith("oak."):
            message = record.msg
            safe_event = isinstance(message, str) and _EVENT.fullmatch(message) is not None
            document["event"] = message if safe_event else "unnamed"
            fields = getattr(record, "oak", None)
            if isinstance(fields, dict):
                for key, value in fields.items():
                    if key in ALLOWED_FIELDS and _safe(value):
                        document[key] = value
        else:
            document["event"] = "library_record"
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            document["error_type"] = type(error).__name__
            if isinstance(error, OAKError):
                document["code"] = error.code
        return json.dumps(document, sort_keys=True, separators=(",", ":"))


def log_level() -> int:
    """`OAK_LOG_LEVEL`, `INFO` by default; anything else is a configuration refusal."""

    name = os.getenv("OAK_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    if name not in LEVELS:
        raise OAKError("OAK-LOG-CONFIG", "OAK_LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")
    return int(logging.getLevelName(name))


def access_log_enabled() -> bool:
    """`OAK_ACCESS_LOG`: one line per API request unless set to a false value."""

    return os.getenv("OAK_ACCESS_LOG", "true").strip().lower() not in {"0", "false", "no"}


def configure_logging(component: str, *, stream: IO[str] | None = None) -> None:
    """Send every record in this process through the allowlist to stderr."""

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(AllowlistFormatter(component))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(log_level())
    # Their lifecycle lines say nothing an operator can act on, and every one is a
    # `library_record` here; warnings and errors still come through.
    for library in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "alembic"):
        logging.getLogger(library).setLevel(max(root.level, logging.WARNING))
    logging.captureWarnings(True)


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    """Log a fixed event name with allowlisted fields."""

    logger.log(level, event, extra={"oak": fields})


def exit_on(logger: logging.Logger, event: str, error: BaseException) -> NoReturn:
    """End the process on `error`, logged as its code and type, never its message.

    An unhandled exception would otherwise reach Python's own handler, which prints the
    message and traceback: a database URL that does not parse quotes part of its password.
    """

    log_event(
        logger,
        logging.ERROR,
        event,
        error_type=type(error).__name__,
        **({"code": error.code} if isinstance(error, OAKError) else {}),
    )
    raise SystemExit(1)


_ASGIApp = Callable[
    [MutableMapping[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]],
    Awaitable[None],
]
_ACCESS = logging.getLogger("oak.api.access")


class AccessLogMiddleware:
    """One line per HTTP request: route template, method, status, duration and request ID.

    Outermost, so a request the loopback guard refuses is logged too. The raw path and
    query string are never logged: a request that matched no route is `unmatched`. The
    request ID is minted here, never taken from a header, and returned as
    `X-OAK-Request-ID` so a user can quote it. An error nothing handled is answered here
    by `unhandled`, because the server's own error middleware sits outside every
    middleware and would send its 500 without the ID. The `quiet` routes (the health
    probes a container healthcheck calls every few seconds) are logged at `DEBUG`.
    """

    def __init__(
        self,
        app: _ASGIApp,
        *,
        enabled: bool = True,
        unhandled: Callable[[MutableMapping[str, Any]], _ASGIApp] | None = None,
        quiet: frozenset[str] = frozenset(),
    ) -> None:
        self._app = app
        self._enabled = enabled
        self._unhandled = unhandled
        self._quiet = quiet

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        request_id = secrets.token_hex(8)
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = 500
        responded = False

        async def send_with_id(message: Any) -> None:
            nonlocal status, responded
            if message.get("type") == "http.response.start":
                responded = True
                status = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                headers.append((b"x-oak-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        error_type: str | None = None
        try:
            await self._app(scope, receive, send_with_id)
        except Exception as error:
            # Its type is logged; its message, which may quote the request, is not.
            error_type = type(error).__name__
            if responded or self._unhandled is None:
                raise
            await self._unhandled(scope)(scope, receive, send_with_id)
        finally:
            if self._enabled:
                route = scope.get("route")
                path = getattr(route, "path", None)
                method = str(scope.get("method", ""))
                state = scope.get("state")
                code = state.get("error_code") if isinstance(state, dict) else None
                log_event(
                    _ACCESS,
                    logging.DEBUG if path in self._quiet else logging.INFO,
                    "request",
                    route=path if isinstance(path, str) else "unmatched",
                    method=method if method in _METHODS else "OTHER",
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                    request_id=request_id,
                    **({"code": code} if isinstance(code, str) else {}),
                    **({"error_type": error_type} if error_type is not None else {}),
                )
