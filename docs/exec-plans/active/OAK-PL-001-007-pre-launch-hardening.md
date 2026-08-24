<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-PL-001–007: Pre-launch hardening

## Status

- Owner/agent: Claude
- Started: 2026-08-24
- Last updated: 2026-08-24
- State: in-progress
- Claimed tasks: `OAK-PL-001`–`OAK-PL-007`

## Outcome

Before anything is published, the five residual risks that were deliberately recorded rather
than fixed at `0.7.0` are closed while breaking changes are still free: the compiled
verification policy tells the truth about its target and the runner enforces it before any
side effect (`RR-032`, `RR-011`); revocation notices are signed and the channel fails closed
(`RR-001`); the container runtime's resolved image digest is verified against the approved one
and registries can be allowlisted (`RR-003`); the toolchain check compares the pins to the
binaries actually running, and pnpm provisions the pinned Node so the comparison passes by
construction (`RR-034`); the web image runs nginx as a non-root user and Compose applies
container hardening (`RR-037`); and both container images carry a CycloneDX SBOM and a build
provenance record (`RR-038`). The release is re-cut as `0.7.1` with a fresh evidence set under
`docs/release/0.7.1/`, ending in a draft release decision that awaits the owner's approval.
A reader can prove each closure from the tests named per milestone, and can prove the digest
migration was deliberate from the before/after values recorded here and in `CHANGELOG.md`.

## Context and invariants

Sprint 8 is merged; `main` is at `cf6986a` (PR #12) with CI green on the remote, version
`0.7.0`, approved 2026-08-22 as a local-first developer release. **Nothing is published**: no
PyPI upload, no registry push, no git tag, no GitHub release. The owner's kickoff brief is
`/Users/nm/Projects/archicompiler/PRE-LAUNCH-PROMPT.md`; the residual-risk register
(`docs/security/residual-risk.md`, 38 entries) and the release decision
(`docs/release/0.7.0/release-decision.md`, with its two standing conditions on `RR-001`/
`RR-003`) are the governing records.

Local terms: the **reference case** is the compiled workspace produced by
`tests/runner_support.py::build_compiled_case` (fixed clock `2026-08-18T12:00:00Z`, fixed
idempotency keys), ending at case `design-case.public-manual-qa` version `0.1.7`. Its four
tracked digests are the **byte-stability baseline**. A **digest-shifting change** is any
change to the canonical bytes of an unchanged document (`docs/compatibility.md`).

Governing threat-model lenses: TM-02, TM-06, TM-08, TM-15. Governing invariants:
`docs/build/security-invariants.md` (runner pre-connection checks 2, 5, 7, 9; supply-chain
SBOM/provenance clause; fail-closed rules). Recipes applied (`skills.md`): Security review
(primary for `OAK-PL-004`–`006`), Dependency and release (primary for `OAK-PL-001`, `-007`),
Documentation and ADR.

Hard invariants:

- **No production or customer readiness claim.** `0.7.1` remains a local-first developer
  release; release approval is not a Gate 2/3 deployment approval.
- **No authority bypass.** MCP stays design/read only; remote CLI keeps refusing local-only
  commands; runner apply stays behind signing, approval and independent runner verification.
- No `command`, `shell`, `executable`, or `argv` field in any canonical document.
- `oak.runner` imports only `oak.contracts`, `oak.domain` and itself; `oak.contracts` and
  `oak.domain` are leaves; `oak.interfaces` may not import `adapters`
  (`tools/check_boundaries.py`).
- **Byte-stability is suspended for the `RR-032`/`RR-011` migration only** (Milestone 6), and
  only deliberately. Every other milestone ends by recompiling the reference case and proving
  the four digests unchanged. Baseline at `main` (`cf6986a`), case `0.1.7`, captured directly
  on 2026-08-24:
  - `deployment_bundle` `bundle.candidate-03.target.local-fixture` `0.1.0`
    `sha256:042313be7ccd8355cfb7eb21b67b3137bc897cbe92d0d77c2f8189a8f9175c00`
  - `runner_plan` `runner-plan.bundle.candidate-03.target.local-fixture` `0.1.0`
    `sha256:5e0a65ba9c1f17945c5100c5532c890806e71bed4c0c40c5e7099a97d4f459dc`
  - `selected_candidate` (`architecture_candidate` `candidate-03`) `0.1.0`
    `sha256:576b0ca62835a521439e44b280ffdfca79438323d45ae79e70521a27d14118b3`
  - `semantic_manifest` (`review_artifact` `semantic.candidate-03.target.local-fixture`)
    `0.1.0` `sha256:2ef34758128e13038d26b82847589b2b0ec2c5f25ba6ba56982a520a92a34d63`

  Supplementary baseline against `local-mutation-fixture.yaml` (not part of the recorded
  reference set; expected to shift in Milestones 5 and 6 because the fixture itself changes):
  - `deployment_bundle` `sha256:13269b85b124c2710d22133d4b25c37ba3fd131f8acf34e6c1e1a8e569f11a2b`
  - `runner_plan` `sha256:bd0d14d30bbc969b6962a3e422f3974bca325e71677994ae21de1c415c262010`
  - `semantic_manifest` `sha256:673849ac450b1b3f4215c1496881db4aef259b69fd8e055d9b3bff187ec8c1d8`
- Fail closed everywhere. Verification uses pinned keys and published digests, never a value
  carried inside the artifact being checked.
- No mandatory network or hosted dependency; `make check` keeps working with egress disabled
  after bootstrap. `make scan-images` and `make audit` are the sanctioned exceptions and stay
  out of `make check`.
- `.github/` edits are deliberate and called out; the `check` job in `ci.yml` is not touched.

Digest capture method (replayable on any commit): from the repository root, compile the
reference case into a temporary directory with `tests.runner_support.build_compiled_case` and
read `kind`/`id`/`version`/`digest` from `.oak/manifest.json`'s `artifact_index` for the four
tracked identities above. The snippet is checked into the branch history via this plan and
was used for every per-milestone verification below.

## Scope

### In

- **Release re-cut (`OAK-PL-001`).** Version `0.7.1` across every file
  `tools/check_toolchains.py::_check_release_version` binds; a `CHANGELOG.md` `0.7.1`
  section; a draft `docs/release/0.7.1/release-decision.md` added to the residual-risk count
  gate; fresh evidence recorded under `docs/release/0.7.1/` as later milestones produce it.
- **Toolchain runtime truth (`OAK-PL-002`, closes `RR-034`).** pnpm provisions the pinned
  Node (`use-node-version`); the self-masking `nodeVersion` setting is removed; a fatal
  runtime check compares the running Python and the pnpm-provisioned Node to the pins.
- **Non-root web image and Compose hardening (`OAK-PL-003`, closes `RR-037`).** The web
  image's runtime stage becomes `nginxinc/nginx-unprivileged` (uid 101), digest-pinned and
  guarded by `check_toolchains`; `compose.yaml` gains `read_only`/`cap_drop`/
  `no-new-privileges`/resource limits per service; the postgres pin and the previously
  unguarded Dockerfile lines join the drift check; a Docker-gated e2e assertion proves the
  runtime uid.
- **Signed, fail-closed revocations (`OAK-PL-004`, closes `RR-001`).** A `revocation`
  schema and example; producer signs notices in the `approver` role; the runner verifies
  every notice against pinned anchors and treats a missing directory or an unreadable,
  unsigned or invalid notice as denial of all pending dispatches.
- **Resolved-digest admission and registry allowlist (`OAK-PL-005`, closes `RR-003`).**
  Optional `execution.allowed_registries` in the target profile, enforced during
  verification before any adapter exists; post-`docker create` comparison of the runtime's
  resolved `RepoDigests` against the approved digest, failing closed with container removal.
- **The digest migration (`OAK-PL-006`, closes `RR-032` and `RR-011`).** The compiled
  verification policy becomes a function of the target; the stale `not_signed` reason and
  the digest-bound compatibility lies are corrected in the same migration; the runner
  enforces `allowed_operation_kinds` and `mutation_allowed` before dispatching; the signed
  examples are regenerated from a committed generator so their signatures verify.
- **Image SBOM and provenance, rescan (`OAK-PL-007`, closes `RR-038`, refreshes `RR-036`).**
  `scripts/scan_images.py` emits per-image CycloneDX SBOMs and an unsigned provenance
  record; the `images` job in `release.yml` runs it and ships the evidence; `make
  scan-images` re-run against the final `0.7.1` images; the recorded gap in
  `docs/build/security-invariants.md` is updated.
- Register, status, changelog and decision-record close-out in both repositories, then a
  multi-agent adversarial audit with independent refutation, then a PR with remote CI green.

### Out

- Publishing anywhere (PyPI, registry, tag, GitHub release) — the owner's separate act.
- Approving the `0.7.1` release — the draft decision record stops at
  **awaiting owner approval**.
- Any new product surface: REST paths, CLI commands, MCP tools, artifact kinds.
- Enforcing `allowed_status` from the verification policy (recorded as future scope).
- Closing any other residual-risk entry; the register's remaining open entries stand.
- Signing release artifacts or images (`RR-005` stands; provenance remains unsigned).

## Contract and data changes

- **Repository version moves to `0.7.1`.** Version literals are digest-independent (proved
  in Milestone 1 by direct compilation, not assumed).
- **Canonical bytes of compiled bundles change once** (Milestone 6): the verification-policy
  review artifact becomes target-derived (id, `allowed_operation_kinds`,
  `mutation_allowed`), the signature marker's `reason` is corrected, and
  `_bundle_document`'s `compatibility` block stops asserting read-only constraints for
  mutation targets. `deployment_bundle` and `runner_plan` reference digests shift;
  `selected_candidate` and `semantic_manifest` provably do not. Called out in
  `CHANGELOG.md` as digest-shifting per `docs/compatibility.md` rule 4.
- **New canonical schema** `schemas/revocation.schema.json` (`schema_version 0.1.0`) with
  example, registered in `scripts/validate_repository.py::EXAMPLE_BY_SCHEMA` and
  `schemas/README.md`. Additive; no existing schema changes shape.
- **`schemas/target-profile.schema.json` gains optional `execution.allowed_registries`.**
  Additive and compatible (closed schema, optional field, no `schema_version` bump). The
  shipped read-only fixture is untouched, so its fingerprint
  `sha256:44863b03…` is unchanged; `examples/targets/local-mutation-fixture.yaml` adopts
  `allowed_registries: [docker.io]`, which recomputes its fingerprint everywhere it is used.
- **Runner protocol tightens** (unpublished, so no deprecation window is owed, recorded per
  `docs/compatibility.md`): revocation notices must be signed and schema-valid; a policy
  whose clauses forbid a requested operation kind is denied; a disallowed registry or a
  resolved-digest mismatch is denied. New error codes `OAK-RUNNER-REVOCATION`,
  `OAK-RUNNER-REGISTRY`, `OAK-RUNNER-IMAGE`; `OAK-RUNNER-POLICY` gains denial paths.
  `signed_payload_bytes` canonicalization is untouched.
- **`docs/compatibility.md` preamble is amended** to state explicitly that its promises bind
  operationally from the first published artifact, and that no `0.7.x` has been published.
- CLI, REST/OpenAPI, MCP surfaces: no shape changes. `docs/error-codes.md` regenerated.

## Milestones

### Milestone 0 — Branch, plan, baseline

- Work: branch `claude/pre-launch-hardening` from `origin/main` (`cf6986a`); this plan;
  baseline digest capture (values above); environment preflight (arm64 venv, Docker daemon,
  `opa` 1.19.1); baseline `make check` with `OAK_TEST_DATABASE_URL` set so the
  PostgreSQL-gated suites run.
- Proof: `make check` completes with zero `make: ***` lines; the four digests equal the
  values recorded in the exec plans from Sprints 6 and 8.
- Rollback: delete the branch.

### Milestone 1 — Re-cut as 0.7.1 (`OAK-PL-001`)

- Work: bump `VERSION`, `pyproject.toml`, `STATUS.md`, `package.json`, `web/package.json`;
  regenerate the OpenAPI document; open `CHANGELOG.md` `## 0.7.1` with a `### Versioning`
  stub noting `0.7.0` was approved but never published; create
  `docs/release/0.7.1/release-decision.md` as **draft, not approved** and add it to the
  residual-risk count gate's file list in `tests/contract/test_configuration_reference.py`.
- Proof: `make check` green; digest capture unchanged from baseline.
- Rollback: revert the commit.

### Milestone 2 — RR-034: provision the pinned Node, check the running binaries (`OAK-PL-002`)

- Work: `.npmrc` gains `use-node-version=24.18.0`; `pnpm-workspace.yaml` drops the
  self-masking `nodeVersion` and keeps `engineStrict`; `make bootstrap` triggers the
  one-time Node provisioning; `tools/check_toolchains.py` gains `runtime_failures()`
  (running Python vs `.python-version`; `pnpm exec node --version` vs `.node-version`;
  inability to run pnpm is itself fatal), called fatally from `main()` while `check()`
  stays pure for the mirrored contract tests; contract tests cover drift and fail-closed
  paths with an injected runner.
- Proof: `make toolchain-check` passes on a host whose system Node is 22.17.1 (the
  provisioned Node satisfies the check); the new contract tests fail it when the injected
  Node version drifts; `make check` green; digests unchanged.
- Rollback: revert the commit.

### Milestone 3 — RR-037: non-root web image, Compose hardening, pin coverage (`OAK-PL-003`)

- Work: `deploy/images/web.Dockerfile` runtime stage moves to
  `nginxinc/nginx-unprivileged:1.29.1-alpine@sha256:…` with the `apk upgrade` layer run as
  root and `USER nginx` restored after; `compose.yaml` gains per-service `read_only`,
  `tmpfs`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]` and resource limits
  where each service tolerates them (postgres capability set decided by testing and
  recorded below); `tools/check_toolchains.py` pins the nginx line, the postgres compose
  pin, and the previously unmatched `AS build` Python line; the mirrored contract tests
  extend accordingly; a Docker-gated web e2e assertion proves `docker compose exec web id
  -u` returns the unprivileged uid and the api returns `10001`.
- Proof: `docker compose up -d --build` serves `/version`; `make web-e2e` green including
  the new uid assertion; one `--platform linux/amd64` build succeeds; `make check` green;
  digests unchanged.
- Rollback: revert the commit; rebuild images from the previous Dockerfile.

### Milestone 4 — RR-001: signed, fail-closed revocations (`OAK-PL-004`)

- Work: `schemas/revocation.schema.json` + `examples/example-revocation.yaml` + registry
  entries; `ReleaseService.revoke_approval` signs the notice in the `approver` role through
  the existing signed-artifact path; the dispatch transport creates `revocations/` so its
  absence is abnormal; the runner's mailbox raises `OAK-RUNNER-REVOCATION` for a missing
  directory or unreadable/oversized notice, and verification validates each notice against
  the schema and the pinned `approver` anchor before honouring it.
- Proof: integration tests prove a signed revocation denies the matching dispatch; an
  unsigned notice denies (fail closed); **deleting the revocations directory no longer
  restores a revoked approval**; the e2e journeys pass unmodified; `make check` green;
  digests unchanged; `docs/error-codes.md` regenerated.
- Rollback: revert the commit.

### Milestone 5 — RR-003: resolved-digest admission, registry allowlist (`OAK-PL-005`)

- Work: optional `execution.allowed_registries` in the target-profile schema;
  `registry_host()` helper in `oak.domain.runner_adapters`; enforcement in
  `verify_dispatch`'s operation loop (denial `OAK-RUNNER-REGISTRY` before any adapter is
  constructed); `ContainerFixtureAdapter.apply` inspects the created container's image and
  requires a `RepoDigests` entry matching the approved digest, removing the container and
  raising `OAK-RUNNER-IMAGE` on mismatch or absence; the mutation fixture adopts
  `allowed_registries: [docker.io]`.
- Proof: unit tests with a scripted executor prove mismatch → removal + denial, empty
  `RepoDigests` → fail closed, match → success; an integration test proves a disallowed
  registry is denied by `verify_dispatch` with no executor ever constructed; the Docker
  mutation journey passes; `make check` green; the four reference digests unchanged (the
  mutation-target digests shift because the fixture changed — recorded under Progress).
- Rollback: revert the commit.

### Milestone 6 — RR-032 + RR-011: the sanctioned digest migration (`OAK-PL-006`)

- Work: `planning.py` derives the verification policy from the target (kinds, mutation
  flag, id), corrects the `not_signed` reason, derives the `compatibility` block's
  constraints from the target, updates `minimum_oak_version`, deletes the dead
  `MUTATION_KINDS`; `verification.py` validates and reads the policy before the operation
  loop and denies any requested kind outside `allowed_operation_kinds` and any mutating
  kind unless `mutation_allowed` is true (all `OAK-RUNNER-POLICY`, all inside
  `verify_dispatch`, structurally before adapter construction); docs
  (`signed-runner.md`, `compiler-flow.md`, `compatibility.md` preamble) updated;
  `docs/error-codes.md` regenerated; `scripts/generate_examples.py` added and the signed
  examples regenerated so their signatures verify against the migrated content, with a new
  contract test that verifies every signed example cryptographically.
- Proof: digest capture immediately before (equal to baseline) and after (recorded under
  Progress and in `CHANGELOG.md` as digest-shifting); `selected_candidate` and
  `semantic_manifest` byte-identical; case still `0.1.7`; an authentic re-signed
  restrictive policy denies a mutation dispatch with no journal written and a `denied`
  completion; the read-only live-guard test and the Docker mutation journey pass
  **unmodified**; `make check` green.
- Rollback: revert the commit; digest capture returns to baseline (re-verified).

### Milestone 7 — RR-038 + RR-036: image SBOM, provenance, rescan (`OAK-PL-007`)

- Work: `scripts/scan_images.py` additionally emits
  `oak-community-<name>-image-<version>.cdx.json` per image (trivy CycloneDX against the
  same exported tarball, still no Docker socket) and `image-provenance.json` (shaped after
  `build_release.py::_write_provenance`, recording the final-stage base references and
  digests, image IDs, platform, and `signed: false`); the `images` job in `release.yml`
  runs the script and ships the evidence in `image-evidence`; `make scan-images` re-run so
  `docs/release/0.7.1/` holds the scan + SBOMs + provenance; the recorded gap in
  `docs/build/security-invariants.md` becomes a closure note; contract tests cover SBOM
  naming, final-stage base selection and the unsigned marker without needing Docker.
- Proof: `make scan-images` exits 0 (or images rebuilt until no fixable findings) with the
  evidence files present; `make release` still runs without Docker; `make check` green;
  digests unchanged from the Milestone 6 values.
- Rollback: revert the commit; delete the evidence files.

### Milestone 8 — Register, status, decision record, drift fixes

- Work: close `RR-001`, `RR-003`, `RR-011`, `RR-032`, `RR-034`, `RR-037`, `RR-038` in the
  register (`RR-035` style; count stays 38); refresh `RR-036` from the rescan; finalize the
  draft `0.7.1` release decision (evidence table, digest before/after, an explicit
  resolution of the `0.7.0` record's count illegibility) ending at **awaiting owner
  approval**; update `STATUS.md`, `CHANGELOG.md`; update the governance repository's
  `STATUS.md` (including its header-date drift and the "How to resume" contradiction) and
  `security-invariants.md`.
- Proof: `make check` green (the count gate, version binding and error-reference staleness
  tests all pass); digests equal the Milestone 6 values.
- Rollback: revert the commit.

### Milestone 9 — Adversarial audit, close-out, PR

- Work: multi-agent adversarial audit of the branch diff — lenses: enforcement (deny before
  side effect), migration correctness (replayability, stale digest references, stale
  descriptions of pre-migration behaviour), runtime honesty (non-root proven in the running
  container; compose keys actually applied), supply-chain honesty (SBOM describes the
  shipped final stage), release integrity/honesty — each finding refuted independently,
  plus a repo-wide latent sweep and a bidirectional register-versus-code verification;
  every surviving finding verified by hand before any fix; remediation commits with their
  own verification; move this plan to `completed/`; final full gate; PR to `main`; remote
  CI green before merge.
- Proof: the Post-implementation audit section below records every finding, its refutation
  or fix, and the evidence; the PR shows CI green.
- Rollback: individual remediation commits revert independently.

## Verification

- Full `make check` per milestone (never two at once; PostgreSQL published via
  `compose.override.yaml` and `OAK_TEST_DATABASE_URL` exported; backgrounded runs verified
  by counting `make: ***` lines).
- Digest capture per milestone: unchanged everywhere except Milestone 6, where both sets
  are recorded here and in the changelog.
- Explicitly outside `make check`: `make web-e2e` (Milestones 3 and 9), `make scan-images`
  (Milestone 7), one `--platform linux/amd64` image build (Milestone 3), `make audit`
  (Milestone 9).
- Adversarial tests accompany every new denial path: unsigned/garbage/absent revocations,
  forbidden operation kinds under an authentically signed restrictive policy, disallowed
  registries, mismatched resolved digests — each asserting the denial happens with no side
  effect and asserting on `OAKError.code`, never message text.
- The e2e mutation journey (`tests/e2e/test_runner_journey.py`) passes unmodified after
  the migration — the brief's acceptance criterion that the policy must fit the shipped
  path, not the reverse.

## Security, privacy and authority review

- Input trust: revocation notices move from trusted-by-location to verified-by-signature
  under pinned anchors; target profiles remain operator-acknowledged local files; image
  references and digests remain compiler-copied from the acknowledged profile and are now
  verified against the runtime's resolution. No new network input.
- Authority: no new privileged operation. Every new check is a refusal, not a permission:
  the runner gains no capability, only more reasons to deny. Signing keys, roles and the
  approval chain are unchanged; the `approver` role signs revocations with the existing
  anchor plumbing. The separation between proposal, approval, signing and mutation is
  untouched.
- Fail-closed: every new path denies on absence, malformation or mismatch (missing
  revocation directory, unreadable notice, malformed policy clauses, empty `RepoDigests`,
  unknown registry when an allowlist is present). No check consults a value carried inside
  the artifact it is checking.
- Audit evidence: denials continue to publish signed completion messages through the
  existing mailbox path; no new logging of sensitive values; SBOM/provenance files contain
  package inventories and public build metadata only.
- No free-form shell path: the container adapter keeps its fixed allowlisted `docker`
  argument vectors; the new inspect/remove vectors are literal tuples through the same
  executor; `scripts/scan_images.py` keeps trivy socketless.

## Operational and rollback plan

Local-only change surface: no consumer exists (nothing published), no stored-data
migration is required (no `schema_version` moves; previously compiled workspaces remain
schema-valid and readable). The digest migration affects newly compiled bundles only.
Each milestone is one revertable commit leaving `make check` green; rollback of the
migration commit restores the baseline digests (verified). The `release.yml` change only
affects the tag-triggered/manual release workflow, which nothing has ever run against a
published artifact. Bounded failure surface for the compose hardening: a service that
cannot tolerate `read_only`/`cap_drop` fails its healthcheck at `docker compose up`,
observed immediately during Milestone 3.

## Progress

- [x] 2026-08-24 M0: branch `claude/pre-launch-hardening` created from `origin/main`
  (`cf6986a`). Environment preflight: venv `macosx-11.0-arm64`, Docker daemon 29.3.1
  arm64, `opa` 1.19.1. Baseline digests captured directly (recorded under Context and
  invariants); the four reference values equal the Sprint 6/8 records. Baseline
  `make check` green with `OAK_TEST_DATABASE_URL` set: zero `make: ***` lines,
  392 + 167 (4 skipped) + 42 tests passed, web build clean. The 4 integration skips
  are the file-backend variants of PostgreSQL-specific assertions in
  `test_workspace_repository_contract.py`, by design.
- [x] 2026-08-24 M1: version re-cut to `0.7.1` across `VERSION`, `pyproject.toml`,
  `STATUS.md`, `package.json`, `web/package.json`, regenerated OpenAPI (`info.version`
  the only OpenAPI change) and `uv.lock`. `CHANGELOG.md` `0.7.1` section opened;
  `docs/release/0.7.1/release-decision.md` created as an unsigned draft and added to the
  residual-risk count gate's file list. First gate run failed deliberately at
  `tools/check_repository.py` — the draft's external-review row used an assurance term
  the vocabulary gate forbids; reworded to cite the `0.7.0` record's restrictions
  instead. Full `make check` then green (zero `make: ***` lines), and the four reference
  digests recompiled unchanged, proving the version literals are digest-independent.
- [x] 2026-08-24 M2 (`OAK-PL-002`, RR-034): pnpm now provisions the pinned Node via
  `devEngines.runtime` in `package.json` (verified live: `pnpm exec node --version`
  reports `v24.18.0` on a host whose system Node is 22.17.1, after pnpm downloaded the
  runtime); the self-masking `nodeVersion` setting is deleted from
  `pnpm-workspace.yaml`; `make bootstrap` triggers the one-time download;
  `tools/check_toolchains.py` gained the fatal `runtime_failures()` (running Python and
  pnpm-provisioned Node vs the pins, pnpm-unavailable fails closed) and a declaration
  check that `devEngines.runtime` pins the same Node as `.node-version`. Five new
  contract tests. `make toolchain-check` passes on this host, full `make check` green
  (397 + 167/4 + 42), digests unchanged.
- [x] 2026-08-24 M3 (`OAK-PL-003`, RR-037): web runtime stage moved to
  `nginxinc/nginx-unprivileged:1.29.1-alpine` (digest-pinned), `apk upgrade` sandwiched
  between `USER root`/`USER nginx`; compose hardening applied to every service
  (`read_only` for api/worker/migrate/web, `tmpfs`, `cap_drop: [ALL]`,
  `no-new-privileges`, memory/CPU limits; postgres keeps a writable data volume with
  `cap_add: [CHOWN, SETUID, SETGID, FOWNER, DAC_OVERRIDE, DAC_READ_SEARCH]` — proven
  against a **fresh** data volume, so first-boot `initdb` works under the reduced set).
  `check_toolchains` now guards the nginx runtime pin, the compose postgres pin and the
  previously unmatched `AS build` Python line, with three new drift tests. Runtime
  honesty proven live: `docker compose exec` reports uid 101 (web) / 10001 (api,
  worker), captured as a docker-gated Playwright spec (`web/e2e/hardening.spec.ts`);
  `docker inspect` confirms `ReadonlyRootfs`, `CapDrop=[ALL]` and `no-new-privileges`
  actually applied. `make web-e2e` 4/4 green; one `--platform linux/amd64` web build
  succeeds and defaults to uid 101; full `make check` green (400 + 167/4 + 42); digests
  unchanged. Discovery: the managed-Node lockfile entry from M2 made the alpine build
  stage try to download a musl Node from `unofficial-builds.nodejs.org` (integrity-
  locked, but slow/unofficial and redundant — the base image IS the pinned Node), so
  `deploy/images/strip-managed-node.cjs` now strips `devEngines` and the lockfile
  runtime entry inside the image build only, failing the build loudly if the lockfile
  shape ever stops matching.

## Decisions

- 2026-08-24 **Re-cut as `0.7.1` with a fresh approval** rather than reusing `0.7.0`.
  Owner decision. The approved `0.7.0` record describes a build whose digests the
  `RR-032` migration invalidates; re-cutting keeps that record honest as history, and
  version numbers are free before publication. Alternative (reuse `0.7.0` with an
  addendum) rejected as leaving a signed record describing a build that no longer exists.
- 2026-08-24 **Fix both `RR-001` and `RR-003` now.** Owner decision. Both are the standing
  conditions on the release approval; `RR-001`'s fix introduces a new signed document
  class, which is additive today and a breaking deprecation cycle after first publication.
  Alternatives (fix only `RR-003`; add a hard local-only refusal and defer both) rejected
  because the cost asymmetry favours closing both while breaking is free.
- 2026-08-24 **`RR-034` is fixed at the cause, with a fatal check as backstop.** Owner
  decision. pnpm provisions the pinned Node, so the fatal runtime check passes by
  construction on a host with a different system Node; a fatal check alone would have
  broken `make check` locally, and an advisory check is fail-open for exactly the drift
  that already happened once.
- 2026-08-24 **The provisioning mechanism is `devEngines.runtime` in `package.json`, not
  `.npmrc` `use-node-version`.** Deviation from the owner's letter, empirically forced:
  under pnpm 11.15.1 both `use-node-version` (`.npmrc`) and `useNodeVersion`
  (`pnpm-workspace.yaml`) are read by `pnpm config get` but never provision or switch the
  runtime on this host, while `devEngines.runtime` with `onFail: "download"` downloads
  and uses Node 24.18.0 for `pnpm node`, `pnpm exec` and scripts. A side discovery worth
  recording: the removed `nodeVersion` setting made `engineStrict` evaluate `engines`
  against the *declared* version rather than the running one — the 0.7.0-era pin was
  verifying itself. With `devEngines.runtime` active and `nodeVersion` gone,
  `pnpm install --frozen-lockfile` passes under a system Node 22 because the engines
  check is satisfied by the genuinely provisioned 24.18.0.
- 2026-08-24 **Image SBOM/provenance generation lives in `scripts/scan_images.py`, wired
  into the `images` job of `release.yml`.** Owner decision. Reuses the exported tarball and
  the pinned socketless trivy; `make release` keeps needing no Docker. Alternatives
  (`make release`, CI-only) rejected for changing the release target's contract or leaving
  local rehearsals without image evidence.

## Post-implementation audit

*(empty until the audit runs)*

## Discoveries and follow-ups

*(recorded as found)*
