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
import math
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
    # `math.ceil`, not `round(x + 0.5)`: Python rounds halves to even, so the latter is
    # off by one at some sample counts and would not be the method the docstring names.
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
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
            "catalogue_architecture_patterns": len(list((catalogue / "patterns").glob("*.yaml")))
            if (catalogue / "patterns").is_dir()
            else 0,
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
            "One full reference case through build_compiled_case: intake, interpretation, "
            "confirmation, candidate generation, evaluation, selection, assurance and plan "
            "compilation, ending at bundle_compiled. Signing, approval and dispatch are "
            "separate commands and are NOT included in this figure."
        ),
        "requirement": "OAK-NFR-PERF-001 (three variants within 120 s)",
        **_summary(samples),
    }


GROWTH_EVENTS = (0, 8, 200, 500)


def _append_synthetic_revisions(workspace: Path, count: int, stamp: str) -> None:
    """Grow a compiled workspace by ``count`` revisions that change only an extension.

    Each revision is a real commit through the adapter (a case successor and an audit
    event, with the manifest verified in full first), so the history it leaves is one
    the adapter would accept from any command; only its content is synthetic.
    """

    from oak.adapters.persistence import FileWorkspaceRepository
    from oak.application.persistence import build_workspace_mutation
    from oak.contracts import SchemaRegistry
    from oak.domain import ArtifactReference, DesignCase, canonical_json_bytes, content_digest
    from oak.domain.artifacts import json_artifact
    from oak.domain.audit import audit_event_document

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(workspace, registry)
    for _ in range(count):
        manifest = repository.manifest()
        current_document = repository.current_case()
        assert current_document is not None
        current = DesignCase.from_document(current_document)
        # Keyed by the event's sequence, never by a loop index: an idempotency key the
        # workspace already holds replays that revision instead of appending one.
        sequence = len(manifest["audit_events"]) + 1
        extensions = dict(current.extensions or {})
        extensions["oak.community/benchmark"] = {"revision": sequence}
        successor = current.revise(status=current.status, updated_at=stamp, extensions=extensions)
        source_reference = extensions.get("oak.community/source_record_ref")
        input_digest = content_digest(canonical_json_bytes({"benchmark": sequence}))
        key = f"benchmark-revision-{sequence:06d}"
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=manifest["audit_events"][-1]["digest"],
            case_id=successor.id,
            case_version=successor.version,
            event_type="workspace_imported",
            actor="benchmark",
            tenant_id="local",
            interface_origin="cli",
            correlation_id=f"correlation-{key}",
            idempotency_key=key,
            input_digest=input_digest,
            occurred_at=stamp,
            intent_ref=successor.intent_ref,
            source_record_ref=(
                ArtifactReference.from_document(source_reference)
                if isinstance(source_reference, dict)
                else None
            ),
        )
        event = json_artifact(
            artifact_id=str(event_document["id"]),
            version=str(sequence),
            kind="audit_event",
            media_type="application/vnd.oak.audit-event+json",
            document=event_document,
        )
        successor = successor.with_audit_head(event.digest)
        case = json_artifact(
            artifact_id=successor.id,
            version=successor.version,
            kind="design_case",
            media_type="application/vnd.oak.design-case+json",
            document=successor.to_document(),
        )
        repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=current.version,
                idempotency_key=key,
                input_digest=input_digest,
                artifacts=(event, case),
                current_case_ref=case.reference,
                event_artifact=event,
                event_document=event_document,
                updated_at=stamp,
            )
        )


def _measure_workspace_point(workspace: Path, samples: int, cli_samples: int) -> dict[str, Any]:
    from oak.adapters.persistence import FileWorkspaceRepository, clear_verification_cache
    from oak.contracts import SchemaRegistry

    repository = FileWorkspaceRepository(workspace, SchemaRegistry.from_directory(ROOT / "schemas"))
    manifest = repository.manifest()
    first_reads: list[float] = []
    for _ in range(samples):
        clear_verification_cache()
        first_reads.append(_timed(repository.manifest))
    cached_reads = [_timed(repository.manifest) for _ in range(samples)]
    oak = Path(sys.executable).parent / "oak"
    command_reads = [
        _timed(
            lambda: subprocess.run(
                [str(oak), "questions", "--output", "json"],
                cwd=workspace,
                check=True,
                capture_output=True,
            )
        )
        for _ in range(cli_samples)
    ]
    return {
        "audit_events": len(manifest["audit_events"]),
        "indexed_artifacts": len(manifest["artifact_index"]),
        "manifest_read_first": _summary(first_reads),
        "manifest_read_cached": _summary(cached_reads),
        "oak_questions_command": _summary(command_reads),
    }


def measure_workspace_growth(samples: int, cli_samples: int = 5) -> dict[str, Any]:
    """Read cost against workspace depth (RR-030).

    The file workspace verifies its whole audit lineage the first time a process reads a
    manifest, so that read is a function of how much history the workspace holds; a later
    read of the same bytes in the same process skips the walk. Four depths: freshly
    initialised, the reference journey, and the journey grown to 200 and 500 audit events
    by synthetic revisions. Each point also times `oak questions`, one interpreter per
    command, which is what a CLI user pays.
    """

    from oak.adapters.persistence import FileWorkspaceRepository
    from oak.contracts import SchemaRegistry
    from tests.runner_support import build_compiled_case

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    points: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as scratch:
        empty = Path(scratch) / "empty"
        FileWorkspaceRepository(empty, registry).initialize(
            workspace_id="workspace.benchmark",
            tenant_id="local",
            created_at="2026-08-21T12:00:00Z",
        )
        point = _measure_workspace_point(empty, samples, 0)
        point["oak_questions_command"] = None
        points.append(point)
    with tempfile.TemporaryDirectory() as scratch:
        harness = build_compiled_case(Path(scratch))
        points.append(_measure_workspace_point(harness.workspace, samples, cli_samples))
        grown = len(FileWorkspaceRepository(harness.workspace, registry).manifest()["audit_events"])
        for target in GROWTH_EVENTS[2:]:
            print(f"  growing the workspace to {target} audit events…", file=sys.stderr)
            _append_synthetic_revisions(harness.workspace, target - grown, harness.now)
            grown = target
            points.append(_measure_workspace_point(harness.workspace, samples, cli_samples))
    return {
        "description": (
            "Manifest read latency at four workspace depths: freshly initialised, after the "
            "reference journey, and after synthetic revisions to 200 and 500 audit events. "
            "The first read in a process verifies the lineage in full; a cached read is a "
            "later read of the same bytes in the same process; the command figure is "
            "`oak questions --output json` as a subprocess, interpreter start-up included. "
            "Nothing in OAK deletes history, so this only grows."
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
            "control plane holding one reference case, created through the API and not "
            "interpreted."
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


MEASUREMENTS = ("reference_compiler", "workspace_growth", "api_reads", "operation_restart")


def run(
    repetitions: int, requests: int, revisions: int, only: tuple[str, ...] = MEASUREMENTS
) -> dict[str, Any]:
    report: dict[str, Any] = {"provenance": provenance(), "measurements": {}}
    measurements = report["measurements"]

    if "reference_compiler" in only:
        print("measuring the reference compiler path…", file=sys.stderr)
        measurements["reference_compiler"] = measure_reference_compiler(repetitions)

    if "workspace_growth" in only:
        print("measuring workspace read growth…", file=sys.stderr)
        measurements["workspace_growth"] = measure_workspace_growth(revisions)

    if "api_reads" in only:
        print("measuring API reads…", file=sys.stderr)
        measurements["api_reads"] = measure_api_reads(requests)

    if "operation_restart" in only:
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
    parser.add_argument(
        "--only",
        action="append",
        choices=MEASUREMENTS,
        help="run one measurement (repeatable); the default runs every one",
    )
    arguments = parser.parse_args()

    report = run(
        arguments.repetitions,
        arguments.requests,
        arguments.revisions,
        tuple(arguments.only) if arguments.only else MEASUREMENTS,
    )
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
