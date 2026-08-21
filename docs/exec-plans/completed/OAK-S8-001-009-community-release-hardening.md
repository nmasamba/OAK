<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S8-001–009: Community release hardening

## Status

- Owner/agent: Claude
- Started: 2026-08-21
- Last updated: 2026-08-21
- State: done (except `OAK-S8-009`, which requires named human approval)
- Claimed tasks: `OAK-S8-001`–`OAK-S8-009`

## Outcome

A stranger with an empty machine can install OAK Community from the released documentation,
run the reference brief-to-plan workflow through the CLI and the web workspace, perform an
outbound-only signed local dry run, verify every released artifact against published digests,
and remove OAK completely — with a written record of what was measured, what was reviewed, and
what is explicitly not assured. Nothing in the release claims production or customer
readiness, and no document implies an external security review that did not happen.

## Context and invariants

Sprint 7 is merged; `main` is at `9998508` (PR #11) with CI green on the remote. Sprints 0–7
delivered the offline CLI journey, the persistent PostgreSQL control plane with a 21-path
`/v1` REST surface, the web workspace, the signed typed runner, the policy/adapter SDK with
governed extensions, and the MCP/remote-CLI/portal interface parity layer. Sprint 8 is the
last sprint before the first release and is deliberately an **evidence, reproducibility and
documentation** sprint: the deliverable is proof that what already exists installs, upgrades,
restores, scans, performs acceptably and is documented well enough to use and remove. New
product surface is out of scope.

Governing requirements: `OAK-NFR-PORT-001`–`002`, `OAK-NFR-SEC-001`–`006`, `OAK-NFR-REL-001`–
`003`, `OAK-NFR-PERF-001`–`002`, `OAK-FR-OPS-001`–`004`. Governing ADRs: 0011 (open component
policy) and 0012 (control-plane distributions) above all, plus 0013 (implementation stack) and
0015 (typed runner operations). Threat-model lenses: TM-02, TM-08, TM-15 (supply chain), TM-07
(runner), TM-10 (tenant/log leakage), TM-19 (no hidden runtime dependency). Recipes applied:
Dependency and release (primary), Security review, Documentation and ADR, and Persistence and
migration for `OAK-S8-002`.

Hard invariants:

- **No production or customer readiness claim.** The release is a local-first developer
  release. Release approval is not a Gate 2/3 deployment approval and no release note, README,
  operator document or performance number may blur that.
- **No authority bypass may be introduced by packaging.** MCP stays design/read only; remote
  CLI keeps refusing local-only commands; runner apply stays behind signing, approval and
  independent runner verification. A release script, workflow or install path must not create
  a privileged shortcut.
- No `command`, `shell`, `executable`, or `argv` field may appear in any canonical document.
- `oak.runner` imports only `oak.contracts`, `oak.domain`, and itself; `oak.contracts` and
  `oak.domain` are leaf packages; `oak.interfaces` may not import `adapters`.
  `tools/check_boundaries.py` enforces this.
- Compiled canonical artifacts are immutable and byte-stable. The reference case digests on
  this branch must equal those on `main`, verified **directly** by compiling both, not
  inferred from the test suite. Current values at case `0.1.7`:
  `deployment_bundle sha256:042313be…`, `runner_plan sha256:5e0a65ba…`,
  `selected_candidate sha256:576b0ca6…`, `semantic_manifest sha256:2ef34758…`.
- Fail closed everywhere: unknown kinds, adapters, schemas and artifacts are refused, never
  skipped. Verification uses pinned keys and published digests, never a value carried inside
  the artifact being checked.
- Public surfaces are governed by `docs/compatibility.md`; the MCP prohibition list is
  permanent and not subject to the additive-change rule.
- No mandatory network or hosted dependency. `make check` keeps working with egress disabled
  after bootstrap, and artifact verification must have an offline path.

## Scope

### In

- **Release identity (prerequisite).** Resolve the version contradiction (`VERSION` and
  `pyproject.toml` at `0.6.0.dev6` versus a `0.1.0` target that sorts *lower*), record it as an
  ADR, and make `VERSION`, `pyproject.toml`, `package.json`, `web/package.json`, `STATUS.md`,
  `docs/compatibility.md` and the contract tests agree.
- **Clean install matrix (`OAK-S8-001`).** An authoritative supported-platform matrix (OS ×
  architecture × install path), verified prerequisites including the undocumented ones, a
  clean-environment install of the built wheel that exercises the packaged-data path, a
  `linux/amd64` image build, and a written feasibility decision on a lightweight Kubernetes
  profile.
- **Upgrade, backup, restore (`OAK-S8-002`).** A named baseline release candidate, a rehearsed
  file-workspace and PostgreSQL upgrade, a backup/restore procedure covering **both** the
  database and the content-addressed artifact root, a restore verification step, canonical
  export/import round-trip evidence, and the downgrade/rollback limits stated and tested.
- **Security review (`OAK-S8-003`).** A threat-model coverage index mapping every TM id to the
  tests that exercise it (and naming those that nothing covers), dependency and container
  scan evidence, a secret and log review, a runner sandbox review, a residual-risk register
  with stable ids for every carried-forward and newly found limitation, and `SECURITY.md`.
  **No external review is commissioned; nothing may imply one occurred.**
- **Supply-chain release (`OAK-S8-004`).** A declared and verified reproducible build, a
  release SBOM describing the shipped artifact rather than the developer virtualenv, a
  licence/NOTICE inventory generated from the runtime closure, a `SHA256SUMS` manifest, image
  build and digest recording, published verification instructions that are **tested against a
  tampered artifact**, and a tag-triggered release workflow.
- **Performance and soak (`OAK-S8-005`).** A benchmark harness with machine-readable
  hardware/workload provenance covering the reference compiler, API reads, job restart, outbox
  lag and a bounded runner operation, published with explicit scope limits.
- **Operator documentation (`OAK-S8-006`).** Install, configure (complete `OAK_*` reference),
  observe, back up, restore, upgrade, troubleshoot, export, uninstall, and secure local
  binding and keys — plus an error-code reference for the stable `OAK-*` contract.
- **Contributor documentation (`OAK-S8-007`).** Architecture tour, first change, extension SDK
  pointer, test topology including the silent PostgreSQL gate, review policy, governance, and
  the release process.
- **Release-candidate rehearsal (`OAK-S8-008`).** The complete clean-room procedure with
  network disabled after dependency and image acquisition, with archived evidence.
- **Release decision preparation (`OAK-S8-009`).** The P0 blocker list, the published
  known-limitations statement, and the evidence pack — then **stop and ask the owner**.

### Out

- Any new product capability, canonical schema, artifact kind, REST path, CLI command that
  changes an existing contract, or MCP tool.
- Publishing to PyPI, a container registry, or any external index. This sprint produces
  verifiable artifacts and a documented procedure; the decision to publish is the owner's.
- Real authentication, multi-tenant controls, or any Enterprise/Cloud capability.
- Self-approving the release. `OAK-S8-009` requires accountable humans.
- Commissioning or simulating an external security review.
- Fixing carried-forward known limitations that Sprint 8 does not naturally touch; those
  become residual-risk register entries or P0 blockers instead.

## Contract and data changes

- **Repository version moves to `0.7.0`** (owner decision, recorded as an ADR). No canonical
  document embeds the repository version: `minimum_oak_version` and `generator_version` in the
  compiler are hardcoded literals, so the bump cannot shift any canonical digest. Verified
  directly rather than assumed.
- **`docs/compatibility.md` changes its threshold** from `0.1.0` to `0.7.0` wherever it names
  the release at which the deprecation window begins. The rules themselves do not change.
- **Runtime dependency closure shrinks.** The unused `jsonschema[format]` extra is dropped;
  nothing in `src/` constructs a `FormatChecker`, so the extra contributes no behaviour while
  adding eight runtime packages including `rfc3987` (GPL-3.0-or-later) to an Apache-2.0
  distribution. `docs/dependencies.md` gains the review entry.
- **No change** to canonical schemas, artifact kinds, digest computation, REST models, the
  OpenAPI baseline, the MCP tool registry, or the runner protocol.

## Milestones

Rollback for every milestone is reverting the branch. No milestone changes an existing
canonical artifact, state transition, or public contract shape.

1. **Release identity and packaging hygiene** — version `0.7.0` across every file that states
   it, ADR recording the decision and the rejected alternatives, web/Python version agreement
   with a contract test, `jsonschema[format]` dropped with `uv lock` and a dependency review
   entry, stray `-.uv-cache/` removed with the `.gitignore`/`.dockerignore` blind spot closed,
   and explicit sdist include/exclude rather than inherited ignore rules.
   Proof: `make check` green; byte-stability verified directly against `main`; two consecutive
   builds produce identical digests; the built sdist contains no cache directory.
2. **Clean install matrix (`OAK-S8-001`)** — supported-platform matrix document, prerequisite
   fixes (`sys.executable` instead of a bare `python`; `git` documented), a runtime toolchain
   check, a clean-environment wheel install exercising the packaged-data path, a `linux/amd64`
   image build, and the Kubernetes feasibility decision written down.
   Proof: the wheel installs into a throwaway environment and resolves bundled schemas outside
   the source checkout; the amd64 image builds and runs `oak --version`; the platform matrix
   states an architecture and glibc floor derived from the actual wheel availability.
3. **Upgrade, backup and restore (`OAK-S8-002`)** — baseline RC named and its digests
   archived, file-workspace and PostgreSQL upgrade rehearsed, paired database + artifact-root
   backup/restore procedure with a verification step, export/import round trip, and
   downgrade/rollback limits tested rather than asserted.
   Proof: a restored deployment passes an integrity check that recomputes digests; the Alembic
   `downgrade()` refusal is pinned by a test; a workspace written by the baseline build is read
   and exported by the release build.
4. **Supply-chain release (`OAK-S8-004`)** — release build script and `make release`, release
   SBOM with the artifact as subject, generated licence inventory and `NOTICE`, `SHA256SUMS`,
   image build with recorded digests, `.github/workflows/release.yml` (tag/dispatch triggered;
   the `check` job is untouched), and verification instructions.
   Proof: verification instructions run verbatim and **fail closed on a tampered artifact**,
   proven by a test; a rebuild reproduces the published digests; the SBOM names the artifact
   and its runtime closure, not the developer virtualenv.
5. **Security review and residual risk (`OAK-S8-003`)** — TM-to-test coverage index, dependency
   and container scan evidence, secret/log review, runner sandbox review, residual-risk
   register with stable ids and severities, `SECURITY.md`, an egress-absence test, and a
   documentation honesty gate.
   Proof: every TM id resolves to covering tests or an explicit recorded gap; the honesty gate
   fails on a seeded overclaim; the offline journey is proven to open no outbound socket.
6. **Performance and soak (`OAK-S8-005`)** — benchmark harness emitting provenance-stamped
   JSON, and a published results document.
   Proof: the harness reruns and reports the same shape; every number carries hardware,
   toolchain, commit, catalogue size and workload parameters; the document states its scope
   limits explicitly.
7. **Operator documentation (`OAK-S8-006`)** — operations runbook, complete `OAK_*`
   configuration reference, error-code reference, uninstall procedure and a clean-machine
   verification script.
   Proof: the `OAK_*` table is checked against the source by a test; the uninstall procedure
   is executed and the verification script reports a clean machine.
8. **Contributor documentation and release process (`OAK-S8-007`)** — `CONTRIBUTING.md`,
   architecture tour, test topology including the PostgreSQL gate, review and governance
   policy, `docs/release-process.md`, and resolution of ADR citations that currently point
   outside the repository.
   Proof: every ADR referenced by a shipped document resolves inside the repository; a
   contributor path from clone to first change is executable as written.
9. **Rehearsal and release decision preparation (`OAK-S8-008`, `OAK-S8-009`)** — clean-room
   rehearsal with network disabled after acquisition, archived evidence, the exit
   demonstration, the P0 blocker list and the published known-limitations statement.
   Proof: the rehearsal is performed with egress disabled and its evidence archived; the
   blocker list is derived from the residual-risk register. **The milestone ends by asking the
   owner for the named maintainer, security and licence approvals; it is not self-approved.**

## Verification

`make check` remains the aggregate gate and must be green, verified by counting `make: ***`
lines rather than trusting the exit code. Byte-stability is verified directly by compiling the
reference case on `main` and on this branch and comparing the deployment-bundle, runner-plan,
semantic-manifest and selected-candidate digests. PostgreSQL-gated suites are run locally with
`OAK_TEST_DATABASE_URL` set against the pinned `postgres:17.6-alpine`, because CI provisions no
database; a skipped suite is recorded as a skip, never reported as a pass. New evidence-bearing
claims are backed by tests wherever a test is possible: artifact verification is tested against
a tampered copy, the honesty gate against a seeded overclaim, the `OAK_*` reference against the
source, and the egress claim against a live socket guard.

## Security, privacy and authority review

Sprint 8 adds no capability and moves no trust boundary. The release script, the release
workflow and the operator scripts are read-only or build-only: `scripts/verify_release.py`
and `scripts/verify_deployment.py` open nothing for writing, `scripts/check_clean_machine.py`
runs no mutating Docker command, and `.github/workflows/release.yml` holds `contents: read`
and publishes nothing. MCP stays design/read only, remote CLI keeps refusing local-only
commands, and runner apply stays behind signing, approval and independent runner
verification.

Untrusted input handled by new code: a `SHA256SUMS` manifest is treated as untrusted — a
name that is absolute or escapes the release directory is refused rather than followed, so a
hostile manifest cannot direct verification at an arbitrary file. Release artifacts are
**not signed**; the documentation states what checksums do and do not prove rather than
implying provenance they cannot carry.

Four confidentiality defects found by the review were fixed rather than documented, each
reproduced locally first: canonical and MCP validation diagnostics echoing the rejected
value, SQLAlchemy bound parameters reaching uvicorn's error log, and unhandled tracebacks
from `oak-runner` and `oak-db-migrate` disclosing paths and connection details. The
no-egress claim moved from a grep to an enforced test.

No external security review was commissioned, and no document implies one occurred; a build
gate now rejects unqualified assurance vocabulary.

## Operational and rollback plan

Every change is additive or a contained fix; reverting the branch is a complete rollback,
and no migration, key rotation or stored-data change is involved.

Two changes alter observable behaviour and are called out because a consumer could notice:
a malformed `If-Match` header now returns `OAK-PRECONDITION-INVALID` (422) instead of
`OAK-EXPECTED-VERSION` (409), and an artifact lookup miss now returns
`OAK-ARTIFACT-NOT-FOUND` instead of `OAK-WORKSPACE-NOT-FOUND` (still 404). Both are
corrections of a code carrying two meanings, both are free to make before the first release
and would need a deprecation window after it, and both are recorded in `CHANGELOG.md`.

The version move to `0.7.0` shifts no canonical digest — verified directly — so stored
workspaces, signed envelopes and trust anchors are unaffected. Dropping the
`jsonschema[format]` extra removes eight packages from the runtime closure and changes no
behaviour, because no `FormatChecker` was ever constructed; rollback is restoring the extra
and re-running `uv lock`.

## Progress

- [x] 2026-08-21 ExecPlan authored; tasks claimed in `STATUS.md`; branch
  `claude/sprint-8-community-release-hardening` created from `origin/main` at `9998508`.
- [x] 2026-08-21 Baseline recorded before any change: the reference case compiled on the
  branch tip at `9998508` produced `deployment_bundle 042313be`, `runner_plan 5e0a65ba`,
  `selected_candidate 576b0ca6`, `semantic_manifest 2ef34758` at case `0.1.7`, matching the
  invariant exactly.
- [x] 2026-08-21 M1 release identity and packaging hygiene: version `0.7.0` across `VERSION`,
  `pyproject.toml`, `package.json`, `web/package.json`, `STATUS.md` and the regenerated
  OpenAPI document, bound together by `make toolchain-check` with three drift tests;
  ADR-0002 recorded with the rejected alternatives; `jsonschema[format]` dropped, removing
  `rfc3987` (GPL-3.0-or-later) and seven other unused packages from the runtime closure
  (45 → 37) with a `docs/dependencies.md` review; the stray `-.uv-cache/` removed and the
  `.gitignore`/`.dockerignore` blind spot closed; sdist contents made an explicit exclude
  list and `reproducible = true` declared rather than inherited. Two consecutive builds
  produce identical digests; the sdist no longer carries a cache directory; byte-stability
  verified directly against the baseline (identical).
- [x] 2026-08-21 M2 clean install matrix: `docs/platforms.md` with the architecture and
  glibc floors read from the wheel tags in `uv.lock` (macOS x86_64 and Windows are
  unsupported, and the reasons are specific), the Kubernetes deferral written down with its
  four blockers, `scripts/validate_repository.py` moved off a bare `python`, and
  `tests/e2e/test_installed_wheel.py` — which builds the real wheel, unpacks it where no
  source tree sits above it, and drives the reference journey from packaged data. That is
  the branch every other e2e test misses, because `.venv` is an editable install. A
  `linux/amd64` API image builds and runs `oak --version` → `0.7.0` as uid `oak`.
- [x] 2026-08-21 M4 supply-chain release: `scripts/build_release.py` and `make release`
  (double build with digest comparison, clean-environment install, out-of-checkout smoke
  test, release SBOM of the installed runtime closure stamped with the artifact digests,
  generated licence inventory naming the packages this platform's markers exclude, and
  `SHA256SUMS`); `scripts/verify_release.py` and `make verify-release`;
  `.github/workflows/release.yml` with `contents: read`, running `make check` before
  `make release`, leaving `ci.yml` untouched; `docs/release-process.md`. Fifteen tests drive
  the verifier against tampered, equal-length-substituted, missing, empty, malformed and
  path-escaping inputs. The generated inventory shows LGPL-3.0 Psycopg as the only copyleft
  entry — the GPL transitive is gone.
- [x] 2026-08-21 M3 upgrade, backup and restore: `scripts/verify_deployment.py` walks the
  artifact index and re-verifies every object, and `tests/integration/test_backup_restore.py`
  creates a scratch PostgreSQL database, migrates it to head, writes state, and proves that a
  database restored *without* its artifact root is detected — the exact half-restore the old
  `pg_dump`-only documentation would have produced. Also pins the Alembic `downgrade()`
  refusal, the export/reimport round trip, and the fail-closed behaviour of a workspace
  whose manifest carries an unknown `schema_version`.
- [x] 2026-08-21 M5 security review and residual risk: `docs/security/threat-coverage.md`
  (all nineteen threat ids mapped to tests, 8 direct / 9 partial / 2 structural / 0 none,
  every cited test verified to exist), `docs/security/residual-risk.md` (35 stable-id
  entries, severities scored for the shipped configuration, owners explicitly unassigned),
  `SECURITY.md`, an assurance-claim gate in `tools/check_repository.py` with a documented
  escape for denials, and `tests/integration/test_offline_boundary.py` which runs the whole
  reference journey with every outbound socket path broken plus a guard-the-guard test.
  **Four confidentiality defects found and fixed**, each reproduced first: canonical and MCP
  validation diagnostics echoing the rejected value, SQLAlchemy bound parameters reaching
  uvicorn's error log, and tracebacks from `oak-runner` and `oak-db-migrate`.
- [x] 2026-08-21 M6 performance: `scripts/benchmark.py` with a machine-readable provenance
  header and `docs/performance.md`. Reference compiler 8.75 s median against a 120 s
  requirement; interactive read p95 31.9 ms (case) and 58.3 ms (audit) against 500 ms;
  workspace manifest reads 4.0 ms at zero artifacts and 281.2 ms at 43. Four measurements
  are reported as *not measured*, with the reason, rather than omitted.
- [x] 2026-08-21 M7 operator documentation: `docs/operations.md`, `docs/configuration.md`
  (all 25 `OAK_*` variables, pinned to the source by a contract test that fails in both
  directions), the generated `docs/error-codes.md`, and `scripts/check_clean_machine.py`.
  Two stable-code defects found while compiling the reference were fixed: a malformed
  `If-Match` returned 409/exit 4, telling automation to retry something that can never
  succeed, and an artifact miss reported as a missing workspace on surfaces that opaque the
  message.
- [x] 2026-08-21 M8 contributor documentation: `CONTRIBUTING.md`, `docs/README.md`, the six
  cited architecture ADRs mirrored into `docs/adr/architecture/` with provenance headers and
  a contract test that every cited ADR resolves, and `docs/development.md` updated with the
  new targets and the silent PostgreSQL gate. The product-reference prohibition gained one
  narrow, tested exception for the mirror directory, because ADR-0012's subject is the
  boundary between the distributions.

## Decisions

- 2026-08-21 **The release version is `0.7.0`, not `0.1.0`** (owner decision). `sprints.md`
  names the release target `0.1.0`, but `VERSION` and `pyproject.toml` are `0.6.0.dev6` and PEP
  440 sorts `0.1.0` *below* it, so publishing `0.1.0` would be an ordering regression that a
  pre-release-tolerant resolver would refuse to prefer. `0.7.0` sorts above every existing
  development build, needs no epoch, and keeps the pre-`1.0` "breaking change is possible but
  never silent" posture intact. Releasing `0.6.0` was rejected because the number reads as
  "sprint 6" while the release contains Sprint 7 and 8 work. Recorded as an ADR;
  `docs/compatibility.md`, `VERSION`, `pyproject.toml`, `package.json`, `web/package.json`,
  `STATUS.md` and the contract tests are all moved to agree.
- 2026-08-21 **Release artifacts are checksummed, not signed** (owner decision). No maintainer
  signing key exists and inventing one would manufacture assurance that no accountable human
  stands behind. The release ships a `SHA256SUMS` manifest, digest-pinned image references, and
  verification instructions that are tested against a tampered artifact; the documentation
  states plainly that artifacts are unsigned and what that does and does not prove. Sigstore
  keyless signing was rejected for `0.7.0` because verification would then require reaching a
  hosted transparency log, which conflicts with the no-mandatory-hosted-dependency invariant.
- 2026-08-21 **Release automation lands in a new `.github/workflows/release.yml`; the `check`
  job is not touched** (owner decision). CI is green and the `check` job's signal is load
  bearing, so the release build is a separate tag/dispatch-triggered workflow. The reason this
  belongs in CI rather than on a maintainer's laptop is concrete: today CI builds the wheel and
  sdist and then discards them, and never builds a container image at all — the blind spot that
  let the API image stay unbuildable from Sprint 6 until 2026-08-20.
- 2026-08-21 **The unused `jsonschema[format]` extra is dropped rather than approved.**
  Nothing in `src/` constructs a `FormatChecker`, so the extra changes no behaviour, but it
  places `rfc3987` 1.3.8 (GPL-3.0-or-later) in the runtime dependency closure of an Apache-2.0
  distribution, unrecorded in `docs/dependencies.md`, which records jsonschema as "MIT".
  `format-nongpl` was rejected because it keeps eight unused runtime packages to preserve a
  capability nothing enables; enabling format checking was rejected because tightening
  validation is a breaking change for producers under `docs/compatibility.md`.

## Post-implementation audit

A seven-lens multi-agent adversarial audit ran against the Sprint 8 diff — release
integrity, honesty, defects in the new Python, operator documentation verbatim, contracts
and boundaries, security-fix regression, and a repo-wide latent sweep — followed by an
independent skeptic per finding, prompted to refute by default.

It raised **34 candidates**. Twenty were routed to skeptics; **eleven survived**
refutation and nine were refuted (three as not-a-defect, six as already-covered or
over-scoped). The remaining fourteen exceeded the verification cap and were verified by
hand instead. **Every finding acted on below was reproduced locally first**, and several
were not: the "corrupt journal crashes `status`" claim only reproduced once the journal
was placed at the real path, and the "malformed dispatch envelope" claim only reproduced
for `"lease": null` specifically, not for the shapes the reporter first tried.

No authority bypass was found. Every real defect was a robustness, integrity-of-evidence
or honesty failure — which, for a sprint whose entire deliverable is evidence, is the
category that matters most.

### Fixed

- **The release verifier's containment guard was defeated by one extra space (high).**
  `_parse` applied the traversal check to the raw name field and then stored
  `name.strip()`. A manifest line with three spaces instead of two — `<digest>` +
  separator + ` /etc/hosts` — is not absolute *as written*, so the guard passed, and the
  stripped form is what got opened. The verifier printed `OK /etc/hosts` and exited 0
  while the actual artifacts were never hashed. `sha256sum -c` refuses the same manifest.
  The guard now validates the name exactly as written, refuses padding, NUL, CR,
  self-reference and duplicates, and re-checks containment after `resolve()` so a symlink
  inside the directory cannot escape either.
  (`tests/integration/test_release_verification.py`)
- **The runner's verification-policy enforcement was dead code (high).**
  `verify_dispatch` read `policy.get("body", policy)`, and no compiled verification policy
  has ever carried a `body` key — the clauses live under `content` — so the lookup always
  returned the wrapper, the comparison was always against `None`, and the guard could not
  fire for any plan the compiler produces. It was also the only attachment admitted
  without a schema check. Both are fixed; the clause that refuses a policy contradicting
  signing or approval is now reachable. What is *not* fixed is recorded as `RR-032`.
- **Untrusted brief content blew the stack (medium).** The structure-depth bound runs
  after parsing, and `RecursionError` is a `RuntimeError` rather than a `ValueError`, so
  it escaped intake's except clause entirely. A 120 KiB brief of `{"a":{"a":{…` — well
  inside the 256 KiB size limit — reached `create_design_case` as its first statement and
  raised an uncaught `RecursionError`. Both parsers are recursive; both are now guarded,
  and the refusal reuses the depth guard's own `OAK-INTAKE-COMPLEXITY`.
- **`oak-runner status` crashed on exactly the condition it exists to report (medium).**
  A corrupt or truncated journal raised `JSONDecodeError`, and a wrong-shaped line raised
  `TypeError` — neither an `OAKError`, and `entries()` sat outside any guard. `run_once`
  calls `verify_chain()` unguarded too, so a damaged journal wedged the runner as well as
  the command meant to diagnose it. Malformed lines are now `OAK-JOURNAL-TAMPERED` and
  `status` reports `unreadable`.
- **A hostile mailbox envelope killed the runner before it could deny anything (medium).**
  The correlation id was derived from `envelope["lease"]["lease_id"]` before the schema
  check and outside the try, so `"lease": null` raised `AttributeError`.
- **The error-code reference was incomplete while claiming completeness (medium).** The
  generator walked only `OAKError("CODE", …)` call sites, so 55 codes never reached the
  document — eligibility reasons that are returned rather than raised, codes passed as a
  `code=` argument, and the HTTP and CLI mapping codes. On REST and MCP a not-found
  message is opaqued, which leaves the code as the operator's only signal. Now 260 codes,
  with a test that fails if the source mentions one the document does not.
- **The uninstall procedure and the clean-machine checker named images Compose never
  creates (medium).** Compose names images `<project>-<service>`; both looked only for
  `<org>/<name>`, so every built image survived an uninstall and the checker still said
  "clean". The checker also under-reported directory sizes by up to 46% and reported
  `~/.oak` a fourth time alongside its own three children.
- **The published performance figure described work it did not measure (medium).**
  `build_compiled_case` ends at `bundle_compiled`; the description claimed it covered
  signing and dispatch. Corrected in `docs/performance.md`, the JSON, the threat-coverage
  index and the offline-boundary test's own docstring.
- **The restore-verification step could not be run on the deployment it documented
  (low).** In Compose, `OAK_DATABASE_URL` and `OAK_ARTIFACT_ROOT` name a host and a path
  *inside* the containers. The runbook now carries the port-publish and volume-copy
  sequence the rehearsal actually used.
- **The runner reads a control-plane variable, and the configuration reference said it
  never does (high, honesty).** `OAK_SCHEMA_DIRECTORY` selects the schema registry the
  runner verifies every dispatch against; an operator hardening a runner environment had
  been told not to bother scoping it. Corrected, and recorded as `RR-033`.
- **The whole shipped product surface was filed under "Unreleased" (medium).** Sprints 0–7
  sat under `## Unreleased` *below* the `0.7.0` heading, so everything that ships read as
  pending.
- **Three cells of the platform matrix contradicted the lockfile they cite (low).** The
  x86_64 glibc floor is 2.24, set by `greenlet`, not 2.17; the aarch64 floor is 2.27, set
  by `psycopg-binary`. The distinction that matters is now stated too: `greenlet` ships an
  sdist, `psycopg-binary` ships none.
- **A valid uppercase-hex manifest was reported as a mismatch (low).** `sha256sum -c`
  accepts either case; OAK told the verifier their good artifact was tampered with — the
  worst possible false alarm from an integrity tool.
- Also fixed: two malformed rows in the threat-coverage table; TM-08 downgraded from
  `direct` to `partial` because the time-of-use half is unenforced; the runtime closure
  installed without hash verification; the egress pin missing `from <package> import
  <module>`; `verify_deployment` passing silently when it verified nothing; the backup
  table omitting the runner's own private key; and `oak-runner`'s missing-variable path
  emitting no error code.

### Recorded rather than fixed

- `RR-032` — the compiled verification policy's `mutation_allowed` and
  `allowed_operation_kinds` clauses are still unenforced. Enforcing them as written would
  deny the mutation path this release ships, because the compiled content is a hard-coded
  constant identical for read-only and mutation targets; correcting the constant shifts
  every bundle digest. That is a deliberate migration, not a release-week edit. Mutation
  remains gated by the target profile and a pinned-anchor approval, so this is a missing
  defence-in-depth layer, not an authority bypass.
- `RR-033` — `OAK_SCHEMA_DIRECTORY` crosses the runner's trust boundary.
- `RR-034` — the toolchain pins are never checked against the running binaries; the
  rehearsal itself built on Node 22.17.1 against a 24.18.0 pin with every gate green.
- The assurance-claim gate is line-scoped, so a claim split across a line break in this
  hard-wrapped corpus passes it. Stated where the gate is described rather than left to be
  discovered.
- The two ADR series share a number space, so a bare `ADR-00NN` citation is ambiguous. The
  contract test checks that a citation *resolves*; it cannot check which series was meant.
  `docs/adr/README.md` now tells authors to cite with a link.

### Found after the audit, while closing out

- **`OAK-S8-003` asks for dependency *and container* scans, and only the dependency half
  was done.** `make audit` covers the Python and web closures and is clean; nothing looks
  inside a built image, so the OS packages in the shipped images are unassessed. No scanner
  was available — `trivy`, `grype` and `syft` are not installed, and `docker scout`
  requires a Docker Hub login the release preparation would not perform. This is the one
  place where the sprint's own task list is not fully satisfied. It is recorded as `RR-035`
  and raised in its own section of the release decision rather than left in the register,
  because a maintainer may reasonably treat an unperformed task as a blocker.

### Not reproduced

Reported but did not hold up when driven directly: the release workflow's tag trigger
"never checked against VERSION" (it is a rehearsal trigger that publishes nothing);
`_percentile` "not nearest-rank" (it is); and `make clean-all` "leaving what the checker
flags" (it did, and was fixed before the finding was judged, which the skeptic then read
as not-a-defect).

## Discoveries and follow-ups

- **The Compose quickstart silently served a three-day-old build.** `docker compose up -d`
  reuses an existing image rather than rebuilding when the source changes, so the release
  rehearsal's stack came up reporting `0.5.0.dev5`. `curl /version` was the only thing that
  revealed it. This is the single most likely way a user's first impression of `0.7.0` is
  actually of something else.
- **`build_compiled_case` ends at `bundle_compiled`, not at a signed dispatch**, despite
  the module docstring saying otherwise ("a compiled case advanced to a signed dispatch").
  That docstring is what led the performance description astray. Worth correcting in a
  later sprint; left alone here because it is Sprint 5 code and the sprint's own claims
  have been corrected instead.
- **`migrations/env.py` reads `OAK_DATABASE_URL` directly and ignores the `sqlalchemy.url`
  config option** that `oak-db-migrate` sets. Harmless because the entrypoint sets both,
  but anyone invoking `alembic` directly must export the variable. Documented in the
  operations runbook.
- **The reference case has 43 indexed artifacts and manifest reads cost 281 ms at that
  depth.** Two data points cannot distinguish linear from super-linear growth. A third
  point would need a workspace builder that produces arbitrary revision depth, which does
  not exist; worth building before anyone claims a supported workspace size.
- **`docs/traceability.md` in the governance repository cites evidence fixtures
  (`security-*`, `poison-*`, `licence-*`, `reg-*`, `EV-SEC`, `EV-TEN`, `EV-LIC`, `EV-DEP`)
  that exist nowhere in the implementation.** Not touched by this sprint, but it points at
  named security evidence a reader cannot find, which undermines the map exactly where it
  matters most.
- **The full suite takes roughly eleven minutes**, most of it rebuilding the same compiled
  fixture. A session-scoped template would remove most of that; the same observation was
  recorded in Sprint 5 and remains true.
