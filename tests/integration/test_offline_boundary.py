# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: the no-egress claim, enforced instead of asserted.

Two of the load-bearing claims in this release are that OAK makes no hosted-provider
call and that it has no mandatory network dependency (TM-13, TM-19, ADR-0012). Until
now both rested on a grep: no provider adapter ships, and the only outbound HTTP in
`src/` is the CLI's own remote mode. A grep does not survive someone adding an adapter.

So: run the whole offline reference journey with outbound sockets forcibly broken, and
separately pin the set of modules allowed to import a network client at all.
"""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "oak"

# Network-capable standard-library and third-party clients.
NETWORK_MODULES = frozenset(
    {
        "http.client",
        "urllib.request",
        "urllib.error",
        "socket",
        "socketserver",
        "asyncio.streams",
        "ftplib",
        "smtplib",
        "telnetlib",
        "httpx",
        "requests",
        "aiohttp",
        "websockets",
    }
)

# Remote CLI mode talks to an OAK control plane the operator explicitly points it at.
# The API server binds a socket; the runner dispatches to a filesystem mailbox, never a
# socket. Any addition to this set is a trust-boundary change, not a refactor.
ALLOWED_NETWORK_IMPORTERS = frozenset(
    {
        "oak/interfaces/cli/remote.py",
    }
)

pytestmark = pytest.mark.integration


class OutboundSocketError(AssertionError):
    """Raised the moment anything tries to reach the network."""


@pytest.fixture
def no_egress(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Break every outbound socket path for the duration of a test."""

    def refuse(*arguments: object, **keywords: object) -> None:
        raise OutboundSocketError("the offline journey attempted an outbound network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", refuse, raising=True)
    monkeypatch.setattr(socket, "getaddrinfo", refuse, raising=True)
    yield


def test_the_egress_guard_itself_actually_blocks(no_egress: None) -> None:
    """Guard the guard.

    If the fixture stopped patching anything, every test below it would pass
    vacuously and the no-egress claim would quietly become unenforced again.
    """

    with pytest.raises(OutboundSocketError):
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)

    with pytest.raises(OutboundSocketError):
        socket.socket().connect(("127.0.0.1", 9))

    with pytest.raises(OutboundSocketError):
        socket.getaddrinfo("example.invalid", 80)


def test_the_reference_journey_completes_with_every_outbound_socket_broken(
    no_egress: None, tmp_path: Path
) -> None:
    """Brief through plan compilation, with the network unreachable.

    `build_compiled_case` ends at `bundle_compiled`; signing, approval and
    dispatch are separate commands and are not exercised here.
    """

    from tests.runner_support import build_compiled_case

    harness = build_compiled_case(tmp_path)

    manifest = harness.workspace / ".oak" / "manifest.json"
    assert manifest.is_file()


def test_a_workspace_export_and_reimport_needs_no_network(no_egress: None, tmp_path: Path) -> None:
    from oak.adapters.persistence import FileWorkspaceRepository
    from oak.contracts import SchemaRegistry
    from tests.runner_support import build_compiled_case

    harness = build_compiled_case(tmp_path / "source")
    registry = SchemaRegistry.from_directory(ROOT / "schemas")

    export_root = tmp_path / "export"
    FileWorkspaceRepository(harness.workspace, registry).export_to(export_root)
    restored = FileWorkspaceRepository(tmp_path / "restored", registry)
    restored.import_from(export_root)

    assert restored.manifest()["artifact_index"]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
            # `from urllib import request` binds a module, and recording only the
            # package would let a new network client in without tripping this gate.
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_only_the_remote_cli_may_import_a_network_client() -> None:
    """Pin the egress surface so a new adapter cannot appear unnoticed.

    `oak.interfaces.api.server` reaches the network through uvicorn rather than by
    importing a client itself, which is why it is not in the allowlist: it binds a
    listener, it does not originate calls.
    """

    offenders: dict[str, set[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT / "src").as_posix()
        if relative in ALLOWED_NETWORK_IMPORTERS:
            continue
        network = _imported_modules(path) & NETWORK_MODULES
        if network:
            offenders[relative] = network

    assert not offenders, (
        "these modules import a network client but are not in the documented egress "
        f"surface: {offenders}"
    )


def test_no_model_or_evidence_provider_adapter_ships() -> None:
    """TM-13 is defended by absence; prove the absence rather than describing it."""

    adapters = ROOT / "src" / "oak" / "adapters" / "models"
    implementations = sorted(
        path.name for path in adapters.glob("*.py") if path.name != "__init__.py"
    )

    assert implementations == ["fake_interpreter.py"], (
        "a real model-provider adapter would move OAK inside the data path for briefs; "
        f"found {implementations}"
    )
