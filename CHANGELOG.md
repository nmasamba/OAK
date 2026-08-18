<!-- SPDX-License-Identifier: Apache-2.0 -->

# Changelog

All notable changes to OAK Community are recorded here.

## Unreleased

### Added

- Sprint 4 workspace shell for `OAK-S4-001`: routed case list/create/open screens,
  server-status-driven actions, durable operation polling with cancellation, audit
  timeline, and stale-version conflict recovery, backed by additive tenant-scoped
  design-case list and audit trail REST resources and `/v1` forwarding in the nginx and
  Vite proxies.
- Sprint 3 PostgreSQL control plane and `/v1` REST workflow for `OAK-S3-001` through `OAK-S3-009`.
- Forward-only Alembic baseline with tenant/environment/workspace-scoped immutable artifacts,
  DesignCase heads and versions, transitions, idempotency, outbox, operations, checkpoints,
  consumer receipts, and rebuildable projection positions.
- Shared file/PostgreSQL repository contract suite covering restart, concurrency, atomic
  rollback, tenant denial, digest lineage, and canonical export/restore.
- At-least-once outbox leases with stable event IDs, consumer deduplication, projection lag,
  and a real separately leased `oak-worker` process.
- Durable generate/evaluate/compile Operations with checkpoints, lease expiry, bounded retry,
  safe terminal failure, cooperative cancellation, and cancellation command provenance.
- DesignCase, candidate, Operation, artifact, export, and import REST resources with local
  actor/tenant binding, ETags, required idempotency keys, optimistic concurrency, safe problem
  details, deterministic opaque pagination, and bounded requests/artifacts.
- Generated OpenAPI 3.1 and typed TypeScript client for the persistent workflow, plus a tested
  local breaking-change gate. CI workflow enforcement remains explicitly deferred.
- Sprint 2 offline compiler flow for `OAK-S2-001` through `OAK-S2-011`.
- Governed synthetic catalogue snapshots and provider-neutral baseline, minimum, balanced, and high-assurance pattern contracts.
- Deterministic hardware, deployment, security, licence, locality, and compatibility constraints with fail-closed unknown handling.
- Transparent cost, latency, quality, operability, and energy ranges with estimator/calibration metadata and Pareto sensitivity.
- Digest-linked fixture evaluation results, immutable selection decisions, assurance plans, and a stable `candidate-03` exit path.
- Canonical review bundle and draft typed runner plan with byte-stable normalized semantic manifests.
- Sprint 1 offline `DesignCase` workflow for `OAK-S1-001` through `OAK-S1-010`.
- Atomic file-backed workspace with immutable content-addressed artifacts, expected-version checks, idempotent mutations, append-only audit lineage, and digest-verified export/import.
- Bounded YAML, JSON, Markdown, and text intake with source quarantine and adversarial path, type, size, structure, and Unicode checks.
- Deterministic typed intent interpretation with complete scalar provenance, stable findings, and at most five ranked clarification questions.
- Provider-neutral optional interpretation proposals, resource limits, and a deterministic failure-injection adapter; no model provider is required.
- Confirmation successors for confirm, correct, reject, and accept-risk decisions, exposed through human, JSON, and YAML CLI commands.
- Complete Sprint 0 walking skeleton for `OAK-S0-001` through `OAK-S0-009`.
- Locked Python package with domain, compiler, application, port, adapter, interface, contract, and runner boundaries.
- Canonical schema registry and lossless public YAML/JSON runtime conformance suite.
- Shared application-service version/readiness queries exposed through the `oak` CLI and loopback-safe `oak-api` HTTP process.
- Generated OpenAPI 3.1 artifact, strict TypeScript client, and accessible local status shell.
- Local PostgreSQL/API/web Compose harness with health checks and loopback-only published ports.
- Stable Make entrypoints, CI, dependency audits, secret-pattern checks, and development SBOM generation.
- Repository hygiene rules that exclude agent state, secrets, build output, local runtime data, and editor files.
- Separate local-source compatibility from exact CI/container builder pins, with an executable drift check across toolchain files, package metadata, images, CI, and documentation.

### Security

- PostgreSQL uniqueness constraints and every repository, operation, outbox, artifact, and
  projection query include tenant/environment scope; cross-tenant REST requests return the
  same safe not-found shape as missing resources.
- API binding remains loopback-only unless explicitly acknowledged, dependency failures expose
  only coarse readiness, request/export sizes are bounded, and problems omit payloads, stack
  traces, provider output, credentials, and private reasoning.
- Worker requests reject command, shell, executable, and argument-vector fields and can invoke
  only deterministic candidate generation, evaluation, or draft bundle compilation. They have
  no approval, signing, runner, secret, target connection, subprocess, or mutation authority.
- Catalogue and target inputs are bounded, schema-validated, alias/symlink safe, and cannot select executable behavior.
- Target profiles are bound to command tenancy and checked for declared platform, capacity, and read-only planning capabilities before bundle publication.
- Immutable evaluation results cannot be overwritten by a second non-idempotent evaluation.
- Runner-plan parameter schemas recursively reject command, shell, executable, and argument-vector fields; Sprint 2 operations are non-mutating and never dispatched.
- Raw brief content remains an untrusted, separate artifact; text instructions cannot invoke tools or approve claims.
- Workspace publication uses a lock and atomic manifest replacement, while import rejects symlinks, corruption, digest mismatch, and artifact identity tampering.
- Idempotent lookup now follows actor/correlation and tenant-context validation.
- The initial harness is non-mutating and binds its API to loopback by default.
- Dependency build hooks are denied by default except for the explicitly reviewed, lockfile-pinned `esbuild` hook.
- Vite was upgraded to 7.3.6 after the initial dependency audit identified high-severity advisories in 7.1.4.
