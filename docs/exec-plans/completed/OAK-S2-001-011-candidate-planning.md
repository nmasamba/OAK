<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S2-001–011: Compile a confirmed case into a deterministic review plan

## Status

- Owner/agent: Codex
- Started: 2026-08-17
- Last updated: 2026-08-17
- State: completed

## Outcome

A user can complete the public offline fixture and run:

```bash
oak candidates --output table
oak evaluate candidate-03 --output json
oak select candidate-03 --rationale-file decision.md
oak assure candidate-03 --output assurance/
oak plan candidate-03 --target examples/targets/local-fixture.yaml --output bundle/
```

The workspace records an immutable catalogue snapshot, four provider-neutral candidate graphs including a simpler baseline, deterministic feasibility and objective evidence, a selected decision, an assurance plan, a deployment bundle, and a draft typed `RunnerPlan`. Repeating compilation produces the same normalized semantic artifact and invokes no target executable.

## Context and invariants

Sprint 1 stores one versioned `DesignCase`, immutable content-addressed artifacts, and append-only audit events through `DesignCaseService` and `FileWorkspaceRepository`. The public confirmation fixture currently resolves three of five questions and therefore must be completed before candidate generation can honestly require `ready_for_candidates`.

This plan covers `OAK-S2-001` through `OAK-S2-011` together because catalogue eligibility, candidate feasibility, comparison, evaluation, selection, assurance, and compilation share dependency digests and one immutable lifecycle. Relevant requirements are `OAK-FR-CAT-001` through `OAK-FR-CAT-006`, `OAK-FR-ARC-001` through `OAK-FR-ARC-007`, `OAK-FR-CTL-006` and `OAK-FR-CTL-008`, `OAK-FR-DEP-001` through `OAK-FR-DEP-003`, `OAK-NFR-PERF-001`, `OAK-NFR-PORT-001` and `OAK-NFR-SEC-003`. ADRs 0001, 0004, 0005, 0008, 0009, 0011 and 0015 govern the implementation.

Hard constraints run before estimators and Pareto comparison. Unknown never passes. Catalogue and target inputs are untrusted and bounded. Candidate explanations expose rules and evidence, never private reasoning. `oak plan` may emit only typed, read-only planning operations; it cannot approve, sign, dispatch, execute, resolve secrets, or mutate a target.

## Scope

### In

- Bundled synthetic component manifests and provider-neutral pattern contracts.
- Bounded local catalogue and target-profile adapters.
- Content-digested catalogue snapshots with eligibility, licence and freshness decisions.
- Baseline, minimum, balanced (`candidate-03`) and high-assurance candidate graphs.
- Deterministic hard constraints, transparent objective ranges, Pareto frontier and sensitivity.
- Rule/evidence explanations, deterministic fixture evaluation results and immutable selection.
- Assurance plans, canonical review artifacts, deployment bundle and draft typed runner plan.
- Shared application operations, local CLI adapters, persistence/audit lineage and offline tests.

### Out

- CI/CD changes, REST/jobs/PostgreSQL, web UI, MCP, real benchmarks or model providers.
- Signing, approval, runner dispatch, target access, subprocess execution or any apply operation.
- Production component recommendations or live catalogue/network ingestion.

## Contract and data changes

Add canonical contracts for catalogue snapshots, architecture patterns, evaluation results, selection decisions, assurance plans and target profiles, plus public synthetic examples. Extend workspace artifact kinds and audit event types additively. Existing candidate, evaluation, bundle and runner-plan schemas remain compatible; richer deterministic metadata uses documented `oak.community/*` extensions where their current contracts do not expose a core field.

The CLI adds `candidates`, `evaluate`, `select`, `assure` and `plan`. Mutations retain expected-version and idempotency behavior. Existing file workspaces remain readable because manifest/schema changes are additive and the repository continues to validate prior artifact kinds. No database migration exists.

## Milestones

### Milestone 1 — Governed catalogue and candidate kernel

- Work: complete the public confirmation fixture; add pattern/snapshot contracts, curated synthetic manifests, safe loaders, eligibility policy, baseline/variant expansion, hard constraints, estimators, Pareto comparison and explanations.
- Proof: unit/contract tests reject incomplete, stale, restricted and poisoned manifests; prove unknown hard constraints fail closed, infeasible candidates never reach the frontier, and catalogue order does not change semantic results.
- Rollback: remove additive catalogue/contracts/compiler modules; no external state exists.

### Milestone 2 — Atomic candidate and evaluation use cases

- Work: generate candidates and evaluation contract through one application service and workspace transaction; evaluate deterministic fixtures into digest-linked results.
- Proof: integration tests cover state denial, expected-version conflict, retry convergence, candidate lookup, pass/fail/block outcomes and audit/reference lineage.
- Rollback: immutable artifacts may remain unreferenced if publication fails; the prior manifest remains authoritative.

### Milestone 3 — Selection and assurance lineage

- Work: record the selected candidate, owner/rationale/alternative reasons/dependency digests and create the required tests, controls, evidence, owners and gate blockers.
- Proof: unfeasible or unevaluated selection is denied; stale and duplicate mutations converge safely; assurance is bound to the selected digest and evaluation contract.
- Rollback: no target state exists; prior immutable case versions remain exportable.

### Milestone 4 — Non-executing bundle compiler and CLI

- Work: validate a bounded target profile; compile canonical review files, deployment bundle, semantic manifest and draft typed runner plan; expose the five Sprint 2 CLI commands and documentation.
- Proof: the exit journey works offline, `candidate-03` remains stable, two outputs contain byte-equal normalized semantic manifests, schemas reject command/shell fields, and no subprocess or target access occurs.
- Rollback: output directories are review artifacts only and may be removed; no runner job or external resource exists.

## Verification

- Schema meta-validation and valid/invalid/boundary fixtures for every new contract.
- Catalogue poisoning, freshness, licence, evidence and order-independence tests.
- Candidate hard-constraint, objective, Pareto, explanation and determinism tests.
- Application state, authorization context, expected-version, idempotency, audit and corruption tests.
- CLI happy/negative/offline flows plus clean-workspace semantic comparison.
- Static scan for command/shell fields and subprocess imports outside existing allowed boundaries.
- `make check`, `make build`, `make audit`, `make sbom`, documentation terminology scan and agent-ignore check.

## Security, privacy and authority review

Manifests, patterns, rationale files and target profiles are untrusted local inputs with symlink, size, type, YAML alias, depth and schema limits. Their text is data only and cannot select executable code. Eligibility and feasibility are deterministic; model output has no role. Canonical artifacts contain public/synthetic metadata and secret references only; the fixture requires no secrets.

The runner plan remains `draft`, contains no approval, and includes only typed inventory/validate/render/plan/verify operations with fixed adapter identity and read-only target permissions. The compiler does not import subprocess APIs, open network connections or contact a target. No output claims that a signature, approval, production readiness or observed benchmark exists.

## Operational and rollback plan

All mutations use the existing file-workspace lock and atomic manifest replacement. Compiler inputs are bundled and offline. Failed parsing, eligibility, constraint, evaluation or output publication leaves the current case unchanged. Output directories are written via a temporary sibling and renamed only after full validation. Existing Sprint 1 exports remain supported; there is no background process, database, remote resource or target mutation to roll back.

## Progress

- [x] 2026-08-17 Read repository status, Sprint 2, architecture, requirements, evaluation/interface/security contracts, work recipes and relevant ADRs.
- [x] 2026-08-17 Created `codex/sprint-2-candidate-planning` from Sprint 1 commit `41f3716`.
- [x] 2026-08-17 Implemented the governed catalogue, provider-neutral patterns, deterministic constraints, estimators, Pareto comparison, and explanations.
- [x] 2026-08-17 Implemented atomic candidate, evaluation, selection, assurance, and plan application operations with immutable lineage and denial/retry paths.
- [x] 2026-08-17 Implemented the non-executing bundle compiler, explicit target-profile preflight, five CLI commands, examples, and offline exit journey.
- [x] 2026-08-17 Completed repository verification and moved this plan to `completed/`.

## Decisions

- 2026-08-17 Keep all Sprint 2 tasks in one ExecPlan because their immutable artifacts and dependency digests form one lifecycle and exit demonstration.
- 2026-08-17 Use only synthetic, bundled catalogue data and existing dependencies; no live component discovery or new production dependency is required.
- 2026-08-17 Preserve `candidate-03` as the balanced fixture candidate and add an explicit simpler baseline.
- 2026-08-17 Represent metadata absent from the current candidate contract in namespaced Community extensions rather than silently changing the meaning of schema version `0.3.0`.
- 2026-08-17 Treat the explicit target profile as invocation data: bind its tenant, include it in the semantic digest, and compare its declared platform, capacity, and allowed operations with the candidate instead of inspecting the control-plane host.
- 2026-08-17 Deny a second non-idempotent evaluation of the same immutable candidate version; exact retries return the first result, while a new candidate version is required for a new evaluation artifact.

## Discoveries and follow-ups

- The Sprint 1 public answer fixture left `question.model-hardware` and `question.data-volume` open, so it could not reach the Sprint 2 lifecycle. The fixture now confirms explicit synthetic values and its assertions cover `ready_for_candidates`.
- The current runner-plan contract requires signature and verification-policy references even for a draft. Compilation references explicit deterministic `not_signed` and draft-verification artifacts and keeps plan status `draft`; it does not fabricate an approval or usable signature.
- Hatchling's editable build backend needs `editables` while rebuilding the local environment without build isolation. Installing the already-cached build helper allowed the pinned offline sync to rebuild `0.4.0.dev4`; it was not added as an application dependency.

## Completion evidence

- `make bootstrap`, `make check`, `make build`, `make audit`, and `make sbom` completed. The full gate reported 205 unit/contract, 21 integration, and 7 end-to-end tests.
- A clean offline wheel installation resolved 25 bundled schemas, three synthetic manifests, and four patterns, then completed init, design, confirm, candidates, evaluate, select, assure, plan, and export at case `0.1.6`.
- The clean-workspace e2e fixture produced byte-equal semantic manifests, retained the simpler baseline, selected stable `candidate-03`, rejected the accelerator-unknown candidate, and emitted a draft five-operation runner plan without contacting a target.
- Negative tests cover poisoned/incomplete/stale/restricted catalogue data, malformed patterns and targets, hard unknowns, infeasible/unevaluated selection, immutable re-evaluation, stale versions, retries, tenant mismatch, missing operation authority, and insufficient target capacity.
- Documentation and repository hygiene scans found no prohibited product references, secrets, agent files, or CI/CD changes.
