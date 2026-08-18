<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S3-001–009: Serve the durable DesignCase workflow through REST and jobs

## Status

- Owner/agent: Codex (final verification completed by Claude)
- Started: 2026-08-17
- Last updated: 2026-08-18 13:05 BST
- State: done
- Claimed tasks: `OAK-S3-001`–`OAK-S3-009`

## Outcome

A local Community operator can start PostgreSQL, `oak-api`, and `oak-worker`, run the
Sprint 1–2 reference DesignCase journey through `/v1`, restart the API and worker between
stages, and obtain the same canonical case, candidate, and bundle semantic digests as the
offline file-backed CLI. Mutating retries converge, stale versions conflict, jobs resume or
fail safely after lease expiry, cancellation is cooperative and durable, and an outbox
consumer restart loses no event and does not apply an event twice.

The first observable acceptance case, for `OAK-S3-001`, is narrower: an empty PostgreSQL
database is upgraded from the baseline migration, then one repository command atomically
stores the immutable artifacts, current DesignCase pointer, transition/audit record,
idempotency result, and stable-sequence outbox event. After reconstructing the repository
against the same database, the current case and artifact digests match the file-repository
result. Injecting a failure before commit leaves all six record sets unchanged.

## Context and invariants

Sprint 1 and Sprint 2 are present on merge commit `9fdb176`. `WorkspaceRepository`,
`DesignCaseService`, and `CandidatePlanningService` already implement the offline workflow
against `FileWorkspaceRepository`. The file manifest and content-addressed objects are the
current local source of truth. The API exposes only health, readiness, and version, while
`oak-worker` is an explicit unavailable placeholder. PostgreSQL 17.6 exists in Compose but
has no application connection or schema.

This plan covers `OAK-S3-001` through `OAK-S3-009` because the canonical transaction,
idempotency, outbox sequence, durable operation, REST concurrency contract, artifact
streaming, generated OpenAPI, and tenant denial behavior form one restart/parity journey.
The first milestone deliberately proves `OAK-S3-001` and `OAK-S3-002` before transport or
job breadth is added.

The governing requirements are `OAK-FR-CTL-001`, `OAK-FR-CTL-003`,
`OAK-FR-CTL-004`, `OAK-FR-INT-001`–`006`, `OAK-FR-ARC-001`–`006`,
`OAK-FR-DEP-001`–`004`, `OAK-NFR-REL-001`–`002`, `OAK-NFR-SEC-001`,
`OAK-NFR-SEC-003`, `OAK-NFR-SEC-005`–`006`, `OAK-NFR-PORT-001`, and
`OAK-NFR-UX-001`–`002`. Accepted ADRs 0002, 0006, 0008, 0013, and 0014 govern
the modular transaction boundary, tenancy, outbox, implementation stack, and interface
parity.

The domain and compiler remain independent of FastAPI, SQLAlchemy, Alembic, PostgreSQL
drivers, transport models, and background-process mechanics. Interfaces call application
services only. PostgreSQL is one modular-monolith transaction boundary; the worker shares
application code but is a separately leased process. Runners, signing, approval, secret
resolution, dispatch, target connection, subprocess execution, and mutation remain out of
scope. `interface_origin` is audit metadata, never authority.

## Scope

### In

- Transaction and repository ports shared by file and PostgreSQL adapters.
- Reviewed, locked SQLAlchemy, Alembic, and PostgreSQL driver dependencies.
- One documented forward-only baseline migration from an empty database.
- Normalized tenant-scoped tables for immutable artifacts/versions, case pointers,
  transitions/audit records, idempotency, outbox, jobs/operations, checkpoints, consumer
  deduplication, and rebuildable projection positions.
- Repository contract parity, concurrency, rollback injection, restore, and tenant tests.
- At-least-once outbox claiming/delivery with event-ID deduplication and lag reporting.
- Bounded-attempt leased compiler/evaluation jobs, heartbeat/expiry, cancellation,
  checkpoints, retry/backoff, and explicit terminal failure.
- Real `oak-worker` entrypoint with no runner or target authority.
- `/v1` DesignCase, candidate, operation, artifact, export, and import resources mapped to
  shared application services with stable problem details, ETags, idempotency, and opaque
  pagination.
- Loopback/local actor mode, unsafe-bind protection, request/stream limits, safe errors and
  logs, and non-enumerating cross-tenant behavior.
- Reproducible OpenAPI and typed web client generation plus a local compatibility gate.
- Compose restart/interruption and file/REST semantic parity evidence.

### Out

- Runner dispatch, plan approval, signing, secret resolution, target access, apply, rollback,
  destroy, or any production/customer deployment.
- Enterprise authentication or a claim that Community local mode proves enterprise
  multi-tenant isolation.
- A mandatory broker, hosted service, model provider, or network dependency.
- Destructive database down-migrations; rollback is backup/restore followed by forward
  migration.
- `.github` workflow changes. The user explicitly deferred CI/CD edits. This conflicts with
  the CI-enforcement clause of `OAK-S3-008`; Sprint 3 will implement and test the local
  OpenAPI compatibility gate but will record CI wiring as deferred and will not claim that
  portion complete without later authorization. The known `actions/setup-node`/pnpm cache
  failure is not changed here.

## Contract and data changes

The persistence port gains explicit tenant/workspace scoping and an atomic mutation unit
that can store immutable artifact metadata/content, advance a case pointer, append one
transition/audit event, persist an idempotency result, and enqueue one stable event. The file
adapter remains supported and implements the same application behavior; existing local
workspaces remain readable and exportable.

The baseline SQL schema is new, not an invented upgrade chain. Tenant and environment scope
participate in primary/unique keys and every adapter query. Canonical payloads retain their
existing JSON Schema meaning and semantic digests; database rows are storage mappings, not a
new canonical contract. JSON payload columns do not replace normalized uniqueness,
sequencing, lease, or scope constraints.

The public API additively introduces the Sprint 3 `/v1` resources, durable Operation/problem
models, artifact/export/import resources, optimistic concurrency headers, deterministic list
ordering, and opaque cursors. Mutations require `Idempotency-Key`; case mutations require
`If-Match`. Long work returns `202` and a durable Operation. Generated OpenAPI and web client
artifacts are updated from source and locally compatibility-diffed.

## Milestones

### Milestone 1 — Atomic PostgreSQL repository parity (`OAK-S3-001`, `OAK-S3-002`)

- Work: define the transaction/storage contracts before ORM mappings; review and lock the
  three persistence dependencies; add Alembic configuration and the forward-only baseline;
  implement the PostgreSQL workspace repository and tenant-aware normalized model; extract
  the shared repository/application contract suite; cover concurrent writers, duplicate
  convergence, stale versions, injected rollback, restart, empty upgrade, representative
  Sprint 1–2 restore, and cross-tenant denial.
- Proof: start the pinned PostgreSQL service; run the migration against an empty database;
  run the same contract suite for file and PostgreSQL adapters; reconstruct the repository
  and compare current-case/audit/artifact digests; inject a pre-commit failure and query that
  artifact, pointer, transition, idempotency, and outbox counts are unchanged.
- Rollback: stop the services and restore the named local development volume from backup or
  create a new empty volume and run the forward baseline. There is no destructive downgrade.
  Reverting code/lockfiles leaves file mode intact.

### Milestone 2 — At-least-once outbox and restart-safe jobs (`OAK-S3-003`, `OAK-S3-004`)

- Work: add typed application ports for outbox claims, consumer receipts/projection
  positions, operations, leases, heartbeats, checkpoints, cancellation, retry schedule, and
  terminal failures; implement PostgreSQL adapters and the worker loop; enqueue only bounded
  compiler/evaluation kinds that call existing services.
- Proof: transactional failure publishes no event; lease expiry permits safe reclaim;
  duplicate event delivery records one consumer effect; cancellation survives restart;
  transient failures back off within the maximum attempt count; permanent/exhausted work is
  terminal and safe; lag exposes queued age/sequence versus indexed-through.
- Rollback: stop the worker. Leased work expires into a reclaimable state; no job has approval,
  runner, secret, target, or mutation authority. Projection tables can be rebuilt from outbox
  events.

### Milestone 3 — Shared-service REST workflow (`OAK-S3-005`, `OAK-S3-006`)

- Work: create typed request/response and problem models, local actor/tenant context mapping,
  repository/application bootstrap, DesignCase/candidate commands and queries, durable
  operation status/cancel resources, ETag/If-Match handling, idempotency conflicts, safe
  error mapping, and deterministic opaque pagination.
- Proof: integration tests call every listed Sprint 3 resource through ASGI and compare
  semantic results/denials with local service calls; duplicate requests converge; stale ETags
  return a stable conflict; long work returns and completes a durable Operation; tenant B
  cannot distinguish tenant A's object from a missing object.
- Rollback: stop API/worker and continue using offline CLI/file workspaces. Existing canonical
  data remains portable and readable.

### Milestone 4 — Bounded portability, generated contracts, and security (`OAK-S3-007`–`009`)

- Work: implement bounded digest/media-typed artifact streaming and tenant-safe export/import;
  regenerate OpenAPI and typed web client; add and test a local compatibility diff command;
  enforce loopback defaults, explicit unsafe bind, body/header/artifact limits, sanitized
  problem/log output, and cross-tenant negative cases; document migrations, backup/restore,
  restart, and the deferred CI gate.
- Proof: export/import round trip preserves digests; oversized/tampered/cross-tenant requests
  fail without state change or existence leakage; committed OpenAPI/client regeneration is
  clean; the local breaking-change gate fails on a controlled incompatible fixture; API and
  worker restarts between reference stages still finish with CLI-equal semantic digests.
- Rollback: disable the network processes and retain canonical export. Database rollback uses
  restore-forward. Generated artifacts can be regenerated from the previous source contract.

## Verification

- Migration upgrade from empty PostgreSQL, representative data restore, restart, and
  restore-forward documentation tests.
- Shared file/PostgreSQL repository and application contract suites, including atomic
  rollback, concurrency, idempotency, stale version, digest lineage, and tenant scope.
- Outbox at-least-once redelivery, stable aggregate sequence, consumer deduplication,
  projection rebuild/indexed-through, lag, poison/failure, and restart tests.
- Job lease contention, heartbeat/expiry, checkpoint, cooperative cancellation, bounded
  retry/backoff, terminal failure, and worker restart tests.
- `/v1` happy, malformed, oversized, stale, duplicate, missing, cross-tenant, cancellation,
  pagination, and safe-problem tests.
- Artifact/export/import bounds, digest verification, symlink/path, media type, tenant, and
  interrupted publication tests.
- OpenAPI reproduction, compatibility diff, typed client build/typecheck, and local gate.
- `make check`, `make build`, `make audit`, `make sbom`, Compose exit journey, documentation
  terminology, agent-ignore, secret, import-boundary, and `.github`-unchanged checks.

## Security, privacy and authority review

Briefs, imported content, headers, target profiles, catalogue documents, and operation inputs
are untrusted. Transport limits apply before application dispatch; canonical/schema and
digest checks remain authoritative. Errors, audit events, logs, job failures, and operation
results contain safe identifiers/codes and correlation IDs, not source bodies, credentials,
raw provider output, stack traces, or private reasoning.

Local actor mode is explicit and binds requests to a configured local tenant. Unsafe
non-loopback binding still requires an explicit opt-in and does not become enterprise
authentication. Tenant/environment scope is enforced in uniqueness constraints and every
repository/outbox/job/artifact query. Cross-tenant requests use non-enumerating behavior.
Worker leases grant only the named bounded application job; they never grant approval,
signing, runner dispatch, target access, shell, or subprocess authority.

## Operational and rollback plan

Apply the baseline migration before starting the persistent API or worker. Readiness reports
only safe dependency status. Back up the local PostgreSQL data before future forward
migrations. Because this is the first server schema, supported recovery is restore into a
clean database followed by forward migration; source-controlled down-migrations are omitted
to avoid destructive rollback. The representative Sprint 1–2 export/restore test proves
canonical portability independent of the database.

Stopping a worker leaves an active lease that expires and can be reclaimed. Cancellation is
durable and cooperative. Bounded retry and explicit terminal states prevent retry storms or
silent success. Outbox publication is at least once, not exactly once; consumer receipts
deduplicate by event ID. Projections are disposable and never authorize state transitions.

The failure surface is the explicitly local Community Compose environment and test
databases. No customer or production environment is authorized or contacted.

## Progress

- [x] 2026-08-17 19:34 BST Verified PRs #2 and #3 merged, fetched origin, fast-forwarded
  `main` to `9fdb176`, and created `codex/sprint-3-persistent-rest-jobs`.
- [x] 2026-08-17 19:34 BST Read repository status, Sprint 3, persistence/interface/release
  architecture, relevant requirements and recipes, interface/repository contracts, accepted
  ADRs 0002/0006/0008/0013/0014, and completed Sprint 1–2 plans.
- [x] 2026-08-17 19:34 BST Claimed `OAK-S3-001` with the atomic PostgreSQL transaction and
  restart/digest acceptance case above.
- [x] Added and applied the forward-only `0001_sprint3_baseline` to an empty local
  PostgreSQL database. `alembic check` found no model drift after the baseline.
- [x] Implemented the tenant/environment/workspace-scoped PostgreSQL repository and ran the
  shared file/PostgreSQL restart, concurrency, rollback, tenant, idempotency, and application
  digest-lineage contract suite. Injected pre-commit failure left artifact/case/head/
  transition/idempotency/outbox counts unchanged.
- [x] Implemented stable-ID at-least-once outbox claims, lease expiry/redelivery, consumer
  receipts, projection positions, delivery release, and observable lag. A restarted consumer
  received the same event ID twice and applied it once.
- [x] Implemented durable typed Operations, leases, heartbeat, checkpoints, bounded attempts,
  deterministic backoff, cooperative cancellation, cancellation command provenance, safe
  failures, and the real compiler/outbox `oak-worker` entrypoint.
- [x] Bound Operation idempotency to semantic command input, made concurrent insert races
  converge on the winning durable row, and verified that a completed retry returns before an
  obsolete case-version precondition is re-evaluated while preserving the first audit context.
- [x] Split `CreateDesignCase` and `InterpretBrief` into distinct immutable transactions while
  preserving the local `oak design` composite flow through those same application methods.
- [x] Added every Sprint 3 DesignCase/candidate/Operation endpoint, ETag/If-Match and
  idempotency handling, safe problems/correlation IDs, local actor/tenant binding,
  deterministic opaque pagination, artifact download, outbox lag, and bounded export/import.
- [x] Proved the full REST/worker reference journey reaches the same semantic case projection,
  `candidate-03`, deployment-bundle, and semantic-manifest digests as the file application
  journey when given identical semantic inputs and times.
- [x] Added digest-verified PostgreSQL export, atomic restore into a fresh PostgreSQL scope,
  file/PostgreSQL round-trip parity, bounded REST export/import, and tamper denial.
- [x] Regenerated OpenAPI and the typed TypeScript client; added a local compatibility
  signature and a controlled removal test. `.github` remains unchanged as required.
- [x] 2026-08-18 Completed the remaining repository-wide, image/Compose, audit, SBOM, and
  clean-diff verification in an environment without the earlier approval/sandbox limits.
  `pnpm install --frozen-lockfile` restored the locked web workspace; web format/type/build,
  the full `make check` aggregate, `make audit` (no known vulnerabilities), and `make sbom`
  all passed; all seven end-to-end tests passed, including the previously sandbox-blocked
  process-level loopback API test.
- [x] 2026-08-18 Ran the complete integration suite against the pinned Compose
  `postgres:17.6-alpine` image (40 passed, 4 file-only parameter skips), including the
  REST/worker digest-parity journey and the PostgreSQL repository/outbox/operation contracts.
- [x] 2026-08-18 Executed the pinned PostgreSQL 17.6 Compose exit journey: built all images,
  applied `0001_sprint3_baseline` to the pinned database, served `/version` (`0.5.0.dev5`)
  directly and web-proxied, and completed the full `/v1` reference workflow to
  `bundle_compiled` at case `0.1.7` with API/worker restarts between stages and a durable
  compile Operation surviving a mid-flight worker restart. Teardown left no project
  containers; named volumes persist.

## Decisions

- 2026-08-17 Use one plan for `OAK-S3-001`–`009` because storage, jobs, REST concurrency,
  artifact portability, and generated contracts share one durable transaction lineage and
  exit journey.
- 2026-08-17 Treat the first Alembic revision as a documented empty-database baseline. Do not
  invent prior PostgreSQL revisions or ship destructive downgrade logic; recovery is
  restore-forward.
- 2026-08-17 Preserve file mode as the account-free offline path and compare both adapters at
  the application boundary.
- 2026-08-17 Implement only a local OpenAPI compatibility gate. `.github` CI wiring and the
  unrelated pnpm-cache workflow repair remain explicitly unauthorized and deferred.
- 2026-08-17 Use SQLAlchemy 2.0, Alembic and Psycopg 3 only inside the replaceable PostgreSQL
  adapter/migration boundary. Their licence, maintenance, security and replacement review is
  recorded in `docs/dependencies.md` and the exact resolutions are locked.
- 2026-08-17 Preserve historic audit/interface origin on canonical import. The import command
  is tenant/idempotency scoped but does not rewrite imported audit events merely to label the
  transport that restored them.
- 2026-08-17 Define REST export as a bounded base64 envelope around the same manifest and
  digest-addressed bytes used by directory export; it is a transport mapping, not a second
  canonical format.

## Discoveries and follow-ups

- GitHub GraphQL returned transient 503 responses for PR #2; the GitHub REST endpoint
  confirmed it merged at `955b6be`, and PR #3 merged at `9fdb176`.
- The host test PostgreSQL available during development is 14.18, while the pinned Compose
  service remains PostgreSQL 17.6. Repository/migration behavior passed on the host instance;
  the final Compose proof must exercise the pinned image before claiming the topology exit.
- Changing package metadata caused pnpm to recreate `node_modules`; its network restoration
  was denied by the approval system after the Python/OpenAPI steps completed. This is a local
  verification-environment limitation, not a change to lockfiles or source behavior.
  Resolved 2026-08-18: the frozen-lockfile install succeeded from the local store.
- The Sprint 0-era `oak-postgres-data` volume (created 2026-08-14) had been initialised under
  a different password, so the first pinned-17.6 `migrate` run failed authentication. The
  database was empty; recovery used `ALTER ROLE oak WITH PASSWORD` over the container's local
  trust socket rather than volume deletion, consistent with the restore-forward posture.
  `POSTGRES_PASSWORD` only applies at first initialisation of a data volume.
