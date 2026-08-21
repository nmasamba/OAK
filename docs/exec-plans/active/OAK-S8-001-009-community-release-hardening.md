<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S8-001–009: Community release hardening

## Status

- Owner/agent: Claude
- Started: 2026-08-21
- Last updated: 2026-08-21
- State: in progress
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

To be completed as the work happens.

## Operational and rollback plan

To be completed as the work happens.

## Progress

- [x] 2026-08-21 ExecPlan authored; tasks claimed in `STATUS.md`; branch
  `claude/sprint-8-community-release-hardening` created from `origin/main` at `9998508`.

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

Not started. This section stays empty until the audit runs.

## Discoveries and follow-ups

To be recorded as they are found.
