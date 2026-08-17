<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S1-001–010: Complete the offline local DesignCase journey

## Status

- Owner/agent: Codex
- Started: 2026-08-17
- Last updated: 2026-08-17
- State: complete

## Outcome

A user can initialize a local workspace, ingest the public structured brief without network access, review a schema-valid typed intent and no more than five deterministic questions, confirm those questions idempotently, and export/import the complete digest-verified workspace.

The observable journey is:

```bash
oak init /tmp/oak-demo
cd /tmp/oak-demo
oak design /path/to/examples/briefs/public-manual-qa.yaml --output yaml
oak questions --output json
oak confirm --answers /path/to/examples/briefs/public-manual-qa-answers.yaml
oak export --output ./case-export/
```

Repeating `oak confirm` with the same answers produces no additional case version or audit event. The journey works with public network access disabled.

## Context and invariants

`DesignCase` is the shared aggregate and indexes immutable artifacts by version and digest. The local workspace is the Sprint 1 repository implementation; later interfaces must call the same application services. Raw brief content is untrusted and remains separate from accepted claims. The deterministic interpreter is authoritative only for mechanical mapping and analysis; an optional model can propose structured values but cannot accept claims or bypass confirmation.

This plan covers `OAK-S1-001` through `OAK-S1-010` together because repository transactions, immutable case versions, source quarantine, intent versions, confirmation idempotency, audit lineage, CLI output, and import/export form one acceptance journey and cannot be proved honestly as isolated files.

Relevant requirements are `OAK-FR-CTL-001`, `OAK-FR-CTL-003`, `OAK-FR-CTL-008`, `OAK-FR-INT-001` through `OAK-FR-INT-006`, `OAK-NFR-REL-001`, `OAK-NFR-REL-002`, `OAK-NFR-SEC-003`, and `OAK-NFR-PORT-001`. Accepted ADRs 0001, 0008, and 0014 govern typed state, append-only audit, and interface parity.

## Scope

### In

- Atomic local workspace manifest, lock, content-addressed object store, expected-version and idempotency records.
- Canonical source-record, workspace-manifest, and audit-event contracts with public synthetic examples.
- Immutable `DesignCase` lifecycle rules and append-only audit linkage.
- Bounded YAML/JSON/Markdown/text intake with path, Unicode, type, size, depth, alias, and regular-file checks.
- Deterministic structured interpretation, provider-neutral proposal port, deterministic fake adapter, contradiction/unknown findings, and ranked questions.
- Confirmation decisions that create successor intent/case versions and preserve provenance.
- Local CLI commands for init, design, questions, confirm, export, and import with stable structured output and exit behavior.
- Positive, negative, concurrency, retry, atomic-failure, import/export, provider-outage, and adversarial tests.

### Out

- Candidate generation, evaluation, selection, assurance, or bundle compilation.
- Network APIs, PostgreSQL persistence, web workspace flows, MCP, signing, runner dispatch, secrets, or target mutation.
- A real model-provider adapter or mandatory hosted service.

## Contract and data changes

Add versioned JSON Schemas and examples for the local workspace manifest, quarantined source record, and audit event. Existing `DesignCase` and `SystemIntentSpec` contracts remain authoritative. Workspace state lives under `.oak/manifest.json`; immutable bytes live under `.oak/objects/sha256/`. Export reproduces that manifest and object set after digest and schema validation. Import accepts only a new workspace and validates every indexed object before publishing it atomically.

The new CLI commands are additive. Structured data goes to stdout and diagnostics to stderr. Mutations carry local actor/tenant/origin, expected version, correlation, and deterministic idempotency context. No prior persisted Community workspace exists, so there is no migration; schema versions and import rejection behavior are documented.

## Milestones

### Milestone 1 — Atomic workspace and aggregate

- Work: add canonical workspace/source/audit contracts, immutable domain values and lifecycle transitions, repository port, file adapter, locking, atomic manifest replacement, content addressing, expected-version and idempotency enforcement.
- Proof: contract and repository tests cover clean initialization, retry convergence, stale writes, lock serialization, corrupted objects, injected replace failure, and all allowed/denied lifecycle transitions.
- Rollback: remove the additive contracts and local adapter; no external store or migration exists.

### Milestone 2 — Safe intake and deterministic interpretation

- Work: add bounded intake normalization, structured/text parsing, deterministic intent mapping with complete scalar provenance, optional proposal port/fake adapter, stable findings, and five-question ranking.
- Proof: the public brief yields a valid intent; fixed input/clock yields byte-identical canonical output; malformed, oversized, aliased, deeply nested, Unicode-confused, symlinked, and provider-outage cases fail safely without a manifest mutation.
- Rollback: remove the interpreter/application commands; quarantined unreferenced content-addressed objects are harmless and may be deleted with the workspace.

### Milestone 3 — Confirmation and audit lineage

- Work: validate confirmation input, apply confirm/correct/reject/accept-risk decisions, create successor intent/case/audit objects, and bind retry behavior to normalized input.
- Proof: all decision kinds and invalid answers are tested; stale expected version fails; an identical retry returns the first result and adds no event; reusing a key with different input conflicts.
- Rollback: existing immutable versions remain readable; moving the manifest pointer back is a local recovery operation documented as development-only.

### Milestone 4 — CLI and portable export/import

- Work: expose the complete local CLI journey, provider-neutral JSON/YAML output, workspace discovery, digest-verified atomic export/import, help, documentation, and end-to-end/adversarial coverage.
- Proof: run the documented commands in fresh temporary directories with network disabled, validate the export, import it into another directory, and compare current case, intent, artifact, and audit digests.
- Rollback: commands are additive; exported data remains plain JSON/YAML/raw source and can be inspected without OAK.

## Verification

- Schema meta-validation, valid public examples, invalid and prior-version rejection.
- Domain transition matrix and immutable successor tests.
- Repository atomicity, expected-version, idempotency, locking, corruption, export/import, and failure-injection tests.
- Provenance coverage, deterministic interpretation, contradiction/unknown/question ordering, and malformed optional-proposal tests.
- CLI happy path, stable error/exit paths, retry behavior, offline execution, and exported artifact validation.
- `make check`, `make build`, `make audit`, documentation terminology scan, agent-ignore check, and staged diff review.

## Security, privacy and authority review

Briefs and import directories are untrusted. Intake is local, bounded, normalized, and rejected before publication for unsafe paths, symlinks, unsupported media, excessive size/depth/nodes, aliases, invalid Unicode, or malformed structured content. Raw brief bytes are quarantined separately and never treated as instructions. Canonical claims require schema validation and retain source classification. Optional model failure creates no fabricated state. Errors and audit records contain safe identifiers and digests, not raw brief content.

The local actor and tenant are explicit metadata. `interface_origin` grants no authority. There is no approval, signing, runner, secret, subprocess, network, or target-mutation path in this plan.

## Operational and rollback plan

All state is local to one `.oak` directory. Object writes precede one atomic manifest replacement, so a crash can leave only unreferenced immutable objects; the previous manifest remains authoritative. The lock and expected-version check prevent lost updates. Export uses a temporary sibling directory and rename. Import never overwrites an initialized workspace. Removing the workspace removes all Sprint 1 state; no background process or remote resource exists.

## Progress

- [x] 2026-08-17 Synced merged Sprint 0 `main`, read the active sprint, contracts, requirements, accepted ADRs, security invariants, interface contract, testing strategy, and matching work recipes.
- [x] 2026-08-17 Implemented Milestone 1: canonical workspace/source/audit contracts, immutable aggregate transitions, atomic file repository, locking, expected versions, idempotency, and corruption checks.
- [x] 2026-08-17 Implemented Milestone 2: bounded intake, deterministic interpretation, complete scalar provenance, stable analysis, ranked questions, and optional proposal failure boundaries.
- [x] 2026-08-17 Implemented Milestone 3: typed confirmation decisions, immutable successors, audit linkage, stale-write rejection, and convergent retries.
- [x] 2026-08-17 Implemented Milestone 4: local CLI journey, workspace discovery, structured output, atomic digest-verified portability, installed-wheel schemas, documentation, and black-box coverage.
- [x] 2026-08-17 Completed repository verification and moved this plan to `completed/`.

## Decisions

- 2026-08-17 Cover all Sprint 1 tasks in one plan because the exit demonstration requires one atomic lineage across intake, intent, confirmation, audit, and portable storage.
- 2026-08-17 Use only the standard library plus already locked schema/YAML dependencies; no new production dependency is justified.
- 2026-08-17 Keep raw source bytes content-addressed and separate from canonical source metadata and intent claims.
- 2026-08-17 Derive the default CLI retry key from the normalized input digest so an identical invocation converges without requiring caller-managed state.
- 2026-08-17 Bundle canonical schemas in the Python wheel so local case commands retain contract validation outside a source checkout.

## Discoveries and follow-ups

- The existing public answers fixture supplies exactly three explicit confirmation decisions; deterministic analysis may add at most two higher-value unknown questions so the five-question limit remains observable.
- Artifact references do not carry an explicit kind. The repository therefore verifies reference metadata against the manifest index and enforces the expected kind for current-case and audit/idempotency pointers.
- Final integrity review found that canonical references must retain optional URIs and that portable manifests need relational validation in addition to per-object digests. Aggregate round-trips now preserve every schema reference, while export/import cross-check audit order, tenant, current case, intent/source lineage, source size, and retry results.

## Completion evidence

- `make check` passed with 183 unit/contract, 18 integration, and 6 end-to-end tests plus formatting, lint, dependency boundaries, repository hygiene, strict Python/TypeScript types, generated contracts, and the production web build.
- `make build` produced the source archive, Python wheel, and web bundle. An isolated target install proved that the wheel resolves all 18 bundled canonical schemas outside the source checkout.
- `make audit` reported no known Python or web dependency vulnerabilities; `make sbom` generated the ignored reproducible development SBOM.
- The installed-wheel exit demonstration initialized, interpreted, questioned, confirmed, retried, exported, and imported the public fixture. The retry retained case `0.1.1`; source and imported manifests were byte-identical with two workspace revisions, two audit events, and two idempotency records.
- The documentation terminology scan and agent-ignore checks passed. No delivery-pipeline behavior was changed during this sprint.
