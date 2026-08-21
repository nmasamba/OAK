# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-001/006/008 installed MCP and validator entrypoint behavior."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OAK = ROOT / ".venv" / "bin" / "oak"
OAK_MCP = ROOT / ".venv" / "bin" / "oak-mcp"
WEBHOOK_EXAMPLE = ROOT / "examples" / "example-webhook-envelope.yaml"
PUBLISHER_IDENTITY = ROOT / "examples" / "portal" / "webhook-publisher.identity.json"


def test_installed_mcp_entrypoint_without_a_database_fails_closed() -> None:
    environment = {**os.environ}
    environment.pop("OAK_DATABASE_URL", None)
    without_db = subprocess.run(
        [str(OAK_MCP)],
        input=b"",
        cwd=ROOT,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    assert without_db.returncode != 0
    assert b"OAK-MCP-CONFIG" in without_db.stderr


def test_installed_mcp_entrypoint_handshakes_and_lists_the_bounded_tools() -> None:
    database_url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for the MCP handshake e2e test")
    frames = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    payload = "".join(json.dumps(frame) + "\n" for frame in frames).encode("utf-8")
    environment = {
        **os.environ,
        "NO_PROXY": "*",
        "no_proxy": "*",
        "OAK_DATABASE_URL": database_url,
    }
    result = subprocess.run(
        [str(OAK_MCP)],
        input=payload,
        cwd=ROOT,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert responses[0]["result"]["serverInfo"]["name"] == "oak-mcp"
    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert "oak_design_case_create" in tool_names
    assert not any(
        term in name
        for name in tool_names
        for term in ("approve", "apply", "secret", "dispatch", "shell")
    )


def test_installed_validate_verifies_the_signed_webhook_example() -> None:
    passed = subprocess.run(
        [
            str(OAK),
            "validate",
            "webhook",
            str(WEBHOOK_EXAMPLE),
            "--public-key",
            str(PUBLISHER_IDENTITY),
            "--output",
            "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        timeout=30,
    )
    assert passed.returncode == 0, passed.stderr
    document = json.loads(passed.stdout)
    assert document["valid"] is True
    assert document["kind"] == "webhook"

    tampered = subprocess.run(
        [
            str(OAK),
            "validate",
            "webhook",
            str(WEBHOOK_EXAMPLE),
            "--public-key",
            "QXR0YWNrZXJLZXlBdHRhY2tlcktleUF0dGFja2VyS2V5QQ==",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        timeout=30,
    )
    assert tampered.returncode == 2
    assert "OAK-VALIDATE-WEBHOOK-KEY" in (tampered.stdout + tampered.stderr)


def _oak(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(OAK), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        timeout=30,
    )


def test_installed_cli_exposes_the_sprint_7_surface() -> None:
    """Assert the surface behaves, not how the help renderer paints it.

    Scraping `oak --help` couples the test to Rich's terminal-width and styling
    decisions, which differ between a developer machine and CI. Invoking the
    surface proves the same thing more strongly: the option and subcommands are
    registered, parsed, and routed.
    """

    # The mcp and validate subcommands exist and are invocable.
    assert _oak("mcp", "--help").returncode == 0
    assert _oak("validate", "--help").returncode == 0

    # `validate` rejects an unknown kind with the stable code rather than a crash.
    unknown_kind = _oak("validate", "everything", str(ROOT))
    assert unknown_kind.returncode == 2
    assert "OAK-VALIDATE-KIND" in unknown_kind.stdout + unknown_kind.stderr

    # The root --server option is registered and routes into remote mode: a
    # local-only command must refuse rather than acting on local state.
    refused = _oak("--server", "http://127.0.0.1:9", "keys", "show")
    assert refused.returncode == 2
    assert "OAK-REMOTE-UNSUPPORTED" in refused.stdout + refused.stderr

    # A remote-capable command reaches the transport and fails closed when the
    # server is unreachable, proving --server is parsed rather than ignored.
    unreachable = _oak(
        "--server", "http://127.0.0.1:9", "questions", "design-case.public-manual-qa"
    )
    assert unreachable.returncode == 2
    assert "OAK-REMOTE-UNAVAILABLE" in unreachable.stdout + unreachable.stderr
