# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-024 (RR-015): log lines are built from an allowlist, never by redaction."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from oak.domain import OAKError
from oak.interfaces.logs import (
    ALLOWED_FIELDS,
    AccessLogMiddleware,
    AllowlistFormatter,
    access_log_enabled,
    configure_logging,
    log_event,
    log_level,
)

SECRET = "oaksentinel-0123"
BASE_FIELDS = {"time", "level", "component", "logger", "event"}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """Route this process's logging through the allowlist into a buffer, then restore it."""

    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    monkeypatch.setenv("OAK_LOG_LEVEL", "DEBUG")
    stream = io.StringIO()
    configure_logging("oak-test", stream=stream)
    yield stream
    root.handlers[:], level = saved
    root.setLevel(level)
    logging.captureWarnings(False)


def _lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def _record(name: str, message: object, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_an_oak_record_keeps_only_allowlisted_fields_with_identifier_values() -> None:
    record = _record(
        "oak.api.access",
        "request",
        oak={
            "route": "/v1/design-cases/{case_id}:interpret",
            "status": 200,
            "request_id": "a1b2c3",
            "tenant": "acme",
            "actor": "pat@example.com",
            "brief": SECRET,
            "code": f"OAK-X {SECRET}",
        },
    )

    document = json.loads(AllowlistFormatter("oak-api").format(record))

    assert set(document) == BASE_FIELDS | {"route", "status", "request_id"}
    assert document["event"] == "request" and document["component"] == "oak-api"
    assert SECRET not in json.dumps(document)


def test_a_message_that_is_not_an_event_name_and_its_arguments_are_never_written() -> None:
    record = _record("oak.worker", "answer was %s", SECRET)

    document = json.loads(AllowlistFormatter("oak-worker").format(record))

    assert document["event"] == "unnamed"
    assert SECRET not in json.dumps(document)


def test_a_library_record_is_its_logger_and_level_only() -> None:
    record = _record("httpx", "HTTP Request: GET %s", f"http://127.0.0.1/v1/x?q={SECRET}")

    document = json.loads(AllowlistFormatter("oak-api").format(record))

    assert document == {
        "time": document["time"],
        "level": "INFO",
        "component": "oak-api",
        "logger": "httpx",
        "event": "library_record",
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError(f"could not parse {SECRET}"), {"error_type": "RuntimeError"}),
        (
            OAKError("OAK-CASE-EXISTS", f"case {SECRET} exists"),
            {"error_type": "OAKError", "code": "OAK-CASE-EXISTS"},
        ),
    ],
)
def test_an_exception_is_its_type_and_code_never_its_message_or_traceback(
    error: Exception, expected: dict[str, str]
) -> None:
    try:
        raise error
    except Exception:
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            __file__,
            1,
            "Exception in ASGI application",
            (),
            __import__("sys").exc_info(),
        )

    text = AllowlistFormatter("oak-api").format(record)

    assert SECRET not in text and "Traceback" not in text
    assert {key: json.loads(text)[key] for key in expected} == expected


def test_the_allowlist_names_no_identity_or_content_field() -> None:
    assert not ALLOWED_FIELDS & {"tenant", "tenant_id", "actor", "case_id", "brief", "query"}


def test_the_level_defaults_to_info_and_refuses_a_name_it_does_not_know(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OAK_LOG_LEVEL", raising=False)
    assert log_level() == logging.INFO
    monkeypatch.setenv("OAK_LOG_LEVEL", "warning")
    assert log_level() == logging.WARNING
    monkeypatch.setenv("OAK_LOG_LEVEL", "VERBOSE")
    with pytest.raises(OAKError) as refused:
        log_level()
    assert refused.value.code == "OAK-LOG-CONFIG"


@pytest.mark.parametrize(
    ("value", "enabled"), [(None, True), ("true", True), ("false", False), ("0", False)]
)
def test_the_access_log_is_on_unless_turned_off(
    monkeypatch: pytest.MonkeyPatch, value: str | None, enabled: bool
) -> None:
    if value is None:
        monkeypatch.delenv("OAK_ACCESS_LOG", raising=False)
    else:
        monkeypatch.setenv("OAK_ACCESS_LOG", value)
    assert access_log_enabled() is enabled


def test_configured_logging_writes_one_json_object_per_line(captured: io.StringIO) -> None:
    log_event(logging.getLogger("oak.worker"), logging.INFO, "operation_cycle", attempt=1)
    logging.getLogger("sqlalchemy.engine").warning("SELECT %s", SECRET)

    lines = _lines(captured)
    assert [line["event"] for line in lines] == ["operation_cycle", "library_record"]
    assert SECRET not in captured.getvalue()


def _application(enabled: bool = True) -> FastAPI:
    api = FastAPI()

    @api.exception_handler(OAKError)
    async def refused(request: Request, error: OAKError) -> JSONResponse:
        request.state.error_code = error.code
        return JSONResponse({"code": error.code}, status_code=409)

    @api.get("/v1/design-cases/{case_id}")
    def read(case_id: str) -> dict[str, str]:
        if case_id == "refused":
            raise OAKError("OAK-EXPECTED-VERSION", f"stale {SECRET}")
        if case_id == "broken":
            raise RuntimeError(f"broken by {SECRET}")
        return {"id": case_id}

    api.add_middleware(AccessLogMiddleware, enabled=enabled)
    return api


async def _get(api: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=api, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        return await client.get(path, headers={"Authorization": f"Bearer {SECRET}"})


@pytest.mark.anyio
async def test_a_request_is_logged_by_route_template_with_a_minted_request_id(
    captured: io.StringIO,
) -> None:
    response = await _get(_application(), f"/v1/design-cases/{SECRET}?token={SECRET}")

    (line,) = [line for line in _lines(captured) if line["event"] == "request"]
    assert response.status_code == 200
    assert line["route"] == "/v1/design-cases/{case_id}"
    assert line["method"] == "GET" and line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["request_id"] == response.headers["x-oak-request-id"]
    assert SECRET not in captured.getvalue()


@pytest.mark.anyio
async def test_a_refused_request_carries_its_code_and_an_unmatched_one_no_path(
    captured: io.StringIO,
) -> None:
    api = _application()
    await _get(api, "/v1/design-cases/refused")
    await _get(api, f"/v1/{SECRET}")

    refused, unmatched = [line for line in _lines(captured) if line["event"] == "request"]
    assert refused["status"] == 409 and refused["code"] == "OAK-EXPECTED-VERSION"
    assert unmatched["route"] == "unmatched" and unmatched["status"] == 404
    assert SECRET not in captured.getvalue()


@pytest.mark.anyio
async def test_an_unhandled_error_is_logged_by_type_only(captured: io.StringIO) -> None:
    response = await _get(_application(), "/v1/design-cases/broken")

    assert response.status_code == 500
    access = [line for line in _lines(captured) if line["event"] == "request"]
    assert access[0]["status"] == 500 and access[0]["error_type"] == "RuntimeError"
    assert SECRET not in captured.getvalue()


@pytest.mark.anyio
async def test_the_access_log_can_be_turned_off(captured: io.StringIO) -> None:
    response = await _get(_application(enabled=False), "/v1/design-cases/x")

    assert response.headers["x-oak-request-id"]
    assert not [line for line in _lines(captured) if line["event"] == "request"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_run_server_configures_logging_and_one_uvicorn_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """Review L2 and L4: `oak serve` reaches run_server too, and WEB_CONCURRENCY must not
    start workers that never configured logging."""

    from oak.interfaces.api import server

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.setenv("OAK_DATABASE_URL", "postgresql+psycopg://unused@127.0.0.1/oak")
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        server.run_server("127.0.0.1", 8999, model_token="t" * 32)
        assert any(isinstance(handler.formatter, AllowlistFormatter) for handler in root.handlers)
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
        logging.captureWarnings(False)
    (options,) = calls
    assert options["workers"] == 1 and options["log_config"] is None
    assert options["access_log"] is False


def test_a_failing_one_shot_worker_logs_by_type_and_exits(
    monkeypatch: pytest.MonkeyPatch, captured: io.StringIO
) -> None:
    """Review L5: `OAK_WORKER_ONCE=1` re-raised into Python's own traceback."""

    from oak.interfaces import worker

    class _Failing:
        def run_once(self, **_: object) -> object:
            raise ValueError(f"cycle failed on {SECRET}")

    monkeypatch.setattr(worker, "configure_logging", lambda component: None)
    monkeypatch.setattr(worker, "create_persistent_worker", lambda worker_id: _Failing())
    monkeypatch.setenv("OAK_WORKER_ONCE", "1")

    with pytest.raises(SystemExit) as stopped:
        worker.main()

    assert stopped.value.code == 1
    (line,) = _lines(captured)
    assert line["event"] == "cycle_failed" and line["error_type"] == "ValueError"
    assert SECRET not in captured.getvalue()
