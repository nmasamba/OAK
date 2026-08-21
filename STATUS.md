<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build status

- **Updated:** 2026-08-22
- **Repository version:** `0.7.0`
- **Phase:** Sprint 8 complete — Community release hardening; `0.7.0` is a candidate awaiting named approval
- **Completed plans:** `docs/exec-plans/completed/OAK-S0-001-009-walking-skeleton.md`, `docs/exec-plans/completed/OAK-S1-001-010-local-design-case.md`, `docs/exec-plans/completed/OAK-S2-001-011-candidate-planning.md`, `docs/exec-plans/completed/OAK-S3-001-009-persistent-rest-jobs.md`, `docs/exec-plans/completed/OAK-S4-001-009-web-workspace.md`, `docs/exec-plans/completed/OAK-S5-001-011-signed-runner.md`, `docs/exec-plans/completed/OAK-S6-001-008-policy-adapter-sdk.md`, `docs/exec-plans/completed/OAK-S7-001-008-mcp-portal-interface-parity.md`, and `docs/exec-plans/completed/OAK-S8-001-009-community-release-hardening.md`
- **Active plan:** none — Sprint 8 closed
- **Next task:** named maintainer, security and licence approval of the `0.7.0` release
  candidate, recorded in `docs/release/0.7.0/release-decision.md`. `OAK-S8-009` is not
  agent-completable and was not self-approved

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
| `OAK-S3-008` | complete | Generated OpenAPI/client and breaking-change gate, enforced in CI through `make check` without a dedicated `.github` step |
| `OAK-S3-009` | complete | Local actor/tenant binding, unsafe-bind guard, body limits, safe errors/readiness, and cross-tenant denials |
| `OAK-S4-001` | complete | Routed workspace shell with case list/create/open over new additive list/audit endpoints, server-driven actions, durable operation polling, audit timeline, and stale-version conflict recovery |
| `OAK-S4-002` | complete | Brief review with fact/inference/default/correction/unknown provenance classes, materiality, confidence, and confirmation lineage |
| `OAK-S4-003` | complete | Ranked-question confirmation with confirm/correct/reject/accept-risk decisions, value prefill, subset answering, and conflict recovery |
| `OAK-S4-004` | complete | Candidate comparison with variants, visible rejection reasons, Pareto status, objective ranges, constraints, topology, and raw documents |
| `OAK-S4-005` | complete | Selection rationale, alternative rejections, evaluation metrics against contract thresholds, and the assurance plan with owners and gate blockers |
| `OAK-S4-006` | complete | Bundle review with plan/approval/apply separation, digest-verified component lock, artifact viewers, and semantic manifest diff |
| `OAK-S4-007` | complete | Audit lineage timeline and downloadable bounded canonical export |
| `OAK-S4-008` | complete | Keyboard focus management, semantic landmarks and labels, contrast, motionless UI, and automated axe checks on every core screen |
| `OAK-S4-009` | complete | Compose-only Playwright journey with denied transition and cooperatively cancelled interrupted operation |
| `OAK-S5-001` | complete | Versioned outbound-only runner protocol with identities, correlation IDs, nonces, and expiry |
| `OAK-S5-002` | complete | Fail-closed pre-target verifier over protocol, digests, signatures, trust anchors, target, lease, approvals, adapters, and parameters |
| `OAK-S5-003` | complete | Hash-chained append-only journal with before/after checkpoints, crash resume, cancellation, and manual-recovery states |
| `OAK-S5-004` | complete | Local Ed25519 signing with per-role keys, explicit development trust marker, and separated signer/verifier code paths |
| `OAK-S5-005` | complete | Bounded inventory adapter returning sanitized host capabilities with no file scraping or secret access |
| `OAK-S5-006` | complete | Local container adapter with allowlisted argv, isolated never-started fixture container, and reversible apply |
| `OAK-S5-007` | complete | Signed lease dispatch through the outbound-only mailbox where delivery never implies success |
| `OAK-S5-008` | complete | Digest/target/action/expiry-bound signed approvals with revocation and adversarial denial coverage |
| `OAK-S5-009` | complete | Typed rollback and destroy operations with verification and `manual_recovery_required` on unsafe failure |
| `OAK-S5-010` | complete | Deterministic branch-ready GitOps files and patch description that promote nothing automatically |
| `OAK-S5-011` | complete | Adversarial suite covering tamper, forgery, staleness, replay, revocation, wrong target, and injection |
| `OAK-S6-001` | complete | Versioned SDK contracts for the five extension classes with capability discovery |
| `OAK-S6-002` | complete | Schema-valid extension templates, fixtures, and a developer guide |
| `OAK-S6-003` | complete | Reusable contract test kit: determinism, compatibility, error mapping, licence/evidence, parameter validation, argv safety, rollback, offline |
| `OAK-S6-004` | complete | Effective-dated, scoped, signed policy-pack lifecycle with quarantine, activation, and stale refusal |
| `OAK-S6-005` | complete | Optional OPA evaluator behind the policy port that must agree with the built-in reference engine or fail closed |
| `OAK-S6-006` | complete | Second deterministic deployment renderer (Helm/Kubernetes-shaped) behind the renderer port |
| `OAK-S6-007` | complete | Policy and deployment adapter replacement in the reference case with unchanged canonical lineage |
| `OAK-S6-008` | complete | Extension supply chain: manifest digest, compatibility, signature hooks, quarantine, explicit activation, no dynamic code |
| `OAK-S7-001` | complete | Bounded typed stdio MCP server (ten interface-contract tools plus a read-only operation-progress query) with closed schemas and no generic shell/file/secret/approval/dispatch tool |
| `OAK-S7-002` | complete | Remote CLI `--server` mode mapping the design journey to REST with stable output, exit codes, digest-verified writes, and fail-closed refusal of local-only commands |
| `OAK-S7-003` | complete | Public compatibility policy for schemas, REST/OpenAPI, CLI, MCP, and the runner protocol before `0.1.0` |
| `OAK-S7-004` | complete | One fixture across file CLI, remote CLI, REST, and MCP with matching candidate/bundle/semantic digests, denial codes, and audit outcomes |
| `OAK-S7-005` | complete | Backstage catalogue/template/proxy examples over documented REST behavior, pinned to the committed OpenAPI paths, with no core-IR type leak |
| `OAK-S7-006` | complete | Signed `webhook-envelope` contract with a pinned-key example and a headless `oak validate export/bundle/webhook` checker suitable for CI and portals |
| `OAK-S7-007` | complete | MCP abuse suite: injection inertness, oversized/unbounded/deep frames, confused deputy, stale version, tenant crossover, tool/method escalation, execution fields |
| `OAK-S7-008` | complete | `docs/interfaces.md` interface setup, permission model, capability matrix, and explicit unavailable operations |
| `OAK-S8-001` | complete | Clean install matrix across supported platforms and install paths |
| `OAK-S8-002` | complete | Rehearsed upgrade, backup/restore, export/import and stated downgrade limits |
| `OAK-S8-003` | complete | Threat-model coverage index, scans, secret/log and runner review, residual-risk register |
| `OAK-S8-004` | complete | Reproducible artifacts with SBOM, licence inventory, checksums and tested verification |
| `OAK-S8-005` | complete | Provenance-stamped performance and soak measurements |
| `OAK-S8-006` | complete | Operator documentation from install through uninstall |
| `OAK-S8-007` | complete | Contributor documentation and the release process |
| `OAK-S8-008` | complete | Clean-room release-candidate rehearsal with archived evidence |
| `OAK-S8-009` | blocked | Evidence, P0 proposal and known limitations prepared; named maintainer, security and licence approval outstanding |

## Verification evidence

- `make bootstrap` completed from the committed lockfiles.
- Sprint 0 `make check` passed: 30 unit/contract, 4 integration, and 4 end-to-end tests plus formatting, lint, boundary, hygiene, toolchain-consistency, type, generated-contract, and web-build gates.
- The bootstrapped environment produced the Python source/wheel artifacts offline, and `make build` produced the production web bundle.
- Sprint 0 Python and web dependency audits reported no known vulnerabilities; `make sbom` produced an ignored development CycloneDX artifact.
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
- Sprint 2 Python and web dependency audits reported no known vulnerabilities; `make sbom` regenerated the ignored reproducible CycloneDX development artifact.
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
- Sprint 5 delivered the signed typed runner and GitOps boundary. The compiled draft plan is
  signed into an immutable envelope binding, approvals bind action/digest/target/expiry with
  revocation, and dispatch requires both under the compiled verification policy. `oak-runner`
  independently verifies every security invariant before target access, journals each side
  effect in a hash chain, and returns bounded redacted evidence with a signed completion.
- A multi-agent adversarial audit of the completed sprint produced 35 candidate findings,
  independently refuted or confirmed; ten survived. Six were fixed, including a critical
  signature-forgery bypass (verification used the key embedded in the document rather than a
  pinned anchor key), a critical approved-image-digest bypass, and a high-severity gap where
  a duplicate operation kind could execute without verification. The remaining four are
  recorded as known limitations in the completed ExecPlan.
- Sprint 5 verification: 22 new unit tests (signing lifecycle, journal integrity, adapter argv
  injection resistance), a 12-case adversarial integration suite proving tampered plans, wrong
  target fingerprints, expired leases, replayed nonces, untrusted signers, revoked approvals,
  and forbidden execution fields are all denied before any adapter call, contract tests for
  canonical-bytes agreement and the repository-wide execution-field ban, GitOps determinism
  tests, and a three-case exit demonstration through the installed entrypoints including a
  real Docker apply/verify/rollback cycle that left no fixture container behind.
- Sprint 4 completed the architecture web workspace: brief/inference review with provenance
  classes, ranked-question confirmation, candidate comparison with objective ranges and
  visible infeasibility, decision/assurance display, bundle review with plan/approval/apply
  separation and semantic diff, audit timeline, and canonical export download. The
  Playwright suite (`make web-e2e`) passed against the pinned Compose stack: the full
  brief-to-bundle reference journey with zero axe violations on all eight core screens, a
  denied stale-version transition with visible recovery, and an interrupted operation
  cancelled cooperatively across a worker stop/start. `make check` passed on the final
  tree; accessibility scanning surfaced and fixed a heading-order defect and a
  keyboard-unreachable scroll region.
- Sprint 4 Milestone 1 added additive tenant-scoped `GET /v1/design-cases` and
  `GET /v1/design-cases/{case_id}/audit` resources (regenerated OpenAPI/client passed the
  local compatibility gate without a baseline reset), forwarded `/v1` through the nginx and
  Vite proxies, and replaced the status shell with a routed dependency-free workspace shell.
  Three new integration tests covering ordering, cursors, tenant non-enumeration, audit
  parity on file and PostgreSQL adapters passed against the pinned 17.6 image, strict mypy
  covered 77 files, `make check` passed, and a Compose browser journey proved case
  creation, interpretation, in-browser candidate generation through a durable operation,
  the audit timeline, and stale-version conflict recovery through the web origin.
- Sprint 6 delivered the policy and adapter SDK. Versioned interfaces cover the five
  extension classes with deterministic capability discovery; a policy port evaluates
  effective-dated, scoped, signed, self-tested packs into engine-neutral canonical
  decisions; a second Helm/Kubernetes renderer proves the same plan contract behind a
  renderer port without making Kubernetes required; and extensions are quarantined until
  digest, compatibility, licence, pinned-anchor steward signature, and embedded tests pass
  and an explicit local actor activates them.
- Byte-stability was verified directly rather than inferred: the reference case compiled on
  `main` and on the Sprint 6 branch produced identical deployment-bundle, runner-plan,
  semantic-manifest, and selected-candidate digests, with `candidate-03` stable at case
  `0.1.7`.
- Sprint 6 verification: 304 unit/contract tests, the policy, extension, rendering,
  equivalence and replacement integration suites, and the end-to-end extension exit
  demonstration through installed entrypoints. The OPA legs run only where the optional
  binary exists; the built-in engine is authoritative and offline.
- Two audits ran against the completed sprint: a direct adversarial probe and a five-lens
  multi-agent audit with independent per-finding refutation. Twenty candidates deduplicated
  to fourteen distinct issues, every one reproduced locally before acceptance. Twelve were
  fixed, including a critical case where the optional OPA engine published canonical
  decisions the built-in reference engine refuses — a matched `deny` was suppressed into an
  `allow` — because OPA 1.19.1 compares some decimal literals by trimmed text. The external
  engine is no longer treated as an independent oracle. The remainder are recorded as known
  limitations in the completed ExecPlan.
- 2026-08-20 dependency maintenance: `pip-audit` reported four `cryptography` 46.0.7
  advisories — `GHSA-537c-gmf6-5ccf`, `PYSEC-2026-3552`, `PYSEC-2026-3553`, and
  `PYSEC-2026-3554` — and no other locked Python or web package carried any advisory. None
  of the four is reachable from OAK, which uses raw-bytes Ed25519 only and loads no X.509
  chain, PKCS#7 structure, or serialized key; the pin moved to `cryptography>=50,<51` and
  the lock to 50.0.0 anyway, because reachability is a property of today's call graph rather
  than a durable control. A fixed-seed Ed25519 signature is byte-identical before and after,
  so existing signed artifacts and trust anchors remain valid. `make check`, `make build`,
  and `make audit` pass on the upgraded lock with no advisory suppressed; the recorded
  review is in `docs/dependencies.md`.
- 2026-08-20 the API container image was repaired. Sprint 6 force-included `policy-packs`
  into the wheel without adding it to the image build context, so `uv sync --frozen` failed
  inside the container and the image, and therefore the Compose stack, had been unbuildable
  since that sprint merged. Neither `make build` nor CI could detect it, because the former
  runs at the repository root and the latter builds no image. A `linux/amd64` image build
  now succeeds, resolves a `manylinux_2_34_x86_64` wheel for `cryptography` 50.0.0 with no
  Rust toolchain present, and runs `oak --version`; a contract test binds the force-include
  list to the Dockerfile so the two cannot drift again.
- 2026-08-20 `OAK-S3-008` closed by owner decision. Sprint 3 deferred the CI-enforcement
  clause because no `.github` change was authorized, and recorded the task as partial. The
  gate is nonetheless enforced: `openapi-compatibility` is a prerequisite of `make check`,
  which `.github/workflows/ci.yml` runs on every push and pull request, and that workflow
  now passes. The deferred item was the dedicated workflow step, which remains unadded and
  unnecessary.
- Sprint 7 delivered MCP, portal, and interface parity. A bounded stdio MCP server exposes
  the ten interface-contract tools plus a read-only operation-progress query with closed
  schemas that mirror the REST bounds; it has no approval, signing, dispatch, secret,
  policy-override, file, or command tool, and a capability-matrix contract test pins the
  registry. The CLI gained a remote (`--server`) mode over the `/v1` surface with stable
  output and exit codes, digest-checked local writes, and fail-closed refusal of the
  local-only signing/approval/dispatch/keys/extensions/policy commands. A canonical
  `webhook-envelope` schema, a pinned-key signed example, and a server-free
  `oak validate export/bundle/webhook` checker support CI and portals; Backstage starters use
  only documented REST behavior. `docs/compatibility.md` and `docs/interfaces.md` publish the
  compatibility policy and the permission/capability matrix.
- Sprint 7 verification: full `make check` green (verified by counting `make: ***` lines, not
  exit code) — 335 unit/contract, 126 integration with 4 gated skips against the pinned
  PostgreSQL 17.6, and 16 end-to-end tests, plus validate/format/lint/boundary/type/
  generated-OpenAPI-compatibility/web-build gates. The OpenAPI contract and its compatibility
  baseline are unchanged (Sprint 7 added no REST path). Byte-stability was verified directly:
  the reference case compiled on `main` and on the Sprint 7 branch produced identical
  deployment-bundle, runner-plan, semantic-manifest, and selected-candidate digests, with the
  case stable at `0.1.7`. A four-interface conformance suite (file CLI, remote CLI, REST, MCP)
  matched candidate/bundle/semantic digests, denial codes, idempotent retries, and audit
  outcomes.
- Sprint 7 CI is green on the remote: both GitHub Actions `check` jobs pass on PR #11 after an
  end-to-end e2e assertion was rewritten. The original test scraped `oak --help` for
  `--server`; that output is rendered by Rich, whose wrapping and styling differ between a
  developer machine and the CI runner, so the assertion failed there while the option worked
  (the same run passed the `oak validate webhook` end-to-end from the same installed build).
  It now asserts behaviour instead: `mcp` and `validate` are invocable, an unknown validate
  kind returns `OAK-VALIDATE-KIND`, `--server` routes a local-only command to
  `OAK-REMOTE-UNSUPPORTED`, and a remote-capable command fails closed with
  `OAK-REMOTE-UNAVAILABLE` against an unreachable server.
- A six-lens multi-agent adversarial audit ran against the Sprint 7 diff with independent
  per-finding refutation and a repo-wide latent sweep. Eleven candidates were raised; two
  independent skeptics confirmed their findings and the remaining eight candidates were
  verified directly against the code after the skeptics hit a session limit, each reproduced
  before acceptance. The authority invariant held — no MCP tool, remote-CLI path, portal
  example, or webhook could reach a forbidden capability. Six real defects were fixed
  (untrusted-YAML anchor expansion in the webhook validator; wrong-shape server responses
  crashing the remote CLI instead of a stable code; the execution-field ban being enforced
  only for bundles and not exports/webhooks; an MCP handler error mislabeled as unknown-tool
  or crashing the session; a vacuous MCP/REST bounds-parity test; and a remote-`design`
  idempotency-key inconsistency). Four scoped limitations are recorded in the completed
  ExecPlan.

- Sprint 8 delivered Community release hardening for the `0.7.0` candidate. The version
  contradiction was resolved first: `sprints.md` targeted `0.1.0` while the repository was at
  `0.6.0.dev6`, and PEP 440 sorts `0.1.0` *below* that, so the release is `0.7.0`
  (ADR-0002). `VERSION`, `pyproject.toml`, `package.json`, `web/package.json`, `STATUS.md`
  and the generated OpenAPI `info.version` are now bound together by `make toolchain-check`
  with drift tests; `package.json` had silently sat at `0.5.0-dev.5`.
- Byte-stability was verified directly rather than inferred: the reference case compiled
  before any change and after every milestone produced identical deployment-bundle,
  runner-plan, semantic-manifest and selected-candidate digests, stable at case `0.1.7`. The
  repository version is not embedded in any canonical document — `minimum_oak_version` and
  `generator_version` are hardcoded literals — which was checked rather than assumed.
- `make release` builds the sdist and wheel twice and refuses to finish unless the digests
  match, installs the wheel into a clean environment holding only the locked runtime closure,
  and runs it from a working directory outside the checkout to prove the packaged schemas,
  catalogue and policy packs resolve. It emits an SBOM of the *released* closure stamped with
  the artifact digests, a generated licence inventory, and `SHA256SUMS`. `make verify-release`
  is a dependency-free consumer-side verifier whose refusal paths are tested against tampered,
  equal-length-substituted, missing, empty, malformed and path-escaping input.
- The runtime dependency closure shrank from 45 packages to 37 by dropping the unused
  `jsonschema[format]` extra, which had placed `rfc3987` 1.3.8 (GPL-3.0-or-later) in the
  runtime closure of this Apache-2.0 distribution while `docs/dependencies.md` recorded
  jsonschema as "MIT". Nothing constructs a `FormatChecker`, so no behaviour changed. The
  generated inventory now shows LGPL-3.0 Psycopg as the only copyleft entry.
- Security review produced `docs/security/threat-coverage.md` (all nineteen threat ids mapped
  to tests: 8 direct, 9 partial, 2 structural, 0 uncovered, every cited test verified to
  exist), `docs/security/residual-risk.md` (34 stable-id entries), and `SECURITY.md`. **No
  external security review was commissioned**, and a build gate now fails on unqualified
  assurance vocabulary — it caught three of its own author's sentences on first run.
- Four confidentiality defects were found and fixed, each reproduced before the fix:
  canonical and MCP validation diagnostics echoed the value that failed validation (the REST
  layer already dropped it, so the transports disagreed); SQLAlchemy bound statement
  parameters — which carry brief text — reached uvicorn's error log, since `access_log=False`
  does not suppress `uvicorn.error`; and `oak-runner` and `oak-db-migrate` answered
  misconfiguration with tracebacks disclosing absolute paths, profile fragments and the
  database host and user.
- Two stable-code defects were fixed. A malformed `If-Match` returned `OAK-EXPECTED-VERSION`,
  which maps to HTTP 409 and CLI exit 4 — both meaning "re-read and retry" — so an automated
  retry loop on a weak entity tag would spin forever; it is now `OAK-PRECONDITION-INVALID`. An
  artifact lookup miss returned `OAK-WORKSPACE-NOT-FOUND` on surfaces that opaque the message,
  making the code the only signal and pointing an operator at a storage failure that had not
  happened; it is now `OAK-ARTIFACT-NOT-FOUND`.
- The no-egress claim moved from a grep to a gate: the reference journey and an
  export/reimport now run with every outbound socket path patched to raise, a
  guard-the-guard test proves the fixture is not vacuous, and an AST check pins the set of
  modules permitted to import a network client to the remote CLI alone.
- Backup and restore are measured rather than declared. `scripts/verify_deployment.py` walks
  the artifact index and re-verifies every object; `tests/integration/test_backup_restore.py`
  creates a scratch PostgreSQL database, migrates it to head, and proves that a database
  restored without its artifact root is detected — the half-restore the previous
  `pg_dump`-only documentation would have produced.
- Performance was measured with provenance rather than asserted: reference compiler 8.75 s
  median against a 120 s requirement, interactive read p95 31.9 ms against 500 ms, and
  workspace manifest reads growing from 4.0 ms at zero indexed artifacts to 281.2 ms at 43
  with no compaction anywhere (`RR-030`). Four measurements are published as *not measured*
  with the reason.
- Operator and contributor documentation now covers install through uninstall, every `OAK_*`
  variable (pinned to the source by a contract test), every `OAK-*` code (generated; 245 of
  267 were previously undocumented), the supported platform matrix with architecture and
  glibc floors read from the lockfile, and the six architecture ADRs that shipped documents
  cite, mirrored so their citations resolve outside the governance repository.
- `OAK-S8-009` is **not complete**. The evidence pack, the P0 blocker proposal and the
  published known-limitations statement are prepared in
  `docs/release/0.7.0/release-decision.md`; three named humans — maintainer, security and
  licence — must sign before `0.7.0` is a release rather than a candidate. It was not
  self-approved.

## Safety boundary

The current harness accepts bounded local architecture briefs, catalogue files, rationale, and target profiles and treats their content as untrusted data. It has no mandatory or real model-provider call and no secret resolution. Signing, approval, runner dispatch, and target mutation now exist in explicitly local development form: keys are labelled `development`, the runner reaches only an isolated non-production fixture profile that opts in through an explicit acknowledgement, and the sole permitted mutation is creating and removing one network-isolated, never-started container through a fixed allowlisted argument vector. Every mutating operation requires a separately signed, current, digest and target bound approval that the runner verifies independently before any target access. A compiled plan is inert until it is signed, approved, and independently verified by the runner. Governed extensions and policy packs are untrusted input: they are quarantined on install, verified against pinned local trust anchors, and never executed — an extension payload is data, and a deployment-adapter extension only binds configuration to an in-tree renderer identity. Policy evaluation is fail-closed, an undecidable condition can never yield an automated allow, and an optional external policy engine that disagrees with the built-in reference engine is refused rather than published. The bounded MCP server and the CLI's remote mode are additional transports onto the same application services and grant no authority: the MCP surface is design/read only with no approval, signing, dispatch, secret, policy-override, file, or command tool, and remote mode refuses the local-only signing and runner commands rather than acting on local state. Remote mode trusts the control plane it is pointed at; a wrong-shape response is refused with a stable code rather than crashing. Signed webhook envelopes and compiled review bundles are verified against pinned keys and existing digest edges only, and are not themselves execution authority. All committed fixtures are public or synthetic, and the committed webhook publisher key is public material whose private half was discarded.
