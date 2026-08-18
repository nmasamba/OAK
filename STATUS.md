<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build status

- **Updated:** 2026-08-18
- **Repository version:** `0.5.0.dev5`
- **Phase:** Sprint 3 complete — persistent REST control plane and durable jobs verified
- **Completed plans:** `docs/exec-plans/completed/OAK-S0-001-009-walking-skeleton.md`, `docs/exec-plans/completed/OAK-S1-001-010-local-design-case.md`, `docs/exec-plans/completed/OAK-S2-001-011-candidate-planning.md`, and `docs/exec-plans/completed/OAK-S3-001-009-persistent-rest-jobs.md`
- **Active plan:** none — authoring the Sprint 4 architecture web workspace ExecPlan is the next step
- **Next task:** author and claim the Sprint 4 (`OAK-S4-001`–`OAK-S4-009`) ExecPlan;
  CI compatibility wiring remains explicitly deferred by user direction

## Claimed work

| Task | State | Observable outcome |
|---|---|---|
| `OAK-S0-001` | complete | Locked Python workspace, importable package, and checked local/builder toolchain contract |
| `OAK-S0-002` | complete | Stable developer commands |
| `OAK-S0-003` | complete | Enforced module dependency rules |
| `OAK-S0-004` | complete | Schema/runtime conformance harness |
| `OAK-S0-005` | complete | Shared-service CLI version/help behavior |
| `OAK-S0-006` | complete | Loopback-safe health, readiness, and version API |
| `OAK-S0-007` | complete | Strict TypeScript status shell |
| `OAK-S0-008` | complete | Local PostgreSQL/API/web Compose profile |
| `OAK-S0-009` | complete | CI and supply-chain baseline |
| `OAK-S1-001` | complete | Atomic file workspace, immutable content-addressed artifacts, concurrency, retries, and portable import/export |
| `OAK-S1-002` | complete | Full immutable DesignCase artifact index and complete allowed/denied lifecycle matrix |
| `OAK-S1-003` | complete | Bounded YAML/JSON/Markdown/text intake and separate untrusted source records |
| `OAK-S1-004` | complete | Deterministic public-fixture interpretation into a schema-valid intent with complete scalar provenance |
| `OAK-S1-005` | complete | Provider-neutral bounded proposal port and deterministic failure adapter, optional and read-only |
| `OAK-S1-006` | complete | Stable missing, contradictory, declared-unknown, and infeasible-claim findings |
| `OAK-S1-007` | complete | At most five stable materiality-ranked questions with candidate-impact reasons |
| `OAK-S1-008` | complete | Actor-bound confirm/correct/reject/accept-risk successors with value digests and audit lineage |
| `OAK-S1-009` | complete | Offline init/design/questions/confirm/export/import CLI with human, JSON, and YAML output |
| `OAK-S1-010` | complete | Malformed, prompt-injection, Unicode, path, size, provenance, race, corruption, and provider-outage coverage |
| `OAK-S2-001` | complete | Bounded synthetic catalogue snapshot with deterministic eligibility, licence, evidence, and freshness decisions |
| `OAK-S2-002` | complete | Provider-neutral simpler, minimum, balanced, and high-assurance candidate graphs |
| `OAK-S2-003` | complete | Fail-closed hardware, deployment, security, licence, locality, and compatibility constraints |
| `OAK-S2-004` | complete | Transparent cost, latency, quality, operability, and energy ranges with calibration metadata |
| `OAK-S2-005` | complete | Order-independent feasible Pareto frontier and visible sensitivity |
| `OAK-S2-006` | complete | Rule/evidence explanations with requirements, uncertainties, and alternatives but no private reasoning |
| `OAK-S2-007` | complete | Digest-linked deterministic pass/fail/blocked evaluation artifacts with immutable retry behavior |
| `OAK-S2-008` | complete | Owner/rationale/alternative/dependency-bound immutable selection decision |
| `OAK-S2-009` | complete | Selected-candidate tests, evidence, controls, owners, and explicit gate blockers |
| `OAK-S2-010` | complete | Target-profile-bound canonical review bundle and draft typed non-executing runner plan |
| `OAK-S2-011` | complete | Offline candidates/evaluate/select/assure/plan CLI exit journey with stable `candidate-03` |
| `OAK-S3-001` | complete | Empty-database forward baseline and atomic immutable case/head/transition/idempotency/outbox transaction |
| `OAK-S3-002` | complete | Shared file/PostgreSQL restart, concurrency, rollback, tenant, and application digest contract suite |
| `OAK-S3-003` | complete | At-least-once outbox leases, stable IDs/sequences, consumer deduplication, and observable projection lag |
| `OAK-S3-004` | complete | Bounded retry/lease/checkpoint/cancellation Operations and real non-runner `oak-worker` |
| `OAK-S3-005` | complete | Shared-service `/v1` DesignCase and candidate workflow with async compiler/evaluation stages |
| `OAK-S3-006` | complete | Durable status/cancel, safe problems, idempotency, ETag/If-Match, and opaque pagination |
| `OAK-S3-007` | complete | Bounded digest/media artifact reads and tenant-safe file/PostgreSQL/REST export/import |
| `OAK-S3-008` | partial | Generated OpenAPI/client and tested local breaking-change gate complete; `.github` CI wiring explicitly deferred |
| `OAK-S3-009` | complete | Local actor/tenant binding, unsafe-bind guard, body limits, safe errors/readiness, and cross-tenant denials |

## Verification evidence

- `make bootstrap` completed from the committed lockfiles.
- Sprint 0 `make check` passed: 30 unit/contract, 4 integration, and 4 end-to-end tests plus formatting, lint, boundary, hygiene, toolchain-consistency, type, generated-contract, and web-build gates.
- The bootstrapped environment produced the Python source/wheel artifacts offline, and `make build` produced the production web bundle.
- Python and web dependency audits reported no known vulnerabilities; `make sbom` produced an ignored development CycloneDX artifact.
- The Compose exit demonstration made PostgreSQL, API, and web healthy; direct and web-proxied `/version` returned `0.4.0.dev3`; teardown left no project containers running.
- Documentation policy scan found no prohibited product references. Git ignore checks cover agent instructions/state, local secrets, environments, build output, runtime data, editors, and operating-system metadata.
- `make toolchain-check` proves that contributor compatibility, exact CI/container builders, package metadata, and documented versions agree; these implementation toolchains are explicitly independent of future target profiles.
- Sprint 1 `make check` passed: 183 unit/contract, 18 integration, and 6 end-to-end tests plus formatting, lint, boundaries, hygiene, types, generated contracts, and web build.
- `make build` produced the source archive, wheel, and web bundle; an isolated wheel install resolved all 18 bundled canonical schemas outside the source checkout.
- The installed-wheel offline exit journey produced case `0.1.1`, converged an identical confirmation retry without a third event, and imported a byte-identical manifest with two audit events and two idempotency records.
- Sprint 1 Python and web dependency audits reported no known vulnerabilities, and the ignored development SBOM was regenerated.
- Sprint 2 `make check` passed: 205 unit/contract, 21 integration, and 7 end-to-end tests plus formatting, lint, boundaries, hygiene, toolchain consistency, types, generated contracts, and web build.
- `make build` produced `0.4.0.dev4` source and wheel artifacts plus the web bundle. A clean offline wheel environment resolved 25 bundled schemas, three component manifests, and four patterns, then completed the full case-to-plan/export journey at case `0.1.6` with seven audit events.
- Two clean CLI workspaces produced byte-identical normalized semantic manifests. The selected target profile affected the digest and passed tenant, capacity, platform, network, and read-only capability checks; incompatible and undersized profiles were denied without state change.
- The generated runner plan remained `draft`, unsigned, unapproved, and limited to five typed read-only operations; schema/runtime scans found no command, shell, executable, or argument-vector field and no target action occurred.
- Current Python and web dependency audits reported no known vulnerabilities; `make sbom` regenerated the ignored reproducible CycloneDX development artifact.
- Documentation policy scans found no prohibited product references, the Git diff contains no CI/CD changes, and Git ignore checks continue to hide agent instructions, state, transcripts, and caches.
- Sprint 3 static verification passed repository validation, Python formatting/lint, modular
  boundaries, repository hygiene, strict mypy across 75 source files, generated OpenAPI/client
  reproduction, the local compatibility gate, and `docker compose config` validation.
- Sprint 3 unit/contract verification passed 210 tests. Database-free integration passed 26
  tests with 18 PostgreSQL cases skipped by contract. Focused PostgreSQL repository/outbox/job
  verification passed 16 tests (3 file-only parameter cases skipped), the bounded export/
  restore proof passed, and the full REST/worker/digest-parity journey passed both tests.
- The persistent REST journey created, interpreted, confirmed, generated/evaluated via durable
  Operations, selected, assured, compiled, streamed artifacts, exported/imported, rejected a
  tamper, and matched the file journey's semantic case projection,
  `candidate-03`, deployment-bundle, and semantic-manifest digests at case `0.1.7`.
- Operation idempotency checks prove that concurrent inserts converge and that completed retries
  return the original durable Operation before re-evaluating an obsolete case precondition;
  correlation, time, interface origin, and later observed version remain audit metadata rather
  than changing the semantic request identity.
- 2026-08-18 verification cleared the previously blocked items: `pnpm install --frozen-lockfile`
  restored the locked web workspace; web format/type/build gates passed; Python and web
  dependency audits reported no known vulnerabilities; `make sbom` regenerated the ignored
  development SBOM; and all seven end-to-end tests passed, including the previously
  sandbox-blocked process-level loopback API test.
- The full `make check` aggregate gate passed. The complete integration suite ran against the
  pinned Compose `postgres:17.6-alpine` image (40 passed, 4 file-only parameter skips),
  including the REST/worker digest-parity journey and the PostgreSQL repository/outbox/
  operation contracts.
- The pinned PostgreSQL 17.6 Compose exit journey built all images, applied
  `0001_sprint3_baseline` to the pinned empty database, served `/version` (`0.5.0.dev5`)
  directly and web-proxied, and completed the full `/v1` reference workflow to
  `bundle_compiled` at case `0.1.7` with API/worker restarts between stages and a durable
  compile Operation surviving a mid-flight worker restart. Teardown left no project
  containers; named volumes persist.
- A Sprint 0-era `oak-postgres-data` volume had been initialised under a different password;
  the empty database was recovered with `ALTER ROLE oak WITH PASSWORD` over the container's
  local trust socket rather than volume deletion, consistent with restore-forward recovery.

## Safety boundary

The current harness accepts bounded local architecture briefs, catalogue files, rationale, and target profiles and treats their content as untrusted data. It has no mandatory or real model-provider call, approval, signing, runner dispatch, secret resolution, target subprocess, target connection, or mutation behavior. The compiled plan is a draft review artifact whose target identity and declared capabilities are validated but never contacted. All committed fixtures are public or synthetic.
