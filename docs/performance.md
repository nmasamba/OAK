<!-- SPDX-License-Identifier: Apache-2.0 -->

# Measured performance

What OAK Community was observed to do at `0.7.0`, on one machine, under a stated
workload. Neither the `0.7.1` re-cut nor `0.8.0` changed the compile path — `0.7.1`
changed compiled content, and `0.8.0` adds an opt-in model seat that the deterministic
journey never loads — so both inherited these figures, and both release decisions record
that inheritance explicitly.

`0.9.0` did change code on the compile path that every target runs (plan compilation reads
the workspace manifest once more, and three assurance strings changed), so it was
**re-measured** on the same machine with the same workload
([release/0.9.0/performance.json](release/0.9.0/performance.json), from a clean tree at
`d5717de`). Every figure is a little higher than at `0.7.0` and none comes near its
requirement:

| | `0.7.0` | `0.9.0` | Requirement |
|---|---|---|---|
| Reference compiler, median | 8.66 s | 8.92 s (+3%) | 120 s |
| Case read, p95 | 30.5 ms | 36.8 ms | 500 ms |
| Audit read, p95 | 56.9 ms | 59.9 ms | 500 ms |
| Manifest read after the full journey, median | 283 ms | 292 ms | — |

One run on each side cannot separate a small regression from the machine's own variation,
so this is not evidence of either. The sections below keep the `0.7.0` figures and their
full description, except the workspace-growth section, which was re-measured on 2026-10-29
at four depths and supersedes the last row of this table: the first manifest read after
the reference journey is 34 ms on the current tree, not 283 ms, and the difference is
Sprint 13's schema-validator reuse, not this machine.

**These are observations, not a service level objective.** They were taken on a single
developer laptop with no controlled environment, no warm-up isolation from operating-system
caching or CPU scaling, and no concurrency. They tell you the shape of the cost and roughly
where the floor is. They do not tell you what your machine will do.

The machine-readable reports, including full provenance, are
[release/0.7.0/performance.json](release/0.7.0/performance.json), which the sections below
describe, and [release/0.9.0/performance.json](release/0.9.0/performance.json). Measure the
current tree into its own release directory, never over an earlier report:

```bash
python scripts/benchmark.py --output docs/release/$(cat VERSION)/performance.json
```

The workspace-growth curve alone, which takes a few minutes, is `--only workspace_growth`,
written beside its predecessors under `docs/performance/` with the date in the name:

```bash
python scripts/benchmark.py --only workspace_growth --output docs/performance/workspace-growth-$(date +%F).json
```

Both reports describe the API read workload as "one interpreted reference case". It is
not interpreted: the benchmark creates the case through the API and reads it back, as the
section on interactive reads says. The description in `scripts/benchmark.py` is corrected;
the recorded reports keep what the tool printed.

## Provenance

| | |
|---|---|
| Version | `0.7.0` (inherited by `0.7.1` — see [release/0.7.1/release-decision.md](release/0.7.1/release-decision.md)) |
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

Where the time went at `0.7.0`: schema validation dominated. A fresh validator was
constructed and `check_schema` re-run on every `validate` call, and every artifact read
revalidates. That was the identified hot spot, named here so the number is explainable —
it was not a Sprint 8 deliverable to fix. Since Sprint 13 `SchemaRegistry` meta-validates
each schema once and reuses its validator, so the figures above, `0.9.0`'s included,
predate that change and have not been re-measured.

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

This is the number most likely to affect a first user. It was re-measured on 2026-10-29,
on the machine above, for Tier 3's Batch A (`OAK-V1-032`, `RR-030`):
[performance/workspace-growth-2026-10-29.json](performance/workspace-growth-2026-10-29.json),
with the hardware, toolchain and workload in its `provenance`, taken from the tree at
`6261c35` with the cache change itself applied but not yet committed (`source_tree_dirty`
says so). Four depths: a freshly initialised workspace; the workspace after the reference
journey, which is 8 audit events and 43 indexed artifacts (the "43" the earlier figures
named); and that workspace grown by synthetic revisions, each a recorded audit event with
its artifacts, to 200 and 500 audit events. Three figures at each depth, ten samples of the
reads and five of the command:

| Audit events (indexed artifacts) | First read in a process, median (p95) | A later read of the same bytes, median (p95) | `oak questions --output json`, median (p95) |
|---|---|---|---|
| 0 (0) | 0.3 ms (0.5 ms) | 0.2 ms (0.4 ms) | — |
| 8 (43) | **33.8 ms** (34.4 ms) | 0.4 ms (0.4 ms) | 1.06 s (1.08 s) |
| 200 (427) | 875 ms (902 ms) | 2.4 ms (5.7 ms) | 1.94 s (2.01 s) |
| 500 (1,027) | 2.19 s (2.25 s) | 5.8 ms (5.8 ms) | 3.31 s (3.43 s) |

What the curve says:

- **The full verification is linear in the history**, at about 4.4 ms per audit event:
  the slope from 8 to 200 events and the slope from 200 to 500 agree within one per
  cent. Each event is one audit artifact and the artifacts it indexes, every one read and
  digest-checked, and that walk is what the first read in a process pays. Two points could
  not tell linear from super-linear growth; four can, through 500 events.
- **The 283 ms recorded above for the journey was mostly schema meta-validation**, which
  Sprint 13's `SchemaRegistry` removed by building each validator once; the same read is
  34 ms on the current tree. Neither release report was re-run, so the table at the top
  keeps what they measured.
- **A later read in the same process does not verify again.** The file adapter keeps a
  per-process cache of the manifests it has verified, keyed on the manifest's path and the
  digest of its bytes, holding 64 entries, consulted on reads only: a read of the same
  bytes costs the parse, under 6 ms at 500 events. The API and the worker are long-lived
  processes, so their reads after the first are the middle column. A CLI command is one
  process and pays the first read once per command, which is why `oak questions` is about
  one second of interpreter start-up plus one full verification.
- **What the cache does not change:** the first read in each process, and so the cost of
  each CLI command, grows with the history, and nothing compacts, prunes or archives it. A
  long-lived workspace's commands get slower, now at a known, linear rate, and do not get
  faster again. Recorded as `RR-030` in [security/residual-risk.md](security/residual-risk.md),
  measured and bounded, still open on that clause.
- **What the cache never does:** a mutation's validation and an export verify the manifest
  in full whatever the cache holds, object reads keep checking their digests, and a changed
  byte is a different key, so a manifest edited on disk is verified again
  (`tests/integration/test_workspace_verification_cache.py`).

The practical mitigation for a workspace that has grown is still that a workspace is per
design case, and `oak export` produces a portable tree you can archive.

## Not measured

Stated rather than silently omitted:

| Measurement | Why not |
|---|---|
| Outbox drain rate under a burst | Needs a Compose stack with the worker stopped and restarted mid-burst. Not automated. `GET /v1/system/outbox-lag` gives an operator the point-in-time snapshot to sample manually |
| Durable operation restart wall-clock | Lease expiry and re-claim are exercised by `tests/integration/test_operations.py::test_operation_lease_expiry_retry_backoff_and_terminal_failure`, which drives the clock deterministically. A wall-clock figure would measure that test's fake clock, not the system. Separately, `completed_at - updated_at` is always zero because the worker captures `now` once per cycle, so job duration cannot be derived from stored state either |
| Bounded runner operation | The read-only five-operation plan runs end to end in `tests/e2e/test_runner_journey.py`; its wall-clock cost is dominated by the host's Docker daemon |
| Concurrent API load | No load driver exists. Every figure above is single-client and sequential |
| PostgreSQL control plane | Every figure above is file-mode. The persistent path was exercised for correctness, not timed |

## Soak limits

Not measured, but bounded since Tier 3's Batch A (`RR-031`), and worth an operator knowing
what still grows:

- The runner's consumed-nonce ledger holds each nonce until its lease's expiry plus five
  minutes of skew, so it is the size of the leases in play, not of the runner's history; it
  is still rewritten whole on each accepted dispatch. A nonce whose expiry is unknown (a
  ledger written before this batch) is kept for ever.
- Processed dispatch directories are removed at the end of a run once older than
  `OAK_RUNNER_DISPATCH_RETENTION_DAYS` (default 30), except the newest and any whose
  completion is not yet ingested. Journals are never removed and grow one file per
  dispatch; `oak-runner status` reads every one.
- A journal is read and verified once per run and appended from the head kept in memory,
  so a dispatch's cost no longer grows with its own journal's length; a heartbeat reads the
  journal to name its head, at most once per `OAK_RUNNER_HEARTBEAT_SECONDS`.
- `OperationWorker.run_once` extends its lease between its steps, from each step's own
  start, so a handler may run up to the lease's 120 seconds from the moment it starts
  rather than from the cycle's; the lease itself is not configurable, and a handler that
  runs longer is still re-claimed while running (by nothing, with the one worker Compose
  runs). The runner's lease is not extended by its heartbeats, which report; an `apply`
  still stops at the lease's expiry (`OAK-RUNNER-LEASE`).
- The control plane keeps every heartbeat it records as an audit event with the message as
  an artifact, so a long install adds one event per heartbeat to the case's history, which
  the curve above prices at about 4.4 ms per event on every first read.
