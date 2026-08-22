<!-- SPDX-License-Identifier: Apache-2.0 -->

# Measured performance

What OAK Community `0.7.0` was observed to do, on one machine, under a stated workload.

**These are observations, not a service level objective.** They were taken on a single
developer laptop with no controlled environment, no warm-up isolation from operating-system
caching or CPU scaling, and no concurrency. They tell you the shape of the cost and roughly
where the floor is. They do not tell you what your machine will do.

The machine-readable report, including full provenance, is
[release/0.7.0/performance.json](release/0.7.0/performance.json). Regenerate it with:

```bash
python scripts/benchmark.py --output docs/release/0.7.0/performance.json
```

## Provenance

| | |
|---|---|
| Version | `0.7.0` |
| Machine | macOS 26.3.1, arm64, 10 CPUs, 64 GiB RAM |
| Python | CPython 3.13.12 |
| Persistence | File workspace |
| Catalogue | 3 component manifests, 4 patterns (the bundled fixture) |
| Brief | `examples/briefs/public-manual-qa.yaml` |

Every figure below is from that configuration. A different catalogue size, a PostgreSQL
control plane, or a populated workspace changes them.

## Reference compiler

The reference compilation path — intake, interpretation, confirmation, candidate
generation, evaluation, selection, assurance and plan compilation, ending at
`bundle_compiled` — over 3 runs. **Signing, approval and dispatch are separate commands and
are not included in this figure**; the runner journey is timed separately and is dominated
by the host's Docker daemon:

| Measure | Value |
|---|---|
| Median | **8.66 s** |
| Range | 8.62 s – 8.66 s |

The governing requirement (`OAK-NFR-PERF-001`) asks for three variants within 120 s. One
full journey producing four candidate variants takes about 8.7 seconds here, roughly an
order of magnitude inside that budget.

Where the time goes: schema validation dominates. A fresh validator is constructed and
`check_schema` re-run on every `validate` call, and every artifact read revalidates. That
is the identified hot spot, named here so the number is explainable — it is not a Sprint 8
deliverable to fix.

## Interactive API reads

Sequential single-client reads over loopback HTTP against a real uvicorn server, with one
reference case created through `POST /v1/design-cases` and **not** interpreted — so the
workspace is at revision 1, not the eight revisions a completed journey produces:

| Endpoint | Median | p95 | p99 |
|---|---|---|---|
| `GET /version` | 0.57 ms | **0.89 ms** | 0.99 ms |
| `GET /v1/design-cases/{id}` | 29.4 ms | **30.5 ms** | 31.6 ms |
| `GET /v1/design-cases/{id}/audit` | 54.7 ms | **56.9 ms** | 59.4 ms |

`OAK-NFR-PERF-002` asks for a p95 interactive read within 500 ms. All three are inside it
by a wide margin **for this workload**, which is one freshly created case at revision 1 —
about as favourable as the measurement gets. Read cost is
history-dependent: pagination slices in Python after loading, and the audit endpoint reads
every audit artifact. Treat these as a floor.

`GET /v1/design-cases` (the list) is not measured: it requires the PostgreSQL case
directory and is unavailable in file mode.

## Workspace growth — read this one

This is the number most likely to affect a first user.

| Indexed artifacts | Manifest read (median) | p95 |
|---|---|---|
| 0 | 3.8 ms | 4.0 ms |
| 43 | **283.3 ms** | 296.1 ms |

The file workspace revalidates its entire audit lineage on every manifest read, and
**nothing in OAK ever deletes history**. One complete reference journey produces 43 indexed
artifacts and takes manifest reads from under 4 ms to over 280 ms — a factor of about 74.

Two data points cannot distinguish linear growth from super-linear growth, and this release
does not claim to know which it is. What it does claim: the cost grows, it grows steeply,
and there is no compaction, pruning or archival mechanism. A long-lived workspace will get
slower and will not get faster again. Recorded as `RR-030` in
[security/residual-risk.md](security/residual-risk.md).

The practical mitigation today is that a workspace is per design case, and `oak export`
produces a portable tree you can archive.

## Not measured

Stated rather than silently omitted:

| Measurement | Why not |
|---|---|
| Outbox drain rate under a burst | Needs a Compose stack with the worker stopped and restarted mid-burst. Not automated. `GET /v1/system/outbox-lag` gives an operator the point-in-time snapshot to sample manually |
| Durable operation restart wall-clock | Lease expiry and re-claim are exercised by `tests/integration/test_operations.py::test_operation_lease_expiry_retry_backoff_and_terminal_failure`, which drives the clock deterministically. A wall-clock figure would measure that test's fake clock, not the system. Separately, `completed_at - updated_at` is always zero because the worker captures `now` once per cycle, so job duration cannot be derived from stored state either |
| Bounded runner operation | The read-only five-operation plan runs end to end in `tests/e2e/test_runner_journey.py`; its wall-clock cost is dominated by the host's Docker daemon |
| Concurrent API load | No load driver exists. Every figure above is single-client and sequential |
| PostgreSQL control plane | Every figure above is file-mode. The persistent path was exercised for correctness, not timed |

## Known soak hazards

Not measured, but visible in the code and worth an operator knowing:

- The runner rewrites its consumed-nonces file in full on every dispatch.
- Processed dispatch directories are never cleaned up.
- The runner journal is re-read on every append.
- `OperationWorker.run_once` never heartbeats against its hard-coded 60-second lease, so a
  job approaching 60 seconds risks being re-claimed while still running.

None of these matters at the scale this release is used at. All of them get worse with
volume, and none is bounded by anything today.
