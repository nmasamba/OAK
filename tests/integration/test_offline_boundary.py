# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: the no-egress claim, enforced instead of asserted.

One of the load-bearing claims in this release is that OAK has no mandatory network
dependency (TM-19, ADR-0012). The other used to be that it makes no hosted-provider call
at all; since Sprint 9 it is narrower and more useful: OAK calls a provider only when a
user has configured one, through one module, to that provider's own hosts.

Both claims are enforced rather than described. The offline reference journey runs with
outbound sockets forcibly broken; the set of modules allowed to import a network client
is pinned; the model-adapter file set is pinned; and the deterministic journey is shown,
in a fresh interpreter, never to load a hosted-provider module at all.
"""

from __future__ import annotations

import ast
import json
import re
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "oak"

# Network-capable standard-library and third-party clients, plus the model-provider SDKs
# and their transports. An SDK import is a network client by another name: without these
# entries a provider adapter could reach the network without tripping this gate.
NETWORK_MODULES = frozenset(
    {
        "http.client",
        "urllib.request",
        "urllib.error",
        "socket",
        "socketserver",
        "ssl",
        "asyncio.streams",
        "ftplib",
        "smtplib",
        "telnetlib",
        "httpx",
        "httpcore",
        "urllib3",
        "anyio",
        "h11",
        "h2",
        "requests",
        "aiohttp",
        "websockets",
        "openai",
        "anthropic",
        "google.genai",
        "google.generativeai",
        "google.auth",
        "huggingface_hub",
        "boto3",
        "botocore",
        "ollama",
        "mistralai",
        "cohere",
    }
)

# Remote CLI mode talks to an OAK control plane the operator explicitly points it at.
# The API server binds a socket; the runner dispatches to a filesystem mailbox, never a
# socket. The model transport is the single outbound path to a configured model provider,
# and it exists so that this set can stay this short: every provider profile, the hosted
# interpreter and the catalogue lookup go through it rather than opening their own
# connection. Any addition to this set is a trust-boundary change, not a refactor.
ALLOWED_NETWORK_IMPORTERS = frozenset(
    {
        "oak/interfaces/cli/remote.py",
        "oak/adapters/models/transport.py",
    }
)

# The complete set of model adapters. `fake_interpreter` is the offline contract double;
# the other four exist only when a user has configured a provider. Adding a file here is a
# change to what OAK can send a brief to, so it is listed rather than globbed.
DOCUMENTED_MODEL_ADAPTERS = (
    "fake_interpreter.py",
    "hosted_interpreter.py",
    "huggingface_catalogue.py",
    "providers.py",
    "transport.py",
)

# Modules the deterministic journey must never pull in. Importing one does not by itself
# send anything, but it is the step before doing so, and `transport` brings `ssl` and
# `socket` with it.
HOSTED_MODEL_MODULES = (
    "oak.adapters.models.transport",
    "oak.adapters.models.providers",
    "oak.adapters.models.hosted_interpreter",
    "oak.adapters.models.huggingface_catalogue",
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


def _declared_distributions() -> set[str]:
    """Import roots the shipped package is allowed to have, from `pyproject.toml` itself."""

    lines = (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    declared: set[str] = set()
    collecting = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("dependencies = [", "keychain = [")):
            collecting = True
            continue
        if collecting:
            if stripped == "]":
                collecting = False
                continue
            name = stripped.strip(",").strip('"')
            if name:
                # `psycopg[binary]>=3.3,<4` -> `psycopg`.
                declared.add(re.split(r"[<>=!\[]", name)[0].strip().replace("-", "_").casefold())
    # Import names that differ from the distribution that provides them.
    declared.update({"yaml"})
    # Direct imports of a declared dependency's own framework. Each is a hard requirement of
    # something in the list above, ships with it, and is not a new distribution in the
    # release closure: `starlette` is what FastAPI is built on, and `referencing` is the
    # resolver `jsonschema` uses. Neither reaches a network.
    declared.update({"starlette", "referencing"})
    return declared


def test_no_module_imports_a_distribution_the_package_does_not_declare() -> None:
    """The structural half of the egress gate: an unknown third party cannot appear.

    The allowlist below names the network clients we know about, which is exactly the
    weakness an adversarial review probed: a module importing some *other* provider SDK
    passes a list of names it is not on. So this test does not enumerate. It resolves every
    top-level import under `src/oak` and fails on anything that is neither the standard
    library, `oak` itself, nor a distribution `pyproject.toml` declares — which is also the
    check that keeps `docs/dependencies.md`'s "no runtime HTTP dependency was added" true.
    """

    allowed = _declared_distributions() | set(sys.stdlib_module_names) | {"oak"}
    offenders: dict[str, set[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        roots = {name.split(".")[0] for name in _imported_modules(path)}
        undeclared = {root for root in roots if root.casefold() not in allowed}
        if undeclared:
            offenders[path.relative_to(ROOT / "src").as_posix()] = undeclared

    assert not offenders, (
        "these modules import a distribution the package does not declare; adding one is a "
        f"dependency decision and belongs in docs/dependencies.md first: {offenders}"
    )


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


def test_the_model_adapter_set_is_exactly_the_documented_one() -> None:
    """TM-13 is no longer defended by absence, so pin what the egress surface is.

    Community can now send a brief to a provider the user configured. The claim that
    replaces "no adapter ships" is narrower and checkable: these five files are the whole
    of it, only one of them may open a connection, and that one is in the allowlist above.
    """

    adapters = ROOT / "src" / "oak" / "adapters" / "models"
    implementations = sorted(
        path.relative_to(adapters).as_posix()
        for path in adapters.rglob("*.py")
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    )

    assert implementations == sorted(DOCUMENTED_MODEL_ADAPTERS), (
        "a new model adapter changes what OAK can send a brief to; add it to "
        f"DOCUMENTED_MODEL_ADAPTERS and to the threat model deliberately. Found {implementations}"
    )


def test_only_the_transport_among_the_model_adapters_imports_a_network_client() -> None:
    """The other four are data, parsing and prompt construction; none opens a connection."""

    adapters = ROOT / "src" / "oak" / "adapters" / "models"
    for name in DOCUMENTED_MODEL_ADAPTERS:
        if name == "transport.py":
            continue
        network = _imported_modules(adapters / name) & NETWORK_MODULES
        assert not network, f"{name} imports a network client: {sorted(network)}"


def test_the_deterministic_journey_never_imports_a_hosted_model_module() -> None:
    """A fresh interpreter runs the offline journey; the provider modules stay unloaded.

    In-process this would prove nothing: another test module in the same session will have
    imported the transport already. So the journey runs in its own interpreter and reports
    what it loaded.
    """

    program = "\n".join(
        (
            "import json, sys, tempfile, pathlib",
            f"sys.path.insert(0, {str(ROOT)!r})",
            "from tests.runner_support import build_compiled_case",
            "with tempfile.TemporaryDirectory() as directory:",
            "    harness = build_compiled_case(pathlib.Path(directory))",
            "    manifest = json.loads(",
            "        (harness.workspace / '.oak' / 'manifest.json').read_text('utf-8')",
            "    )",
            "    kinds = sorted({entry['kind'] for entry in manifest['artifact_index']})",
            "modules = sorted(n for n in sys.modules if n.startswith('oak.'))",
            "print(json.dumps({'modules': modules, 'kinds': kinds}))",
        )
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    reported = json.loads(completed.stdout.splitlines()[-1])
    loaded = set(reported["modules"])

    # Guard the guard: a journey that silently did nothing would import the same modules,
    # so the subprocess reports what it actually compiled and that is checked first.
    assert {
        "brief_source",
        "source_record",
        "system_intent",
        "design_case",
        "architecture_candidate",
        "deployment_bundle",
        "runner_plan",
    } <= set(reported["kinds"]), reported["kinds"]

    assert "oak.adapters.models.fake_interpreter" not in loaded
    for module in HOSTED_MODEL_MODULES:
        assert module not in loaded, f"the deterministic journey imported {module}"
    assert "interpretation_proposal" not in reported["kinds"]
