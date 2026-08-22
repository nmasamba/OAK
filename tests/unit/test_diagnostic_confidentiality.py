# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: a rejected value must never travel back out in a diagnostic.

The security invariants require secret values to stay out of exceptions, logs and
traces, and TM-10 names logs as a tenant-data leak path. Three concrete paths violated
that before this release:

* `jsonschema` builds most messages by interpolating the offending value, so
  `ContractValidationError` — whose docstring called itself "payload-safe" — and the
  MCP tool-argument error both echoed it. The REST layer already dropped it, so the
  two interfaces were not at parity.
* SQLAlchemy embeds bound statement parameters in `StatementError`. Canonical
  documents, including brief text, are bound parameters, and uvicorn's error logger
  writes the traceback to stderr even with `access_log=False`.

These tests use a marker string that must never appear in any diagnostic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from oak.contracts import ContractValidationError, SchemaRegistry, payload_safe_reason

ROOT = Path(__file__).resolve().parents[2]
SECRET = "sk-live-DO-NOT-ECHO-THIS-VALUE"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


@pytest.mark.parametrize(
    ("schema", "instance"),
    [
        ({"type": "integer"}, SECRET),
        ({"type": "string", "maxLength": 4}, SECRET),
        ({"type": "string", "pattern": "^a$"}, SECRET),
        ({"enum": ["a", "b"]}, SECRET),
        ({"type": "array", "minItems": 3}, [SECRET]),
        ({"type": "array", "maxItems": 1}, [SECRET, SECRET]),
        ({"type": "array", "uniqueItems": True}, [SECRET, SECRET]),
        ({"type": "object", "minProperties": 2}, {SECRET: 1}),
        ({"type": "object", "propertyNames": {"maxLength": 2}}, {SECRET: 1}),
    ],
)
def test_payload_safe_reason_never_echoes_the_rejected_value(
    schema: dict[str, object], instance: object
) -> None:
    validator = validator_for(schema)(schema)
    errors = list(validator.iter_errors(instance))

    assert errors, "the probe must actually fail validation"
    for error in errors:
        assert SECRET not in payload_safe_reason(error), error.validator


def test_payload_safe_reason_still_names_the_failed_constraint() -> None:
    """Safe must not mean useless: the caller still learns what was wrong."""

    schema = {"type": "string", "maxLength": 4}
    error = next(iter(validator_for(schema)(schema).iter_errors(SECRET)))

    reason = payload_safe_reason(error)

    assert "maxLength" in reason
    assert "4" in reason


def test_payload_safe_reason_keeps_structural_messages_verbatim() -> None:
    """A missing required key names the key, which the caller already knows."""

    schema = {"type": "object", "required": ["title"]}
    error = next(iter(validator_for(schema)(schema).iter_errors({})))

    assert payload_safe_reason(error) == "'title' is a required property"


def test_a_canonical_validation_failure_does_not_echo_document_content(
    registry: SchemaRegistry,
) -> None:
    with pytest.raises(ContractValidationError) as refusal:
        registry.validate(
            "design-case.schema.json",
            {"id": SECRET, "schema_version": SECRET, "version": SECRET, "title": SECRET},
        )

    assert SECRET not in str(refusal.value)
    assert refusal.value.path.startswith("/")


def test_the_mcp_server_reports_argument_errors_without_the_argument() -> None:
    """MCP frames land in an agent client's transcript.

    The REST layer already drops the offending value (`_field_problems` reads only
    `loc` and `msg`); MCP passed `jsonschema`'s message through verbatim, so the two
    transports were not at parity on what a refusal discloses.
    """

    from oak.interfaces.mcp.server import MCPServer
    from oak.interfaces.mcp.tools import MCPToolExecutor

    class _Guard:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"argument validation must refuse before dispatch: {name}")

    executor = MCPToolExecutor(
        _Guard(),  # type: ignore[arg-type]
        local_actor="local-user",
        local_tenant="local",
        clock=lambda: "2026-08-21T12:00:00Z",
    )
    server = MCPServer(executor, server_version="test")

    frame = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "arguments": {"original_name": SECRET * 400, "content": SECRET},
                "name": "oak_design_case_create",
            },
        }
    ).encode("utf-8")
    response = server.handle_frame(frame)

    rendered = json.dumps(response)
    assert SECRET not in rendered, rendered[:400]


def test_the_database_engine_hides_bound_statement_parameters() -> None:
    """Brief text is a bound parameter; SQLAlchemy embeds those by default."""

    import sqlalchemy

    from oak.adapters.persistence import create_postgresql_engine

    engine = create_postgresql_engine("postgresql+psycopg://oak:pw@127.0.0.1:1/oak")

    assert engine.hide_parameters is True

    # Prove the property with a real driver rather than trusting the flag alone.
    probe = sqlalchemy.create_engine("sqlite://", hide_parameters=True)
    with probe.begin() as connection:
        connection.exec_driver_sql("create table t (a integer)")
    with pytest.raises(sqlalchemy.exc.StatementError) as failure, probe.begin() as connection:
        connection.execute(
            sqlalchemy.text("insert into t (a, missing) values (:a, :m)"),
            {"a": 1, "m": SECRET},
        )

    assert SECRET not in str(failure.value)
