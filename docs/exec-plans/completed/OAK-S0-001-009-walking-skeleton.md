<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S0-001–009: Serve the Community walking skeleton

## Status

- Owner/agent: Codex
- Started: 2026-08-14
- Last updated: 2026-08-14 17:11 BST
- State: complete

## Outcome

A contributor can bootstrap one locked monorepo, run `oak --version`, serve the shared system-information query through `oak-api` or `oak serve`, inspect `/healthz`, `/readyz`, and `/version`, view the same version in a minimal web shell, validate every canonical schema/example, and run one stable repository gate. The local Compose project starts PostgreSQL, API, and web services without a runner or hosted provider.

Exact proof:

```bash
make bootstrap
uv run oak --version
make check
docker compose up -d postgres api web
curl --fail http://127.0.0.1:8080/version
docker compose down
```

## Context and invariants

The implementation repository initially contained only `.gitattributes`. Source specifications, schemas, and public fixtures are read from `/Users/nm/Projects/archicompiler`; implementation changes are made only in this repository.

The typed canonical contracts remain authoritative. CLI and API call the same application service. The API defaults to loopback. No current path ingests customer content, calls a model, signs or approves a plan, starts a runner, resolves a secret, invokes a subprocess from untrusted input, or mutates a target. Relevant requirements are `OAK-FR-CTL-001`–`003`, `OAK-FR-CTL-006`, `OAK-FR-CTL-008`, `OAK-NFR-SEC-003`, `OAK-NFR-REL-002`, and `OAK-NFR-PORT-001`.

## Scope

### In

- Pinned Python and TypeScript workspaces with lockfiles and build metadata.
- Domain/compiler/application/ports/adapters/interfaces/runner package boundaries and executable checks.
- Complete canonical schema registry and public example round-trip tests.
- Shared-service CLI and HTTP health/readiness/version behavior with safe errors.
- Generated OpenAPI artifact and strict web status shell.
- Loopback-published PostgreSQL/API/web Compose services.
- Stable Make targets, CI, hygiene, secret-pattern, dependency audit, and development SBOM hooks.
- Community-only committed documentation and comprehensive ignore policy including agent state.

### Out

- Design-case mutation, brief interpretation, candidate generation/evaluation, plan compilation, persistence migrations, jobs/outbox, authentication, signing, approvals, runner dispatch, and target operations.

## Contract and data changes

Adds CLI commands `oak --version` and `oak serve`; console entrypoint `oak-api`; HTTP `GET /healthz`, `GET /readyz`, and `GET /version`; stable problem responses; and generated OpenAPI 3.1. No canonical schema meaning changes, persistence, or migration.

## Milestones

### Milestone 1 — Reproducible package and repository contract

- Work: add manifests, locks, licence metadata, canonical schemas/examples, package skeleton, Make entrypoints, ignore rules, and this plan.
- Proof: `make bootstrap`, package build, ignore assertions, and schema registry load.
- Rollback: remove added manifests/source/artifacts; no external state exists.

### Milestone 2 — Shared service through CLI and API

- Work: implement the immutable version result and system-information application service; map CLI/API transports; generate OpenAPI; test safe bind and safe error behavior.
- Proof: CLI, application, and API tests plus local curl.
- Rollback: remove interface entrypoints; no persisted state changes.

### Milestone 3 — Web, Compose, and CI harness

- Work: add strict web client, container builds, local services, CI, audits, SBOM target, and end-to-end tests.
- Proof: `make check`, `make build`, Compose health/curl/teardown when the local Docker daemon is available.
- Rollback: stop Compose and remove the additive harness files; database volume contains only empty local development state.

## Verification

- Schema/meta: load all schemas, validate every mapped public example, reject an invalid example, and round-trip parsed values.
- Unit: package/version application query and host safety decisions.
- Contract: AST module rules, deliberate violation fixture, generated OpenAPI diff, documentation policy, agent ignore rules.
- Integration: ASGI health/readiness/version and structured 404/validation errors.
- End-to-end: installed CLI version/help and spawned loopback HTTP process.
- Supply chain: locked sync/build, dependency vulnerability audit, development SBOM, and licence record.

## Security, privacy and authority review

All endpoints are read-only process metadata. Responses contain version, supported schema identifiers, and coarse readiness only. Errors omit stack traces and dependency details. Non-loopback binding is fail-closed without explicit acknowledgement. No secrets, personal data, customer documents, model content, shell fields, target credentials, approvals, or mutation authority exist.

## Operational and rollback plan

This is additive and has no migration. `docker compose down` removes processes; named database state remains unless the operator explicitly requests volume deletion. The API has bounded startup/shutdown and no retrying external call. A source revert fully rolls back the harness.

## Progress

- [x] 2026-08-14 Read active sprint, architecture, requirements, accepted stack/interface/runner ADRs, interface contract, security invariants, testing strategy, and matching recipes.
- [x] 2026-08-14 Inspected the implementation worktree and confirmed only `.gitattributes` plus an ignored OS file existed.
- [x] 2026-08-14 Selected Python 3.13.12 and Node.js 24.18.0 as supported maintained toolchains.
- [x] 2026-08-14 Implemented and locked the Python/package skeleton; clean `make bootstrap` and offline `uv build --no-build-isolation` passed.
- [x] 2026-08-14 Added all canonical schemas/public examples, lossless YAML/JSON/runtime conformance, and executable boundary checks including a deliberate violation.
- [x] 2026-08-14 Implemented shared CLI/API behavior, generated OpenAPI 3.1, safe problems, loopback denial, and real-process tests.
- [x] 2026-08-14 Implemented strict web, Compose, CI, audit, SBOM, and hygiene behavior; exact Node 24 container build passed.
- [x] 2026-08-14 `make check` passed with 36 tests; Python and web audits were clean; Compose health/curl/teardown proof passed.

## Decisions

- 2026-08-14 Cover all nine Sprint 0 tasks in one plan because lockfiles, package boundaries, generated API/web contracts, local services, and CI share one exit demonstration.
- 2026-08-14 Use handwritten runtime wrappers with schema-registry validation; canonical JSON Schemas remain authoritative.
- 2026-08-14 Keep serving metadata-only and read-only; later commands must not be stubbed as successful OAK functionality.
- 2026-08-14 Keep PostgreSQL unexposed and publish API/web on loopback; use a standard project bridge because Docker Desktop did not realize host bindings on an internal bridge.
- 2026-08-14 Treat exact `uv`, Python, and Node pins as CI/container builder inputs. Local `uv` compatibility is a contributor-bootstrap concern, and neither path supplies a future compilation target profile.

## Discoveries and follow-ups

- The repository's initial untracked `.DS_Store` is now ignored; no user source change was overwritten.
- Initial bootstrap probing found that the available `uv` catalogue did not expose a newer Python patch. That was a local tool observation, not the reason for the supported Python version and not a product dependency; Python 3.13.12 remains an explicit, independently reviewable repository pin.
- pnpm blocked dependency build hooks by default; the workspace now explicitly permits only the lockfile-pinned `esbuild` hook required by Vite.
- pnpm runtime auto-provisioning was rejected after an Alpine build attempted to use an unofficial Node archive host. Exact local, CI, and container pins remain, without a hidden runtime download path.
- Docker Desktop did not realize host loopback port bindings on an `internal` bridge. The harness retains loopback-only API/web publication and no PostgreSQL host port, but uses a standard project bridge so the documented curl proof is reachable.
- Isolated `uv build` queried the package index after bootstrap; Hatchling is now a locked development dependency and the stable build target disables isolation so bootstrapped builds work offline.
- Successful local image resolution supplied immutable digests for Python, Node, nginx, uv, and PostgreSQL; Dockerfiles and Compose now pin both readable tags and those digests.
- Container verification passed against the reachable local Docker daemon; teardown preserved only the named development volume and left no project container running.
