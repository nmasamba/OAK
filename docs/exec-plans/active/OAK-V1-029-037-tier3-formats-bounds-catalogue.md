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
- Last updated: 2026-10-29 (M1, the workspace format migration)
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
- `OAK-V1-030`: `deployment-bundle.json` gains the assurance-plan digest edge (a new field,
  so every newly compiled bundle's digest moves; this is Q1's move); `oak validate bundle`
  gains the check and the "unbound" report for older bundles.
- `OAK-V1-031`: the catalogue snapshot records provenance per entry (curated, or an activated
  extension with its pack digest and signer), which moves the snapshot digest and so every
  compiled artifact (Q1's move, in the same milestone); `oak extensions activate` keeps its
  surface, and an activated component or pattern pack now reaches `compile_catalogue` when,
  and only when, its signature verifies against the trust directory; the register says
  which `RR-004` clause closed.
- `OAK-V1-032`: no contract change; a cache inside the file adapter and the measured curve.
- `OAK-V1-033`: new `OAK_RUNNER_*` retention rows; a lease-extension method on the operation
  store port (and the in-memory store); the nonce ledger's shape may gain an expiry per
  nonce (a runner-home file, not a canonical document).
- `OAK-V1-034`: new `OAK_*` rows for every limit; `429` responses on existing operations
  (an additive response code, listed as unreleased in the OpenAPI compatibility test);
  new `OAK-*` codes for the limits; the log allowlist decides what of a client address may
  be logged.
- `OAK-V1-035`: build-time only; the release evidence records the snapshot date and the
  BuildKit version.
- `OAK-V1-036`: a new audit event a server writes on restore (an existing or additive event
  type), with `interface_origin: import`.

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
- **M3, the cache.** Keyed on the bytes it skips work for; never consulted when a mutation
  is validated; object reads keep verifying.
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
  that migrated, and the rewrite rule. Unit and contract suites: 1,355 passed.

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
- 2026-10-29 M0. **Task numbering.** `OAK-V1-029` to `-036` are A1 to A8 in the prompt's
  order (migration, bundle edge, catalogue, reads, soak, budgets, images, restore) and
  `OAK-V1-037` is the review; the milestones run A1, then A2 with A3, then A4, A5, A6, A8,
  A7, the review, because the migration must exist before anything changes a stored shape,
  the digests move once, and the images need Docker and the longest CI runs.

## Discoveries and follow-ups

- 2026-10-29 M1. Two test files with one basename (`tests/unit/test_workspace_format.py`,
  `tests/integration/test_workspace_format.py`) cannot be collected together without
  package files; the unit file is `test_workspace_format_rules.py`.
- 2026-10-29 M1. `oak export` read the current case before exporting, so the first
  export of an older format was refused by the read; the command now reads the format
  first and the case only when the format is current.

## Self-review

(Empty until the work happens.)
