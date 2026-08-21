# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-005: measure OAK Community and record where the numbers came from.

There was no timing, metric or benchmark code anywhere in the project, so every
performance statement would have been an unevidenced assertion. This measures the paths
the non-functional requirements name and emits one JSON report whose header carries the
hardware, toolchain, source revision and workload it was taken on.

Numbers without that header are not evidence. A figure from one developer laptop is not a
service level objective and this report never presents one as such.

    python scripts/benchmark.py --output docs/release/0.7.0/performance.json

Measurements that need PostgreSQL are skipped, and recorded *as skipped*, unless
OAK_TEST_DATABASE_URL is set. A missing measurement is reported, never silently dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _percentile(samples: list[float], fraction: float) -> float:
    """Nearest-rank percentile; explicit because `statistics.quantiles` interpolates."""

    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered) + 0.5) - 1))
    return ordered[index]


def _summary(samples: list[float]) -> dict[str, Any]:
    return {
        "samples": len(samples),
        "min_ms": round(min(samples) * 1000, 2) if samples else None,
        "median_ms": round(statistics.median(samples) * 1000, 2) if samples else None,
        "p95_ms": round(_percentile(samples, 0.95) * 1000, 2),
        "p99_ms": round(_percentile(samples, 0.99) * 1000, 2),
        "max_ms": round(max(samples) * 1000, 2) if samples else None,
    }


def _timed(operation: Callable[[], Any]) -> float:
    start = time.perf_counter()
    operation()
    return time.perf_counter() - start


def _git(*arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def provenance() -> dict[str, Any]:
    """Everything a reader needs to decide whether these numbers apply to them."""

    from oak.runner.adapters import collect_inventory

    catalogue = ROOT / "catalogue"
    return {
        "artifact_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "source_commit": _git("rev-parse", "HEAD"),
        "source_tree_dirty": bool(_git("status", "--porcelain")),
        "hardware": collect_inventory(),
        "toolchain": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "workload": {
            "catalogue_component_manifests": len(list((catalogue / "components").glob("*.yaml")))
            if (catalogue / "components").is_dir()
            else len(list(catalogue.rglob("*.yaml"))),
            "reference_brief": "examples/briefs/public-manual-qa.yaml",
            "persistence": "file workspace",
        },
        "caveats": [
            "Measured on one developer machine, not a controlled environment.",
            "No warm-up isolation from operating-system caching or CPU scaling.",
            "These are observations, not a service level objective.",
        ],
    }


def measure_reference_compiler(repetitions: int) -> dict[str, Any]:
    """The whole brief-to-signed-dispatch reference path (OAK-NFR-PERF-001)."""

    from tests.runner_support import build_compiled_case

    samples: list[float] = []
    for _ in range(repetitions):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            start = time.perf_counter()
            build_compiled_case(root)
            samples.append(time.perf_counter() - start)
    return {
        "description": (
            "One full reference case: intake, interpretation, confirmation, candidate "
            "generation, evaluation, selection, assurance, compilation, signing and dispatch."
        ),
        "requirement": "OAK-NFR-PERF-001 (three variants within 120 s)",
        **_summary(samples),
    }


def measure_workspace_growth(samples: int) -> dict[str, Any]:
    """Read cost against workspace depth.

    The file workspace revalidates its whole audit lineage on every manifest read, so
    read latency is a function of how much history the workspace holds. Two depths are
    enough to show the shape, and the shape is what an operator needs.
    """

    from oak.adapters.persistence import FileWorkspaceRepository
    from oak.contracts import SchemaRegistry
    from tests.runner_support import build_compiled_case

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    points: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as scratch:
        empty = Path(scratch) / "empty"
        repository = FileWorkspaceRepository(empty, registry)
        repository.initialize(
            workspace_id="workspace.benchmark",
            tenant_id="local",
            created_at="2026-08-21T12:00:00Z",
        )
        points.append(
            {
                "indexed_artifacts": 0,
                "manifest_read": _summary([_timed(repository.manifest) for _ in range(samples)]),
            }
        )

    with tempfile.TemporaryDirectory() as scratch:
        harness = build_compiled_case(Path(scratch))
        compiled = FileWorkspaceRepository(harness.workspace, registry)
        indexed = len(compiled.manifest()["artifact_index"])
        points.append(
            {
                "indexed_artifacts": indexed,
                "manifest_read": _summary([_timed(compiled.manifest) for _ in range(samples)]),
            }
        )

    return {
        "description": (
            "Manifest read latency at two workspace depths: freshly initialised, and after "
            "the full reference journey. Nothing in OAK deletes history, so this only grows."
        ),
        "points": points,
    }


def measure_api_reads(requests: int) -> dict[str, Any]:
    """Interactive read latency (OAK-NFR-PERF-002).

    Measured over a real loopback socket against a real uvicorn server, not an in-process
    ASGI shim: the shim would omit the HTTP and socket cost an interactive client pays.
    """

    import socket
    import threading
    import urllib.request

    import uvicorn

    from oak.interfaces.api.app import create_app
    from tests.mcp_support import build_file_control_plane

    with tempfile.TemporaryDirectory() as scratch:
        control_plane, _ = build_file_control_plane(Path(scratch))
        application = create_app(control_plane=control_plane)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=port,
                log_level="critical",
                access_log=False,
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{port}"

        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            try:
                urllib.request.urlopen(f"{base}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.05)
        else:
            server.should_exit = True
            return {"status": "not measured", "reason": "the local API did not become ready"}

        def read(path: str) -> Callable[[], Any]:
            return lambda: urllib.request.urlopen(f"{base}{path}", timeout=10).read()

        # A real domain read, not just a static probe: create one case through the API
        # and read it back. `/v1/design-cases` (the list) needs the PostgreSQL case
        # directory, so it is unavailable in file mode and is not measured here.
        brief = (ROOT / "examples" / "briefs" / "public-manual-qa.yaml").read_text(encoding="utf-8")
        create = urllib.request.Request(
            f"{base}/v1/design-cases",
            data=json.dumps({"original_name": "public-manual-qa.yaml", "content": brief}).encode(
                "utf-8"
            ),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "benchmark-create-case-0001",
            },
            method="POST",
        )
        created = json.loads(urllib.request.urlopen(create, timeout=30).read())
        case_id = str(created["case"]["id"])

        # Discard the first few samples: the first request pays import and connection
        # warm-up that no steady-state reader experiences.
        for _ in range(5):
            read("/version")()
        version_samples = [_timed(read("/version")) for _ in range(requests)]
        case_samples = [_timed(read(f"/v1/design-cases/{case_id}")) for _ in range(requests)]
        audit_samples = [_timed(read(f"/v1/design-cases/{case_id}/audit")) for _ in range(requests)]

        server.should_exit = True
        thread.join(timeout=10)

    return {
        "description": (
            "Sequential single-client reads over loopback HTTP against a file-backed "
            "control plane holding one interpreted reference case."
        ),
        "requirement": "OAK-NFR-PERF-002 (p95 interactive read within 500 ms)",
        "caveat": (
            "One case, no concurrency, one client. Read cost is history-dependent - "
            "pagination slices in Python after loading and the audit endpoint reads every "
            "audit artifact - so a workspace with many cases and deep history will be "
            "slower. Treat this as a floor, not a service level. The design-case list "
            "endpoint is not measured: it needs the PostgreSQL case directory, which file "
            "mode does not provide."
        ),
        "version_endpoint": _summary(version_samples),
        "design_case_read": _summary(case_samples),
        "design_case_audit": _summary(audit_samples),
    }


def measure_operation_restart(database_url: str | None) -> dict[str, Any]:
    """Time to re-claim a durable operation after its lease expires."""

    if not database_url:
        return {
            "status": "not measured",
            "reason": (
                "OAK_TEST_DATABASE_URL is not set. Durable operation leases require "
                "PostgreSQL; this measurement is skipped rather than approximated."
            ),
        }

    from oak.adapters.persistence import PostgreSQLOperationStore, create_postgresql_engine

    engine = create_postgresql_engine(database_url)
    store = PostgreSQLOperationStore(engine, tenant_id="local", environment_id="benchmark")
    return {
        "status": "store constructed",
        "note": (
            "Lease re-claim timing is exercised by "
            "tests/integration/test_operations.py::test_operation_lease_expiry_retry_backoff_"
            "and_terminal_failure, which drives the clock deterministically rather than "
            "sleeping. A wall-clock figure here would measure the test's fake clock."
        ),
        "store": type(store).__name__,
    }


def run(repetitions: int, requests: int, revisions: int) -> dict[str, Any]:
    report: dict[str, Any] = {"provenance": provenance(), "measurements": {}}
    measurements = report["measurements"]

    print("measuring the reference compiler path…", file=sys.stderr)
    measurements["reference_compiler"] = measure_reference_compiler(repetitions)

    print("measuring workspace read growth…", file=sys.stderr)
    measurements["workspace_growth"] = measure_workspace_growth(revisions)

    print("measuring API reads…", file=sys.stderr)
    measurements["api_reads"] = measure_api_reads(requests)

    print("measuring durable operation restart…", file=sys.stderr)
    measurements["operation_restart"] = measure_operation_restart(
        os.environ.get("OAK_TEST_DATABASE_URL")
    )

    measurements["not_measured"] = {
        "outbox_drain_rate": (
            "Requires a Compose stack with the worker stopped and restarted mid-burst. "
            "Not automated; /v1/system/outbox-lag exposes the point-in-time snapshot an "
            "operator samples manually."
        ),
        "bounded_runner_operation": (
            "The read-only five-operation runner plan is exercised end to end by "
            "tests/e2e/test_runner_journey.py. Its wall-clock cost is dominated by Docker "
            "availability on the host, so a figure here would measure the daemon."
        ),
        "concurrent_api_load": (
            "No load driver exists. The p95 above is sequential and single-client."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure OAK Community with provenance.")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    parser.add_argument("--repetitions", type=int, default=3, help="reference compiler runs")
    parser.add_argument("--requests", type=int, default=200, help="API read samples")
    parser.add_argument("--revisions", type=int, default=25, help="manifest read samples")
    arguments = parser.parse_args()

    report = run(arguments.repetitions, arguments.requests, arguments.revisions)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
