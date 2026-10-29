<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-029–037: Tier 3, Batch A — formats, bounds and the catalogue

**Directed by the owner on 2026-10-29.** On 2026-10-23 the owner asked for the outstanding
backlog ranked by the cost and benefit of doing each item before 1.0; Tier 2 of that ranking
merged on 2026-10-29 as PR #41 (`e8f98da`). The owner then moved Tier 3 ("after 1.0") ahead
of 1.0, because its large items each change what 1.0 would promise: a format migration, a
bundle edge, a signed catalogue boundary, a native install mode, a scanner that feeds the
design and a selection rule are contract changes under `docs/compatibility.md`, so after 1.0
each would cost a deprecation cycle or a `2.0`, and before 1.0 a changelog entry. The kickoff
prompt is `TIER-3-PROMPT.md` in the original spec repo; it cuts Tier 3 into three batches,
each its own PR branched from the merged `main`. This plan is Batch A. It starts from
`origin/main` at `e8f98da` on branch `tier3-formats`. It bumps no version, cuts no tag,
writes no decision record, signs nothing and publishes nothing.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-29
- Last updated: 2026-10-29 (M2, the digest move: the bundle edge and the catalogue boundary)
- State: in-progress
- Claimed tasks: `OAK-V1-029`–`OAK-V1-037`

One plan covers nine task IDs: one per item A1–A8 of the prompt and one for the review, the
gates and the PR. They continue the release-readiness series (`OAK-V1`), so the planned
Sprint 15 keeps its number.

The batches, restated: **Batch A** (this plan) is the formats-and-bounds batch; **Batch B**
is the machine (hardware scanning first, then native installation); **Batch C** opens with
Sprint 15 (selecting a reviewed researched design) and holds the surfaces earlier sprints left
open (the PPTX, report tools over MCP, the external review package, metrics, web unit tests,
the PDF's structure tree). The owner's Q0 answer puts A, B and C's Sprint 15 before 1.0 and
the rest of C after it unless an item turns out cheap. Batch B starts only after the owner
has merged this batch, and branches from the new `main`.

## Outcome

After this plan:

1. **A file workspace can be upgraded, and rescued without upgrading** (`OAK-V1-029`,
   `RR-017`): a versioned manifest reader knows the current format and every older one a
   migration step accepts; `oak workspace migrate` runs the chain of pure, idempotent steps
   under the workspace lock, and nothing else ever migrates; `oak export` works on any known
   older format without migrating, so export is never the command that refuses. A step may
   change the manifest and the index and never rewrites a stored object's bytes: a document
   that must change shape becomes a new object with a new digest, recorded by an audit event
   that names the migration as its origin. The `0.9.0` reference workspace is a committed
   corpus under `tests/`, proven to import, to migrate (a no-op today), to run every command
   and to export un-migrated. Downgrade is not supported and the documents say so.
2. **A bundle's assurance plan is bound** (`OAK-V1-030`, `RR-008`): `deployment-bundle.json`
   carries a digest edge to `assurance-plan.json` and `oak validate bundle` checks it; a
   bundle written before the edge reports "assurance plan unbound", never "verified".
3. **An extension feeds the catalogue only when the operator's trust anchors vouch for it**
   (`OAK-V1-031`, `RR-025` and `RR-004`'s catalogue clause): an activated component-manifest
   or architecture-pattern extension enters the compiler's catalogue only when its pack is
   signed by an identity pinned in the operator's trust directory, and the catalogue snapshot
   records the provenance of every entry; an unsigned or foreign-signed pack never feeds a
   design. Items 2 and 3 land in one milestone, the one deliberate move of the four reference
   digests before 1.0 (Q1).
4. **Workspace reads are bounded, and the curve is published** (`OAK-V1-032`, `RR-030`): the
   manifest read cost measured at 0, 43, 200 and 500 audit events with hardware provenance in
   `performance.md`; a per-process verification cache keyed on the manifest's digest skips
   only the work whose inputs it is keyed on, so the API and the worker verify a workspace
   once per process and object reads keep verifying their digests; the CLI's per-command cost
   is measured and stated honestly.
5. **The runner and the worker survive a soak** (`OAK-V1-033`, `RR-031`): a consumed nonce is
   dropped only once its lease's expiry plus clock skew has passed and kept when the expiry
   cannot be read; processed dispatch directories are cleaned after a configurable retention
   that never removes the newest journal or a completion not yet ingested; the journal is
   appended from an in-memory head verified when the file is opened; the operation store has
   a lease extension the worker calls between steps. The runner's own signed heartbeat is
   decided with the owner (see Decisions) and, if it does not land, the register says so.
6. **Aggregate work is capped** (`OAK-V1-034`, `RR-024` and `RR-041`): per-address and
   per-tenant request limits answering `429` with `Retry-After` and an `OAK-*` code, a cap on
   queued and running operations per tenant, and a per-case daily count of billable model
   requests, all on by default with generous, configurable values (Q2), each an `OAK_*` row
   that the configuration contract test enforces. The limiter's state lives in one API
   process, which is what Community runs, and the documents claim nothing distributed.
7. **The container images reproduce** (`OAK-V1-035`, `RR-006`): Debian packages from a dated
   `snapshot.debian.org` archive, the Alpine side pinned, the user created from fixed files,
   `SOURCE_DATE_EPOCH` set and layer timestamps rewritten, so two builds of one commit give
   one image ID per platform; the `images` job builds each image twice and compares, and
   `make toolchain-check` requires that step (Q3). The register entry's bytecode claim is
   checked and corrected.
8. **A restored history's actors are claims the export made** (`OAK-V1-036`): a server
   restore records the importing actor as an audit event, keeps the restored events as
   history, and `compatibility.md` and `operations.md` say what a restored actor is.
9. **Review, gates and PR** (`OAK-V1-037`).

## Context and invariants

- **Assumptions.** No published release ever wrote a workspace manifest at a format other
  than `0.4.0` (checked at kickoff: `v0.7.1`, `v0.8.0` and `v0.9.0` all pin the const and
  write it), so the production migration chain starts empty and the mechanism is proven on
  a synthetic step registered by the tests, plus the real `0.9.0` corpus. The reference
  digests move exactly once, in M2. Docker Desktop on the development machine is arm64 and
  updates itself silently; CI's BuildKit version is pinned and recorded in M7.
- **Invariants.** No production readiness claim. No authority bypass: MCP stays design and
  read only, the remote CLI keeps refusing local-only commands, runner apply stays behind
  signing, approval, enrollment and the runner's own verification; research approves
  nothing. The runner executes `docker` alone, never a `PATH` lookup, a shell or a path a
  document names. No `command`, `shell`, `executable` or `argv` field in any canonical
  document, and no schema field named `command`. The import boundaries hold
  (`tools/check_boundaries.py`, `tests/integration/test_offline_boundary.py`); any widening
  is explicit. **Byte-stability with one deliberate move:** the reference case compiled on
  `origin/main` and on this branch is compared; only M2 moves the four reference digests,
  once, with the new digests in the changelog and `compatibility.md`; the report's JSON
  golden and PDF digest move only if M2 moves them, and no other milestone moves anything.
  **Fail closed:** an unknown `schema_version`, an unsigned extension, a nonce whose expiry
  will not parse and a bundle without the new edge are refusals or truthful "unbound"
  reports, never passes. `make check` keeps working offline after bootstrap; CI may
  download. Logs never carry a secret, user content or the limiter's client address unless
  the log allowlist says so explicitly. The OpenAPI baseline changes only by additive
  operations listed as unreleased. `make check` is judged by counting `make: ***` lines,
  never two at once, with `OAK_TEST_DATABASE_URL` on a throwaway, migrated PostgreSQL on
  `127.0.0.1:15433`. The owner's `oak-community` Compose stack (5173, 8080) and its
  database (15432) are never touched. `tests/live` is never run with
  `OAK_LIVE_MODEL_TESTS=1`. `docs/error-codes.md` is regenerated after every `src/` edit. No
  vendor attribution in commits or the PR.
- **Recipes** (`skills.md`): Persistence and migration (M1, M3); Contract change (M1, M2);
  Governed pack and Security review (M2); Runner safety and Domain use case (M4); Interface
  adapter and Security review (M5); Dependency and release (M7); Interface adapter and
  Domain use case (M6); Documentation and ADR throughout.
- **Files that matter.** `src/oak/adapters/persistence/file_workspace.py` (the manifest,
  `_validate_workspace_lineage`, export and import), `schemas/workspace-manifest.schema.json`
  (`schema_version` is a `const`), `src/oak/bootstrap.py` (`SUPPORTED_SCHEMA_VERSIONS`),
  `src/oak/interfaces/cli/validate.py` (the detached-bundle check),
  `src/oak/compiler/catalogue.py` and `src/oak/application/candidate_planning.py` (the
  snapshot every compiled artifact is bound to), `src/oak/application/extensions.py` and
  `src/oak/adapters/extensions/store.py` (activation, `oak extensions verify`),
  `src/oak/runner/mailbox.py`, `src/oak/runner/journal.py`, `src/oak/interfaces/worker.py`
  and `src/oak/ports/operations.py` with `tests/mcp_support.py`'s in-memory store,
  `src/oak/interfaces/api/app.py` (`MAXIMUM_REQUEST_BYTES`, the middleware and `_refusal`),
  `src/oak/interfaces/logs.py` (`ALLOWED_FIELDS`), `deploy/images/api.Dockerfile`,
  `deploy/images/web.Dockerfile`, `.github/workflows/release.yml`, `tools/check_toolchains.py`,
  `src/oak/application/control_plane.py` (`import_design_case`).

## Scope

### In

- A migration module in the application layer and a versioned reader in the file adapter;
  `oak workspace migrate`; the `0.9.0` corpus under `tests/fixtures/workspaces/`; the audit
  event type that names a migration.
- `schemas/deployment-bundle.schema.json`, the compiler's bundle writer, `oak validate
  bundle`; the catalogue port, the extension store's activation and the catalogue snapshot's
  provenance; the regenerated reference goldens and digests.
- A verification cache in `file_workspace.py`; `scripts/benchmark.py` or a sibling that
  measures the curve; `docs/performance.md`.
- `src/oak/runner/mailbox.py`, `src/oak/runner/journal.py`, `src/oak/runner/main.py`,
  `src/oak/interfaces/worker.py`, `src/oak/ports/operations.py`,
  `src/oak/adapters/persistence/operations.py`, `tests/mcp_support.py`.
- A limiter and an operation cap in the API and the application layer; the model-request
  count on the design-case service; `docs/configuration.md` rows; the OpenAPI document and
  its unreleased list.
- Both Dockerfiles, `release.yml`'s `images` job, `tools/check_toolchains.py`,
  `scripts/scan_images.py` where the evidence records the snapshot date.
- The importer's audit event on a server restore.
- Tests for each; `docs/security/residual-risk.md`, `docs/compatibility.md`,
  `docs/operations.md`, `docs/performance.md`, `docs/configuration.md`,
  `docs/release-process.md`, `docs/interfaces.md`, `docs/signed-runner.md`,
  `docs/development.md`, `docs/platforms.md` where a claim changes, the manual,
  `docs/error-codes.md` (generated), `CHANGELOG.md`, `STATUS.md`, the readiness list's
  "what 1.0 promises" item; the original spec repo's status, roadmap, backlog, changelog,
  `docs/build/security-invariants.md` and `docs/threat-model.md` where a control changes.

### Out

- Tier 0, and the owner's half of Tier 1.
- Batch B (hardware scanning, native installation) and Batch C (Sprint 15, the PPTX, report
  tools over MCP, the external review package `RR-028`, metrics, web unit tests, the PDF's
  structure tree, K3, K4), each with its own kickoff.
- A real `schema_version` bump of the workspace manifest, unless another item forces one
  (none is expected; see M1).
- `RR-004`'s other clause (policy decisions gate no state transition) stays open.
- Signing the curated in-wheel catalogue: the owner did not take that option under Q1.
- The runner's signed heartbeat, unless M4's decision brings it in.
- Compaction or archival of a workspace, unless M3's curve is super-linear.
- Any version bump, tag, decision record, signature, GitHub Release, PyPI upload or
  registry push.

## Contract and data changes

Planned at kickoff; each milestone records what shipped, as `docs/compatibility.md` will.

- `OAK-V1-029`: a new audit event type naming a migration (additive enum value); new CLI
  command `oak workspace migrate` (local-only); new codes for a workspace at a known older
  format and at an unknown one; the manifest schema keeps its `const` for the current format
  and the versioned reader owns every older one. No stored document changes shape.
- `OAK-V1-030` (shipped): `deployment-bundle.schema.json` (`0.3.0`) gains the optional
  `assurance_plan_ref`, written by every compile, so every newly compiled bundle's digest
  moves (Q1's move); `oak validate bundle` checks it, refuses a substituted plan with
  `OAK-VALIDATE-DIGEST`, and its JSON gains `assurance_plan` (`bound`, or `unbound` for a
  bundle written before the edge, which stays valid).
- `OAK-V1-031` (shipped): `catalogue-snapshot.schema.json` (`0.4.0`) gains the optional
  per-entry `provenance` and top-level `patterns`, written by every compile (Q1's move, in
  the same milestone); `oak extensions activate` keeps its surface; an active
  component-manifest or architecture-pattern pack reaches `compile_catalogue` when, and
  only when, at the read, its activation record names its manifest, its steward signature
  verifies against the trust directory and its payload matches the signed digests,
  otherwise the compile refuses with the new `OAK-CATALOGUE-EXTENSION`; the extension
  verifier and the feed share `oak.contracts.signatures.verify_pinned_signature`; the
  register says `RR-004`'s catalogue clause closed and its policy clause did not.
- `OAK-V1-032`: no contract change; a cache inside the file adapter and the measured curve.
- `OAK-V1-033` (shipped): `OAK_RUNNER_HEARTBEAT_SECONDS` and
  `OAK_RUNNER_DISPATCH_RETENTION_DAYS`; the runner publishes the `heartbeat` message kind
  the schema always listed, `audit-event.schema.json` gains `runner_heartbeat` (additive)
  and the case gains the extension `oak.community/runner_heartbeat_refs`; `oak ingest`'s
  JSON gains `heartbeats`; the nonce ledger (a runner-home file) is a map of nonce to lease
  expiry, a `0.9` list still read; the operation-store port already had `heartbeat`, which
  the worker now calls between its steps, so the port and the PostgreSQL adapter are
  unchanged.
- `OAK-V1-034` (shipped): `OAK_REQUESTS_PER_MINUTE_PER_ADDRESS`,
  `OAK_REQUESTS_PER_MINUTE_PER_TENANT`, `OAK_OPERATIONS_PER_TENANT` and
  `OAK_MODEL_REQUESTS_PER_CASE_PER_DAY`; `429` with `Retry-After` documented on every
  REST operation (additive under the baseline check, listed in `compatibility.md`); the
  new codes `OAK-RATE-LIMIT-ADDRESS`, `OAK-RATE-LIMIT-TENANT`, `OAK-OPERATION-QUOTA`,
  `OAK-MODEL-BUDGET` and `OAK-LIMIT-CONFIG`; `OperationStore.active_count` on the port,
  the PostgreSQL store and the in-memory test store; the log allowlist keeps the client
  address out, so a refused request's line carries the limit's code only.
- `OAK-V1-035` (shipped): build-time only. `ARG DEBIAN_SNAPSHOT` and `ARG SOURCE_DATE_EPOCH`
  in the API Dockerfile, no `apk upgrade` in the web one; `scripts/reproduce_images.py`;
  both workflows pin BuildKit `v0.34.0` by digest and build twice; the release evidence
  gains `image-reproducibility.json`, and `image-provenance.json` gains `reproducibility`
  beside a `byte_reproducible` that is true only from that record; `scripts/scan_images.py`
  takes `--reproducibility`.
- `OAK-V1-036` (shipped): `workspace_restored` in the audit event's `event_type` enum
  (additive), written by a server restore of a server export under the importing actor
  with `interface_origin: import`, and the case and event extension
  `oak.community/restored_from`; the restored case comes back one patch version on;
  importing the same export again is a duplicate whatever the key.

## Milestones

### M0 — Kickoff (`OAK-V1-029`–`037` claimed)

- Work: branch `tier3-formats` from `origin/main` (`e8f98da`, CI green); this plan; the rows
  claimed in `STATUS.md`; both repositories' status corrected for PR #41's merge; the
  owner's Q0 and Q1–Q3 answers recorded.
- Proof: `make validate` here; the original spec repo's validator.
- Rollback: revert the kickoff commit.

### M1 — The workspace format migration (`OAK-V1-029`)

- Work: the versioned reader (raw manifest read, the known-format set, the refusal codes);
  the migration chain and its step type; `oak workspace migrate`; export of an older format
  without migrating; the `0.9.0` corpus from a detached worktree at `v0.9.0`; `operations.md`
  § Upgrade rewritten; `compatibility.md` and the register.
- Proof: the corpus imports, migrates as a no-op, runs every command and exports
  un-migrated; a synthetic older format upgrades through a test step, twice as a no-op, and
  two interpreters with different `PYTHONHASHSEED` values produce byte-identical results; an
  unknown format is refused on every command but names the build that can read it; the
  fixture holds a tenant and workspace id and nothing secret.
- Rollback: revert the commit; the const-only reader returns.

### M2 — The digest move: the bundle edge and the catalogue boundary (`OAK-V1-030`, `OAK-V1-031`)

- Work: the assurance-plan edge in the bundle and `oak validate bundle`; the provenance
  field in the catalogue snapshot; the activation path that feeds a signed component or
  pattern pack into the catalogue port; the goldens and the four reference digests
  regenerated once; the changelog's digest note and `compatibility.md`.
- Proof: a substituted assurance plan is caught; an old bundle reports "unbound"; a runner
  plan compiled from an old bundle still verifies (nothing is re-signed); an unsigned pack,
  a pack signed by a key outside the trust directory, and a tampered pack never reach the
  catalogue; a signed one does, with its provenance in the snapshot; the reference case on
  `origin/main` and on this branch differ only in the bundle, the snapshot and what names
  them, recorded.
- Rollback: revert the commit; the digests return.

### M3 — Bounded workspace reads (`OAK-V1-032`)

- Work: the measurement at 0, 43, 200 and 500 events with synthetic workspaces and hardware
  provenance; the per-process cache keyed on the manifest digest; `performance.md`.
- Proof: a test that the first read in a process verifies fully and a later read of the same
  bytes does not repeat it, that a changed byte invalidates, that a mutation's validation
  never consults it, and that object reads still verify digests; the curve published with
  what the change did and did not improve, the CLI's per-command cost included.
- Rollback: revert the commit.

### M4 — Runner and worker soak limits (`OAK-V1-033`)

- Work: nonce expiry and retention in the ledger; processed-dispatch cleanup after a
  configurable retention; the journal's in-memory head; the lease extension on the
  operation-store port, its PostgreSQL adapter and the in-memory test store; the worker
  calling it between steps; the heartbeat decision.
- Proof: tests that a nonce is kept while its lease could still be replayed and dropped
  after expiry plus skew; an unreadable expiry keeps the nonce; cleanup leaves
  `oak-runner status`'s comparison true and never removes the newest journal or an
  un-ingested completion; a journal appended after a verified open is byte-identical to
  one re-read on every append; the worker's lease extends under a long step.
- Rollback: revert the commit.

### M5 — Budgets and rate limits (`OAK-V1-034`)

- Work: the per-address and per-tenant limiters answering `429` through `_refusal`, the
  operation cap, the per-case daily model-request count; the `OAK_*` rows; the OpenAPI
  document and the unreleased list; what the log line may carry.
- Proof: tests at the limit and one past it, `Retry-After` present, `/healthz` and `/readyz`
  exempt, the cap refusing a queue past its size, the model count refusing the next
  billable request; `make check` and `make web-e2e-isolated` green under the defaults.
- Rollback: revert the commit; the limits disappear.

### M6 — The restore follow-up (`OAK-V1-036`)

- Work: an audit event on a server restore naming the importing actor, the restored events
  kept; `compatibility.md` and `operations.md` on restored actors.
- Proof: a server restore of a server export carries the new event under the importing
  actor; a local `oak import` is unchanged; the documents say what a restored actor is.
- Rollback: revert the commit.

### M7 — Reproducible images (`OAK-V1-035`)

- Work: both Dockerfiles on dated snapshots with a fixed user and rewritten timestamps;
  the `images` job building twice and comparing; `make toolchain-check` requiring the step
  and the pinned BuildKit; the register entry corrected; `release-process.md`.
- Proof: two local `linux/amd64` builds give one image ID per image; the CI job proves it;
  `make scan-images` still runs on the result.
- Rollback: revert the commit; the images build as before.

### M8 — Review, gates and PR (`OAK-V1-037`)

- Work: an independent adversarial review of the finished diff with every finding refuted
  independently and verified before it is acted on; the documentation sweep in both
  repositories; the readiness list's "what 1.0 promises"; `make check` with the test
  database; `make audit`; the browser suite on a throwaway project; the manual's PDF; the
  plan to `completed/`; the PR, with CI green over several runs.
- Proof: zero `make: ***` lines; CI green.

## Verification

Each item has a test on its failure path as well as its happy path, mutation-checked where
it is a new guard. Full gates at the end: `make check` with `OAK_TEST_DATABASE_URL` on a
fresh, migrated PostgreSQL 17.6 (port 15433), `make audit`, `make web-e2e-isolated`, the
reference case compiled on `origin/main` and on this branch and compared (differing only in
M2's declared move), and the PR's CI over several runs.

## Security, privacy and authority review

By milestone, to be filled as each lands:

- **M1, the migration.** A migration rewrites no object's bytes and edits no history; it
  runs only on an explicit command under the workspace lock; an unknown format fails closed
  on every command; export reads the index through the version-independent keys only.
- **M2, the catalogue boundary.** Trust anchors come from the operator's trust directory,
  never from inside the extension; the verifier never takes its policy from the document it
  checks; a review bundle is still not a security artifact and the register keeps saying so.
- **M3, the cache.** Keyed on the manifest bytes; never consulted when a mutation, an
  export or a migration is validated; every object a command opens keeps verifying. What
  a cached read skips is the walk over the history's objects, so a history object changed
  on disk after a process's first read is noticed when opened, by the next full
  verification, or by the next process, not by a cached read in that process (the closing
  review's W2; the documents say so).
- **M4, the runner.** The nonce ledger stays fail-closed; cleanup never hides a cut; the
  journal's head stays hash-chained.
- **M5, the limiter.** State in one process, claimed as such; the client address reaches a
  log only through the allowlist's decision; a refusal goes through `_refusal`.
- **M6, the restore.** The importer is recorded, not made an authority; a restored actor is
  a claim.
- **M7, the images.** Reproducibility and `RR-036`'s security updates coexist through the
  snapshot date, which the release moves; `make scan-images` still decides what ships.

## Operational and rollback plan

Each milestone is one commit and can be reverted alone. Operator-visible changes are listed
in the changelog as they land. The one stored-format mechanism (M1) adds no migration step
that a `0.9.0` workspace needs.

## Progress

- [x] 2026-10-29 M0. Kickoff: branch `tier3-formats` from `e8f98da` (CI run 40857131329
  green), this plan, the claim in both repositories, the owner's four answers recorded
  (`f095bad`).
- [x] 2026-10-29 M1 (`OAK-V1-029`). `oak.domain.workspace_format` (the format chain, the
  invariant keys and the four rules a step is held to, enforced by `migrate_manifest`); the
  file adapter's `raw_manifest`, an in-memory overlay for objects a migration produced but
  has not written, `format_report`, `migration_outcome` and `commit_migration`, with
  export and import of an older format as it is; `WorkspaceFormatService` and the
  `WorkspaceFormatPort`; `oak workspace status` and `oak workspace migrate` (local-only);
  `oak validate export` and `oak import` reporting `migration_needed`; the
  `workspace_migrated` event type and the `oak.community/migration` extension. Proof: 34
  unit cases of the rules (`tests/unit/test_workspace_format_rules.py`); 10 integration
  tests through the adapter, the service and the CLI with a synthetic older format
  (`tests/workspace_format_support.py`): refused on every command but status and export,
  the export byte-for-byte, imported as it is, migrated once with its successor and event
  and twice as a no-op, byte-identical under two `PYTHONHASHSEED` values in two
  interpreters, an unknown format refused everywhere including export and import, a
  corrupt object stopping an older export, a changed workspace refusing the planned
  commit, objects on a case-less workspace refused, a manifest-only step recording
  nothing, and `--server` refused; the `0.9.0` corpus (43 objects, from a detached
  worktree at `v0.9.0`) imports, migrates as a no-op, runs `questions`, `architecture` and
  `report --record`, exports and validates (`tests/integration/test_workspace_corpus.py`).
  Four mutations killed: the format gate, the source-digest check on commit, an export
  that migrated, and the rewrite rule. Unit and contract suites: 1,355 passed (`5e2468a`).
- [x] 2026-10-29 M2 (`OAK-V1-030`, `OAK-V1-031`). The bundle's `assurance_plan_ref` and
  its check in `oak validate bundle`; `oak.adapters.catalogue.ExtensionFedCatalogue`,
  which every compile reads through `bootstrap.compiler_catalogue` (the local CLI and the
  server alike), re-checking each active component-manifest or architecture-pattern
  extension's activation record, steward signature (against the trust directory, through
  the one shared `verify_pinned_signature`) and payload digests before a document enters
  the catalogue; per-entry `provenance` and the `patterns` list in the snapshot; the four
  reference digests moved once and re-pinned, the two report goldens and the published
  example report regenerated, the move written into `CHANGELOG.md` and `compatibility.md`.
  Proof: `tests/integration/test_catalogue_extensions.py` (10 tests through the CLI: a
  signed, activated component feeds the snapshot with its provenance and changes no
  design; curated-only provenance; a deactivated extension no longer feeds; a tampered
  payload, a signer no longer pinned, a pack dropped into the active directory, an altered
  activation record and a signature by a key outside the trust directory each refuse the
  compile; a curated id shadowed and a pattern duplicating a variant are refused as
  duplicates); two validator tests (a substituted assurance plan refused; a `0.9.0` bundle
  valid and `unbound`); `test_reference_digests.py` re-pinned; 1,417 unit, contract and
  affected integration tests passed. Five mutations killed: the signature re-check, the
  payload digest check, the missing activation record, the activation record's manifest
  digest, and the assurance edge in the validator. `make lint` and `make validate` green.
- [x] 2026-10-29 M3 (`OAK-V1-032`). The measurement: `scripts/benchmark.py --only
  workspace_growth` grows the reference workspace by synthetic revisions (each a recorded
  audit event with its artifacts, keyed by audit sequence) to 200 and 500 audit events and
  measures, at 0, 8 (the reference journey: 43 indexed artifacts), 200 and 500 events, the
  first manifest read in a process, a later read of the same bytes, and
  `oak questions --output json` as a subprocess, with hardware provenance
  (`docs/performance/workspace-growth-2026-10-29.json`, from the tree at `6261c35` with
  the cache applied, uncommitted). Found: linear, about 4.4 ms per audit event (34 ms at
  the journey, 875 ms at 200, 2.19 s at 500); the 283 ms recorded at `0.7.0` for the
  journey was schema meta-validation, gone since Sprint 13; a cached read is under 6 ms at
  500 events; a CLI command is about one second of start-up plus one verification. The
  cache: `file_workspace.py` keeps a per-process ordered map of 64 verified manifests
  keyed on the manifest's real path and the digest of its bytes, under a lock;
  `manifest()` skips `_verify` on a hit; `commit`, `export_to` and the migration start
  from `_verified_manifest()`, which always verifies; `clear_verification_cache` is
  exported for the benchmark and the tests. `record_recreation` hardened on the way: its
  event names the intent and the source record on a case past interpretation (the cache
  test recorded one on a compiled case and the lineage check refused it). Proof:
  `tests/integration/test_workspace_verification_cache.py` (6 tests: the first read
  verifies and the second does not; a changed byte verifies again and a broken lineage is
  refused; a mutation and an export verify in full whatever the cache holds; object reads
  keep checking digests; the cache never exceeds its bound). Three mutations killed: the
  key without the bytes' digest, a commit reading through the cache, and the bound not
  enforced. `docs/performance.md` rewritten at "Workspace growth", `RR-030` measured and
  bounded with its growth clause open, the changelog.
- [x] 2026-10-29 M4 (`OAK-V1-033`). The ledger: `RunnerMailbox.consume_lease_nonce`
  records each nonce with its lease's expiry and drops those past expiry plus
  `NONCE_RETENTION_SKEW_SECONDS` (300), keeping an unknown or unreadable expiry for ever,
  and reads a `0.9` list ledger. Cleanup: `clean_processed_dispatches` at the end of
  `run-once`, after `OAK_RUNNER_DISPATCH_RETENTION_DAYS` (default 30, 0 to 3650), keeping
  the newest processed dispatch and any with a message still in `messages/`, never a
  journal. The journal: `RunnerJournal` verifies the chain once per object and appends
  from an in-memory head; `verify_chain` re-reads. The worker: `OperationWorker.run_once`
  takes `renew`, a (now, lease_expires_at) pair read from the clock at each step, and
  calls the store's `heartbeat` before the handler and before recording its result;
  `run_worker` supplies it. The heartbeat (the owner's decision of 2026-10-29):
  `LeaseHeartbeat` publishes a signed `heartbeat` message at a step boundary once the
  interval has passed (`OAK_RUNNER_HEARTBEAT_SECONDS`, default 30; the acceptance beat
  always), naming the journal's head; `execute_dispatch` beats at lease acceptance,
  around each operation and through the container adapter's create, start and readiness
  steps; a beat the mailbox refuses is dropped without a gap in the sequence.
  `oak ingest` records a heartbeat as a `runner_heartbeat` event with the message as an
  artifact under `oak.community/runner_heartbeat_refs`, sorts a batch so a lease's
  heartbeats precede its completion, lists them apart from `accepted` (which stays the
  completions), and `_check_journal_reach` takes every heartbeat head as a floor. Proof:
  `tests/integration/test_runner_soak.py` (9 tests: a running dispatch publishes signed
  heartbeats, ordered by head, that ingest records once; the default interval publishes
  the acceptance beat alone; `0` publishes none and a bad value is `OAK-RUNNER-CONFIG`;
  a completion short of a heartbeat's head is refused and the case does not move; a
  heartbeat signed by an unenrolled key is rejected; processed dispatches are cleaned
  after the retention, never the newest, an un-ingested one or a journal, and `status`
  still reads `matched`; the ledger keeps a nonce while its lease could be replayed,
  drops it after, keeps an unreadable or unknown expiry, and reads a `0.9` list),
  `tests/unit/test_runner_journal_head.py` (one verified read per object, bytes identical
  to a fresh object per append; a tampered journal is never extended),
  `tests/unit/test_runner_heartbeat.py` (the interval, zero, and a dropped beat),
  `tests/unit/test_operation_worker_renewal.py` and `test_worker_loop.py` (the renewal
  from the step's own clock). `test_install_lifecycle.py`, `test_signed_runner.py`,
  `test_runner_trust_boundary.py`, `test_runner_revocation.py` and `test_operations.py`
  pass with the heartbeats on. Seven mutations killed: heartbeat heads not floors,
  heartbeats not recorded first, cleanup taking the newest, cleanup ignoring an
  un-ingested completion, the journal head skipping verification, the worker never
  renewing, and the runner never beating. `signed-runner.md` ("Heartbeats", "What the
  runner keeps"), `compatibility.md`, `operations.md`, `configuration.md`,
  `performance.md` ("Soak limits"), `threat-coverage.md`, `RR-031`, the changelog.
- [x] 2026-10-29 M5 (`OAK-V1-034`). The request limiter: `oak.interfaces.api.limits` (a
  token bucket per key, a minute's burst then the allowance per minute, at most 4,096
  keys per limiter, state in the one API process) behind `_RequestLimitMiddleware`,
  outside the loopback guard and inside the access log, keyed on the client address and
  on the tenant the request claims, exempting `/healthz` and `/readyz`, answering `429`
  through `_refusal` with `Retry-After` and `OAK-RATE-LIMIT-ADDRESS` or
  `OAK-RATE-LIMIT-TENANT` (`OAK_REQUESTS_PER_MINUTE_PER_ADDRESS` 1,200,
  `OAK_REQUESTS_PER_MINUTE_PER_TENANT` 6,000). The operation cap:
  `OperationStore.active_count` on the port, the PostgreSQL store and the in-memory test
  store; `OperationService.submit` refuses a new operation with `OAK-OPERATION-QUOTA`
  (`429`, `Retry-After: 5`) once the tenant has `OAK_OPERATIONS_PER_TENANT` (100) queued
  or running, after an idempotent duplicate is answered. The model budget:
  `oak.application.model_budget` counts the case's model-backed interpretations and
  narrations on the UTC day from its own audit history; `DesignCaseService.interpret` and
  `ReportService.record` refuse the next with `OAK-MODEL-BUDGET` (`429`, `Retry-After`
  to the next UTC day) at `OAK_MODEL_REQUESTS_PER_CASE_PER_DAY` (100), before anything is
  sent. `bootstrap.read_limit` parses every value (`0` off, up to a million, else
  `OAK-LIMIT-CONFIG`). Every operation in the contract documents `429` with `Retry-After`
  (`openapi/oak.openapi.json` regenerated, the web client unchanged; the baseline check
  passes, the change is additive and listed in `compatibility.md`). Proof:
  `tests/unit/test_request_limits.py` (6), `tests/integration/test_api_limits.py` (7: at
  the limit and past it with `Retry-After`, the probes exempt, the tenant key, zero off,
  a bad value refusing the app, the access line with the code and no address, the
  application's `429`s, the contract), `tests/integration/test_operation_quota.py` (3),
  `tests/integration/test_model_budget.py` (5), `active_count` on PostgreSQL in
  `test_operations.py` (gated; the macOS skip ledger counts it), the OpenAPI problem test
  extended. Seven mutations killed: the limiter admitting everything, the probes not
  exempt, the limiter's refusal without `Retry-After`, the cap never refusing, the budget
  never refusing, narrations not counted, and the application's `429` without
  `Retry-After`. `configuration.md` (four rows), `operations.md` (Limits, five
  troubleshooting rows), `compatibility.md`, `performance.md`, `threat-coverage.md`
  (`TM-14`), `RR-024` and `RR-041` bounded, the changelog, `CONTRIBUTING.md`.
- [x] 2026-10-29 M6 (`OAK-V1-036`). `DesignCaseService.record_restore` (sharing
  `_record_origin` with `record_recreation`) writes `workspace_restored` with
  `oak.community/restored_from` (the export's manifest id and digest, the case id and
  version, the number of events restored) after `CommunityControlPlane.import_design_case`
  has restored a server export, under the importing command's actor with
  `interface_origin: import`; the restore's duplicate check accepts a destination whose
  case records a restore from this export's digest, so the same export imports again as a
  duplicate under any key while another state of the case is still
  `OAK-IDEMPOTENCY-CONFLICT`. Proof: `tests/integration/test_local_to_server.py` (the
  restored event keeps the export's actor and the restore event carries the importer's,
  the origin on the case and the event, the status unchanged; a second import under the
  same and another key is a duplicate with no second event; a later export of the case is
  refused), the schema and contract suites. Three mutations killed: the restore not
  recorded, the duplicate check ignoring the recorded origin, and the event's origin not
  `import`. `compatibility.md`, `interfaces.md`, `operations.md` (Export: what a restored
  history says), `threat-coverage.md` (`TM-12`), the changelog.
- [x] 2026-10-29 M7 (`OAK-V1-035`). `deploy/images/api.Dockerfile`: `ARG SOURCE_DATE_EPOCH`
  in the build stage, so `uv`'s bytecode compilation writes hash-based `.pyc` files (it
  does: every file checked carries flag 3); the venv's `uv_cache.json` and its RECORD line
  removed after `uv sync` (uv's record of the build, stamped with the build's clock);
  Debian's packages from `snapshot.debian.org` at `ARG DEBIAN_SNAPSHOT=20261029T000000Z`
  through a rewrite of the base's `debian.sources`, apt run with `Check-Valid-Until` off
  and retries, apt's, dpkg's and ldconfig's clock-stamped files removed; the user created
  with `--no-log-init`, `chage --lastday 2026-01-01` and the account-file backups removed.
  `web.Dockerfile`: the trixie variant of the unprivileged nginx image, the same snapshot
  rewrite and cleanup under `USER root`, then `USER nginx` again.
  `scripts/reproduce_images.py` builds each Dockerfile
  twice (`--build-arg SOURCE_DATE_EPOCH=<the commit's time>`,
  `--output type=docker,rewrite-timestamp=true`, the second build `--no-cache`), compares
  the image IDs and writes the record; the release `images` job runs it for `linux/amd64`
  and hands the record to `scripts/scan_images.py --reproducibility`, whose provenance
  carries `reproducibility` and claims `byte_reproducible` only from a matching record;
  CI's `check-linux-arm64` job runs it for `linux/arm64`; both on
  `moby/buildkit:v0.34.0@sha256:b059f8d7…` through the buildx container driver.
  `tools/check_toolchains.py` requires one snapshot date in both Dockerfiles, the
  source-date argument, one pinned BuildKit in both workflows, the twice-built proof in
  both jobs and the record handed to the scan. Proof: locally, on a container-driver builder running
  the pinned BuildKit, both images built twice for `linux/arm64` from `9b0d6d0` gave one
  ID each with the Alpine web base (api `sha256:806692b3…`, web `sha256:b6e7ddcf…`); the
  scan of that web image then showed 60 fixable findings without `apk upgrade`, and the
  newest upstream Alpine images still three, so the web image moved to the trixie variant
  with the snapshot (`121142f`), and both images built twice again gave one ID each (api
  `sha256:63aa901d7ea063a5d13687590d5a57972c552cc04c1fbf4f16a63e857e1da117`, web
  `sha256:caabde7986158fe07cf4982b57fa169fd5687b0bc5bf1c45e2efa88cab9039e5`, from the
  tree at `ec9a9ae` with that change applied); `scripts/scan_images.py --build` on the
  result, with the record handed in, reports no fixable CRITICAL or HIGH in either image
  (API: 44 HIGH with no vendor fix, as before; web: 1 CRITICAL and 58 HIGH with no vendor
  fix, Debian's, where the Alpine image had reported none) and a provenance that says
  `byte_reproducible: true` for `linux/arm64`; the
  first attempt differed on the API image by exactly `uv_cache.json` and the RECORD line
  naming it, found by comparing the two builds' layers entry by entry, and reproduced once
  those were removed; `linux/amd64` is the release job's and the PR's CI to prove.
  `tests/contract/test_toolchain_contract.py` (eight new cases: the snapshot, the source
  date, a web snapshot date differing from the API's, the proof step in each workflow, the record handed to the scan, an
  unpinned and a divergent BuildKit, and the arm64 case re-pointed) and
  `test_image_scan_gate.py` (the provenance claims reproducibility only from a record that
  proves it); `make toolchain-check` green. `release-process.md` (Images, the checklist's
  snapshot item, the local proof), `RR-006` closed and `RR-036`'s remedy, `operations.md`,
  `dependencies.md`, `threat-coverage.md` (`TM-15`), the manual, the changelog.

## Decisions

- 2026-10-29 M0. **The owner's kickoff answers**, asked together at the start with options
  and a recommendation each, every one the recommended option:
  - **Q0, the cut and the order:** Batch A, then Batch B, both before 1.0; Batch C's Sprint
    15 before 1.0, so that 1.0 can promise that a reviewed researched design is selectable;
    the PPTX, report tools over MCP, metrics, web unit tests and the PDF's structure tree
    after 1.0 unless one turns out cheap. The owner's 2026-10-16 order put Sprint 15 before
    native installation; the dependency order is the reverse (Batch B gives Sprint 15 its
    installation path and its hardware class), and the Q0 answer follows the dependency.
  - **Q1, the one deliberate digest move:** yes, once, in one milestone (M2), with the
    goldens regenerated and the move written into `CHANGELOG.md` and `compatibility.md`;
    `RR-004`'s catalogue-feed clause joins, because the boundary where authenticity matters
    is the extension boundary (an activated extension feeds the catalogue only when its pack
    is signed by an identity in the operator's trust anchors). Signing the curated catalogue
    as well was offered and not taken.
  - **Q2, budgets:** on by default, generous, every value configurable; `RR-041` joins as a
    per-case daily count of billable model requests.
  - **Q3, images:** pin the distributions' package snapshots by date; the date moves at each
    release.
- 2026-10-29 M0. **The production migration chain starts empty.** Every published release
  (`v0.7.1`, `v0.8.0`, `v0.9.0`) pins and writes manifest format `0.4.0`, and `0.4.0` is the
  only format the adapter has ever written (since `41f3716`, Sprint 1). The mechanism is
  therefore proven on a synthetic older format that the tests register as a step, and on
  the real `0.9.0` corpus, for which migration is a no-op; no real step ships, as the prompt
  scopes it.
- 2026-10-29 M1. **Where the format knowledge lives.** The chain and its rules are pure
  domain code (`oak.domain.workspace_format`), so the file adapter applies them to files
  and the application runs the command without either importing the other; the
  PostgreSQL store does not implement the format port, because its format is the alembic
  revision `oak-db-migrate` carries forward. A step returns the manifest at its target
  format, the objects it added and, when the stored design case no longer reads under the
  current schema or now refers to a new object, that case at the current shape; the
  application, not the step, records the successor and the audit event, so no step can
  write history.
- 2026-10-29 M1. **Refusal codes.** A format the chain knows but does not serve is
  `OAK-WORKSPACE-MIGRATE`, naming the command; a format no step accepts is
  `OAK-WORKSPACE-FORMAT`, naming the build that reads it (the one case that used to be
  `OAK-WORKSPACE-CORRUPT`, recorded as breaking for a script that matched the code);
  `OAK-WORKSPACE-CORRUPT` keeps its meaning, an unreadable or invalid manifest or object; a
  step that breaks a rule, or a migration planned against a manifest that changed, is
  `OAK-WORKSPACE-MIGRATION`. An unknown format is refused on export too: nothing about
  its index can be believed, so copying it would copy an unknown.
- 2026-10-29 M1. **Export reads the invariant keys.** Every format keeps
  `schema_version`, `id`, `tenant_id` and the index's `digest` and `size_bytes` where they
  are, so an older workspace is exported from those alone, after the chain has proven in
  memory that it reads; the manifest is copied byte for byte and nothing a step produced
  is written. `oak import` keeps the older format too, and `oak workspace migrate` is
  run there: import never migrates implicitly either.
- 2026-10-29 M1. **A migration event names the source record.** The lineage check
  requires an event that names an intent to name the source record the intent was read
  from, as every interpretation and confirmation event does; the first version of the
  migration event named none and the migrated workspace failed its own validation, which
  the two-interpreter test caught. The reference comes from the case's
  `oak.community/source_record_ref`, never from the new object.
- 2026-10-29 M2. **Where the gate lives.** At the read, not only at activation. An
  activation proves what the trust directory said then; the catalogue feed asks again,
  so a steward key removed since activation, a payload edited in the active directory,
  a pack dropped there without activating it, or an activation record altered after the
  fact each stop the next compile. The refusal is loud (`OAK-CATALOGUE-EXTENSION`),
  never a quiet omission: an operator who activated an extension must not get a design
  that left it out without a word.
- 2026-10-29 M2. **One signature scheme.** The extension verifier's pinned-anchor check
  moved into `oak.contracts.signatures.verify_pinned_signature`, which returns a reason
  code; the verifier keeps its old report sentences through a map, and the catalogue feed
  has its own. Trust anchors come from the operator's trust directory
  (`bootstrap.load_steward_anchors`), never from the pack.
- 2026-10-29 M2. **The schema additions are optional fields.** `assurance_plan_ref`,
  per-entry `provenance` and `patterns` are written by every compile but optional in the
  schemas, so every stored document, the `0.9.0` corpus included, still validates; the
  validator reports an old bundle's assurance plan `unbound` instead of refusing it.
- 2026-10-29 M2. **What moved, and what did not.** The snapshot's provenance moves the
  snapshot digest, which every candidate names, so the candidate, the decision, the
  assurance plan, the bundle (also for its new edge), the runner plan and the case moved;
  the semantic manifest and the intents did not. The research golden moved for the same
  reason (25 leaves), the reference report golden in 10 digest leaves; the published
  example report was regenerated by substituting those values, which the equality test
  confirms. The provenance of a researched manifest is `research`, named beside the
  snapshot's existing `oak.community/research` extension.
- 2026-10-29 M2. **A pattern extension cannot add a variant.** The pattern schema's
  `variant` enum is closed to the four curated variants, so a contributed pattern can
  only duplicate one and is refused; the feed still handles the class, and the guide
  says so rather than implying a fifth design is a pack away.
- 2026-10-29 M0. **Task numbering.** `OAK-V1-029` to `-036` are A1 to A8 in the prompt's
  order (migration, bundle edge, catalogue, reads, soak, budgets, images, restore) and
  `OAK-V1-037` is the review; the milestones run A1, then A2 with A3, then A4, A5, A6, A8,
  A7, the review, because the migration must exist before anything changes a stored shape,
  the digests move once, and the images need Docker and the longest CI runs.
- 2026-10-29 M3. **What the cache is keyed on, and who may use it.** The manifest's real
  path and the digest of its bytes: the bytes are what the skipped verification would have
  read, so a manifest changed on disk, however slightly, is a miss. Reads only: a
  mutation's validation, an export and a migration start from a full verification whatever
  the cache holds, because they write from what they read. It holds 64 entries per
  process, under a lock, and remembers nothing about objects: object reads keep checking
  their digests.
- 2026-10-29 M3. **The "43" point is the reference journey.** The prompt's depths (0, 43,
  200, 500) mix the journey's artifact count with audit-event counts; the measurement
  walks audit events, so it labels each depth by audit events with the indexed artifacts
  beside: 0 (0), 8 (43), 200 (427), 500 (1,027).
- 2026-10-29 M3. **Measured on the uncommitted tree.** The curve was taken with the cache
  change applied and `6261c35` as the parent; the report says `source_tree_dirty: true`
  and is kept as taken rather than re-run after the commit, which changes no code the
  measurement runs.
- 2026-10-29 M3. **No compaction.** Linear growth at 4.4 ms per event puts the first read
  of a 500-event workspace at about 2 s; compaction or archival would change the stored
  format and stays open under `RR-030`, as the plan allowed only were the curve
  super-linear.
- 2026-10-29 M4. **A heartbeat is a report.** The owner chose the signed heartbeat for
  this batch rather than after 1.0; it moves no state, extends no lease (the runner's lease
  deadline is unchanged) and is bound to its lease like a completion: believed only from
  an enrolled runner for a dispatched lease. Its one effect on trust is a floor: the
  journal head it names must be reached by the lease's completion.
- 2026-10-29 M4. **Heartbeats before completions.** The filesystem mailbox lists messages
  by name, which puts `completion` before `heartbeat`; ingest sorts each batch so a lease's
  heartbeats are recorded first, and the sort is stable so nothing else moves. `accepted`
  keeps meaning the completions, which existing readers count; the heartbeats are listed
  apart, in the result and in the CLI's JSON.
- 2026-10-29 M4. **Two meanings of zero.** `OAK_RUNNER_HEARTBEAT_SECONDS=0` switches
  heartbeats off, which is what an operator means by it; the `run_once` test seam passes
  the interval `LeaseHeartbeat` takes, where `0` beats at every boundary, so a journey can
  be proven on a fake clock.
- 2026-10-29 M4. **What cleanup keeps.** The newest processed dispatch whatever its age,
  any whose completion is still in `messages/`, and every journal: the evidence stays, and
  `status` ties it by the lease the journal's own first entry names, so the comparison
  does not need the directory.
- 2026-10-29 M4. **The ledger keeps what it cannot read.** A nonce with no expiry (a
  `0.9` list) or an unreadable one is kept for ever: the ledger fails closed; only a lease
  the runner knows has lapsed, plus five minutes of skew, lets a nonce go.
- 2026-10-29 M4. **The worker renews from the step's clock.** The pair comes from the
  worker loop's clock at the moment of the step, not from the cycle's `now`, so a long
  step runs under a lease of its own length; a lease another worker has since claimed is
  reported as lost there, before the step runs or its result is recorded. The port's
  `heartbeat` already existed; nothing in the PostgreSQL adapter changed.
- 2026-10-29 M5. **The limits, and what they claim.** On by default and generous, as the
  owner chose (Q2): 1,200 requests a minute per address and 6,000 per tenant (the browser
  suite and `make check` build one app per test and stay far under; the benchmark's 200
  reads fit one burst), 100 operations queued or running per tenant, 100 billable model
  requests per case per day. The limiter's state is the API process's own and is claimed
  as such: two processes or hosts each keep their own count, and a restart forgets it.
- 2026-10-29 M5. **A token bucket, keyed on the claim.** A minute's burst then the
  allowance per minute, so an interactive page is never refused and a flood is answered
  before any header is examined (the limiter sits outside the loopback guard); the tenant
  key is the `X-OAK-Tenant` header's claim, bounded in length, and each limiter remembers
  at most 4,096 keys, so a stream of invented tenants or addresses cannot grow the table.
- 2026-10-29 M5. **The address stays out of the log.** The allowlist does not carry it; a
  refused request's line names the limit through its code (`…-ADDRESS` or `…-TENANT`) and
  nothing else of the key.
- 2026-10-29 M5. **The model budget is a count in the case's history.** A counter in
  memory would be useless to the CLI, which is one process per command, and would forget
  on restart; the audit history already records every model-backed interpretation (its
  event names the interpreter) and every narration (its event lists the narrative
  artifact), so the count is read from there and holds for the CLI, the API and MCP. A
  request the provider refused or that failed records nothing and is not counted; the
  adapters already stop it at one attempt and one retry. A case can be interpreted once,
  so in practice the count bounds narrations; a user who starts new cases is bounded by
  the request limits and the operation cap, not by this count, and the register says so.
- 2026-10-29 M5. **`429` with `Retry-After` for all three.** The limiter answers in
  middleware through `_refusal`; the cap and the budget are `OAKError`s the handler maps
  to `429`, adding `Retry-After` (five seconds for the cap, the worker's poll; the time to
  the next UTC day for the budget). `OAK-MODEL-RATE-LIMITED`, the provider's own limit,
  keeps its `429` without the header, unchanged.
- 2026-10-29 M5. **Bounded, not closed.** `RR-024` and `RR-041` move to Low with what
  remains stated: no per-job cost or token figure, a limiter that counts per process, and
  no tenant-wide model budget; closing them is the register review's call at 1.0.
- 2026-10-29 M6. **Record the importer, keep the history.** The prompt's recommendation:
  a server export's restore is the backup path, and re-creation would lose history. The
  restored events are the export's claims and stay as written; one event under the
  importing actor marks where the server's own attestation begins, and the documents say
  so in those words. A distinct event type (`workspace_restored`) rather than a second
  meaning for `workspace_imported`, so a reader of history needs no extension to tell a
  restore from a re-creation.
- 2026-10-29 M6. **Idempotent by the export's digest.** Appending an event made the
  destination's manifest differ from the import's, which the old duplicate check read as
  a conflict on every re-import; the check now also accepts a destination whose case
  records a restore from this export's digest, so a retry under any key is a duplicate,
  while an export of another state is refused as before.
- 2026-10-29 M7. **Pin by date, as the owner chose (Q3).** Debian's packages come from
  `snapshot.debian.org` at the date `ARG DEBIAN_SNAPSHOT` names, so the API image's
  security updates are the ones published up to that date and the date moves at each
  release (a checklist item in `release-process.md`); the register's `RR-036` names that
  move as the remedy. Alpine keeps no dated archive, and the newest upstream Alpine image
  (built 2026-10-19) still carried three fixable CRITICAL/HIGH findings, so dropping
  `apk upgrade` for a newer base digest, the prompt's second option, would have failed
  the scan gate: the web image moves to the trixie variant of the same unprivileged nginx
  image (`1.30.6-trixie`, 246 MB where the Alpine one was about 50 MB) and takes its
  packages from the same snapshot, so both images follow one rule.
- 2026-10-29 M7. **The claim is per platform and per builder.** A build is proven by
  building twice with no cached layer and comparing image IDs; the release job proves
  `linux/amd64`, CI's arm64 job proves `linux/arm64`, and the provenance says
  `byte_reproducible: true` only from the record of such a comparison, naming what it
  covers. A Compose build passes no source date and claims nothing.
- 2026-10-29 M7. **One BuildKit, pinned by digest.** Timestamp rewriting needs BuildKit
  0.13 or later, and Docker Desktop updates itself, so both workflows run the same
  `moby/buildkit:v0.34.0` by index digest (the newest release more than two weeks old on
  2026-10-29, as the action pins are chosen) through the buildx container driver, and
  `make toolchain-check` refuses an unpinned or divergent pin.
- 2026-10-29 M7. **`SOURCE_DATE_EPOCH` is the commit's time.** Passed as a build argument,
  declared in the build stage so that `uv`'s bytecode compilation sees it and Python
  writes hash-based `.pyc` files, used by BuildKit for the image configuration, and
  applied to every layer by `rewrite-timestamp=true`.
- 2026-10-29 M7. **What the register said about bytecode.** `UV_COMPILE_BYTECODE=1`
  compiles the venv's `.pyc` files at build time and `PYTHONDONTWRITEBYTECODE=1` keeps the
  runtime from writing any; the entry's "bytecode compilation is enabled" was true of the
  build and unclear about the runtime, and now says both.
- 2026-10-29 M8. **No second digest move.** The review suggested folding provenance into
  the candidates' idempotency digest; that changes the `candidates_generated` event and so
  every digest downstream of it, a second move of the reference digests, which Q1 allowed
  once. The digest stays as it was; a re-activation under another signer with the same
  manifests is a retry of the same compile, which is what the digest says it is.
- 2026-10-29 M8. **The cache's limit is documented, not removed.** A cheaper freshness
  check over the history's objects (a stat per object) would narrow what a cached read can
  miss but not close it; the honest fix is to say what is skipped, which every document
  now does, and to keep every write path verifying in full.

### Closing review findings (M8, 2026-10-29)

Five reviewers read the finished diff, one per area, and were asked to refute the plan's
claims; the documents sweep covered both repositories. Every finding was verified here
before it was acted on. Severity is the reviewer's.

| ID | Area | Severity | Finding | Resolution |
|---|---|---|---|---|
| W1 | M6 restore | high | A restore is two writes (import, then the event); a failure between them left a restored workspace without its event, and every retry was a duplicate; a natural trigger: the export carries the origin's idempotency records, so an import key the origin had used conflicted after the workspace existed | The event's key is the restore's own, derived from the import's key and the export, which removes the trigger the reviewer found (test); what remains is the one-commit window between the workspace write and its event, in which a crash leaves a restored history without its event, because that state cannot be told from this server's own export imported back (which the persistent journey does, and must answer as a duplicate): documented in `compatibility.md` and `operations.md`, and pinned by a test |
| W2 | M3 cache | medium | The cache skips the lineage walk, which reads the history's objects; the comment said the skipped checks were functions of the manifest bytes alone | The code comment, the docstring, `performance.md`, `RR-030`, the changelog and this plan say exactly what a cached read skips and when a changed history object is noticed; the mechanism is unchanged by decision |
| W3 | M1 rules | medium | The "never rewrites or drops" rule compared digest to size only: a step could relabel, re-kind, reorder or drop one of two entries sharing bytes | Every original index entry must stay as it was and in its place, as a prefix; six unit cases |
| W4 | M1 rules | medium | The history rule was a length check, skipped when a step dropped the key; a dropped key crashed `migrate()` | `audit_events` and `idempotency_records` must equal the input's; four unit cases |
| W5 | M1 import | medium/low | An imported older export was not schema-validated on its migrated view, so `validate export` could accept what `migrate` then refused | The import validates the migrated manifest as `export_to` does |
| W6 | M6 restore | low | Once the case moved on, a repeat import answered the moved case as the duplicate | The repeat answers the case as the restore recorded it; test |
| W7 | M1 commit | low | The chain runs outside the lock; the commit skipped the idempotency check, refusing a reused key only after writing objects | The commit checks the key before writing; the plan's wording corrected |
| W8 | M1, M3 | low | Two docstrings overstated | Corrected |
| C1 | M2 catalogue | medium | Provenance was keyed by bare id across kinds: a contributed manifest named like a curated pattern labelled the pattern as contributed | Provenance keyed by kind and id; a contributed id held by a document of either kind is refused as a duplicate; test |
| C2 | M2 catalogue | medium | The activation record was read, never validated; a bad time entered the snapshot and a missing key crashed | The record is validated against its schema and its time parsed at every read; test |
| C3 | M2 docs | medium | `compatibility.md` claimed a `0.9.0` reader validates the new documents; its schemas close additional properties | Corrected to the truth in both directions |
| C4 | M2 catalogue | low/medium | A forged activation record admitted a pack the verifier refused; compatibility was not re-checked at read | One domain check (`compatibility_problem`) serves the verifier and the feed, run at every read; test with a hand-written record |
| C5 | M2 catalogue | low | A malformed entry in quarantine stopped every compile | Only the active directory is read; test |
| C6 | M2 catalogue | low | The payload was read twice; the second read was parsed unverified | The verified bytes are what is parsed |
| C7 | M2 research | low | The CLI's research service read a bare curated catalogue; the candidates' idempotency digest ignored provenance | Research reads the fed catalogue (test); the digest is left as it was, because changing it moves the reference digests a second time, outside the owner's Q1 budget (decision below) |
| R1 | M4 journal | medium | "Never extended" was overstated: the chain is verified once per object, and `head()` re-read the file unverified, so a run and its file could diverge | Before each append the run checks the file still ends at its head; `head()` answers from the verified head; docs and test names say "once per run"; tests |
| R2 | M4 heartbeat | medium | A journal error inside a beat became an operation failure and a rollback; a refused beat retried at every boundary | A beat drops on any error, waits an interval, spends no sequence; test |
| R3 | M4 cleanup | low | A processed dispatch with an unreadable envelope was removed while its completion was unread | The journal's `lease_accepted` names the lease; a directory tied to neither is kept; test |
| R4 | M4 ledger | low | The prune trusts the runner's clock at write time; a clock stepped forward and back drops a nonce early | Said so in the register and the code |
| R5 | M4 ingest | low | The same-batch ordering was not tested as a security property | Test: a short completion and its heartbeats in one batch |
| R6 | M4 worker | low | The in-memory store's `heartbeat` checked nothing, so no test exercised a lost lease through renewal | The store refuses a renewal of a lease it no longer holds; test |
| R7 | M4 heartbeat | low | Any positive interval, so a readiness poll could flood the mailbox and the case's history | The interval is `0` or at least one second; the register names the version churn and the per-completion read cost |
| L1 | M5 cap | medium | The count and the insert were two store calls: concurrent submissions both found room | The store judges the cap with the insert under one lock (an advisory transaction lock on PostgreSQL, the store's lock in memory); race test |
| L2 | M7 provenance | medium | The provenance claimed reproducibility from any record saying so | The record must be about these images: platform, artifact version, source commit, a named builder, and a scan that did not rebuild; tests |
| L3 | M5 limiter | low/medium | Eviction past capacity forgot the oldest key even in debt, so a flood of fresh keys reset a limit | Eviction forgets only keys owing nothing; test |
| L4 | M7 toolchain | low | The command checks were substring checks; an `echo` satisfied them | The command must start a line; test |
| L5 | M7 record | low | The record took the first Dockerfile's snapshot date; an unknown BuildKit was recorded as such | Divergent dates and an unknown BuildKit refuse to make a claim |
| L6 | M7 Dockerfiles | low | An unmatched `sed` left the live mirror in place silently | Each build checks the rewrite matched and no live mirror remains |
| L7 | M5 contract | low | `429` was documented on the exempt probes | Removed there; tests |
| L8 | M5 budget | low | The budget reads every audit artifact of the case on each model request | Noted in the register (linear in the history, bounded by `RR-030`'s curve) |
| L9 | M7 | info | The trixie web image's proof was pending when the register said closed | Proven before this table was written |
| D1–D16 | docs | — | Sixteen stale or unbacked statements across both repositories (README, CONTRIBUTING, `compatibility.md`, `operations.md`, `performance.md`, the register, threat coverage, a runner comment, the error reference's quick table, the spec repo's record of the heartbeat decision) | Corrected, the spec repo's at close |

## Discoveries and follow-ups

- 2026-10-29 M1. Two test files with one basename (`tests/unit/test_workspace_format.py`,
  `tests/integration/test_workspace_format.py`) cannot be collected together without
  package files; the unit file is `test_workspace_format_rules.py`.
- 2026-10-29 M1. `oak export` read the current case before exporting, so the first
  export of an older format was refused by the read; the command now reads the format
  first and the case only when the format is current.
- 2026-10-29 M3. The benchmark's synthetic revisions reused their idempotency keys across
  calls, so a second growth step replayed the first's events as duplicates (308 events
  where 500 were asked); the key now carries the audit sequence.
- 2026-10-29 M3. `record_recreation` wrote an event naming no intent; on a case past
  interpretation the lineage check refuses that, so the event names the intent and the
  source record there, and still nothing on a draft case.
- 2026-10-29 M4. `FilesystemMailbox.read_messages` orders by file name, so a lease's
  completion came before its heartbeats and the lifecycle journeys ended on a heartbeat
  event; the ingest sort above fixed it.
- 2026-10-29 M4. The retention test first expected an old, ingested dispatch to survive a
  later run; it is exactly what the cleanup removes once it is no longer the newest.
- 2026-10-29 M5. `scripts/generate_openapi.py` writes the web client from a fixed source,
  so documenting `429` touched `openapi/oak.openapi.json` only; the compatibility checker
  flags removed responses, not added ones.
- 2026-10-29 M7. Docker Desktop's default builder refuses `rewrite-timestamp` with its
  containerd image store ("conflicts with unpack"); the buildx container driver, which the
  workflows use with the pinned BuildKit, exports a tarball the daemon loads, and works.
  The script takes `--builder` for it.
- 2026-10-29 M7. `uv sync` leaves `uv_cache.json` in the project's dist-info with the
  build's clock and a directory stamp; it was the one file that differed between two
  builds once the clock-stamped system files were gone.

## Self-review

(Empty until the work happens.)
