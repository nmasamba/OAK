<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S4-001–009: Architecture web workspace over the persistent control plane

## Status

- Owner/agent: Claude
- Started: 2026-08-18
- Last updated: 2026-08-18 13:40 BST
- State: in-progress
- Claimed tasks: `OAK-S4-001`–`OAK-S4-009`

## Outcome

A product owner, architect, or reviewer with no CLI access completes the public reference
decision in a browser against the local Compose stack: they open the workspace, review the
brief with facts, inferences, defaults, unknowns, and provenance visually and semantically
distinct, answer the ranked questions, compare candidate architectures including the
deliberately infeasible variant and its reasons, understand why `candidate-03` was selected,
review the assurance plan and compiled bundle with plan/approval/apply explicitly separated,
inspect the audit timeline, and download a canonical export whose digests match the CLI
export. The core flow passes keyboard-only navigation and automated accessibility checks,
and a browser end-to-end suite proves the journey, one denied transition, and one
interrupted operation using local Compose only.

## Context and invariants

Sprint 3 is merged to `main` at `c64a86f` and verified against the pinned PostgreSQL 17.6
Compose topology. The `/v1` REST workflow, durable Operations, worker, artifact/export
resources, generated OpenAPI, and typed client exist. The web application is a single-file
React 19 status shell showing version/health only. The nginx production proxy and the Vite
dev proxy forward only `/version`, `/healthz`, and `/readyz` — not `/v1`. The typed client
is emitted from a hand-maintained `CLIENT_SOURCE` literal in `scripts/generate_openapi.py`
and checked by `make openapi-compatibility`. There is no frontend test tooling of any kind
in the pnpm workspace.

The API has no list-design-cases endpoint and no audit/timeline read endpoint; both are
required by the workspace and must be added additively. The worker already maintains a
rebuildable `design-case-index` projection suitable for listing.

Governing requirements: `OAK-FR-CTL-001` (all interfaces operate the same versioned
DesignCase through shared application services; no interface bypasses policy transitions),
`OAK-NFR-UX-001` (P0: the UI MUST distinguish fact, inference, proposal, approval, policy
decision, and unknown), `OAK-NFR-UX-002` (explainability without private model reasoning),
and `OAK-NFR-SEC-001`. Accepted ADRs 0002, 0013, and 0014 govern the modular boundary, the
implementation stack, and interface parity. The skills.md "Workspace UI" recipe applies,
with the Interface adapter and accessibility/evidence add-ons.

Hard invariant from ADR-0014: the browser renders server-returned state, allowed actions,
and denials. It never computes lifecycle transitions, never fakes optimistic approval, and
`interface_origin` remains audit metadata, never authority. Briefs, case content, and
artifact payloads are untrusted data and are rendered inert (no HTML/script interpretation).

## Scope

### In

- Additive `GET /v1/design-cases` list endpoint over the existing projection with
  deterministic ordering and opaque cursor pagination, plus an additive audit/timeline read
  endpoint over existing transition/audit records. OpenAPI and client regeneration through
  the local compatibility gate for both.
- `/v1` forwarding in `deploy/nginx/default.conf` and `web/vite.config.ts` (same-origin
  proxy; no CORS added to the loopback-guarded API).
- Workspace shell: routing, case list/create/open, operation status polling, RFC-7807
  problem rendering, Idempotency-Key generation, ETag/If-Match concurrency handling with a
  visible stale-version recovery path.
- Brief and inference review, question/confirmation flow, candidate comparison, decision
  and assurance, bundle review, and audit/export screens per `OAK-S4-002`–`007`.
- Typed view models derived from the canonical JSON Schemas for case, intent, candidates,
  decision, assurance plan, and operations (replacing untyped `JsonObject` handling).
- Missing artifact client functions in the generated client.
- Accessibility built into each screen (keyboard, focus, semantic labels, contrast, reduced
  motion) with automated checks, plus a manual review pass.
- First frontend test tooling: component/a11y checks and a browser end-to-end suite driving
  the Compose stack, wired to new Make targets. `pnpm-workspace.yaml` build allowances are
  extended only for the reviewed test tooling.

### Out

- Runner dispatch, signing, approval, apply, rollback, destroy, secret resolution, or any
  target access. The compiled plan remains a draft, non-executing review artifact and the
  bundle screen presents apply as explicitly unavailable in Community.
- Enterprise authentication, user management, or any claim beyond the local actor mode.
- `.github` CI wiring, which remains explicitly deferred by user direction; all new gates
  are local Make targets.
- A chat or model-provider interface; interpretation remains the deterministic offline path.
- Changes to canonical schema meaning, semantic digests, or database schema. The projection
  and existing tables serve the new read endpoints.

## Contract and data changes

Both new REST resources are additive and read-only, keyed by tenant scope with
non-enumerating cross-tenant behavior, deterministic ordering, and opaque cursors,
following the Sprint 3 conventions. `openapi/oak.openapi.json`, the compatibility baseline
workflow, and the typed client are regenerated from source; `make openapi-compatibility`
must pass without a baseline reset. No database migration is expected; if listing requires
an index, it arrives as a new forward-only Alembic revision, never an edit to the baseline.

The client generation approach is a recorded decision for Milestone 1: extend the existing
`CLIENT_SOURCE` mechanism first (no new dependency), and re-evaluate adopting a real
generator before Milestone 4 if hand-maintenance proves error-prone; any switch must keep
the emitted client byte-reproducible from source.

## Milestones

### Milestone 1 — Shell, list endpoint, and `/v1` plumbing (`OAK-S4-001`)

- Work: implement the list and audit endpoints and their tests; regenerate OpenAPI/client;
  fix both proxies; build the routed shell with case list/create/open, operation polling,
  problem rendering, idempotency and If-Match conventions, and safe empty/loading/failed
  states; establish typed view models and the schema-derived type pipeline.
- Proof: through the web origin (`127.0.0.1:5173`) against Compose, a user creates a case,
  opens it, and watches an operation reach a terminal state; a stale If-Match produces the
  documented conflict recovery UI; `make check` and the compatibility gate pass.
- Rollback: endpoints are additive; the previous shell remains buildable from the prior
  commit; reverting the branch restores the status shell with no data impact.

### Milestone 2 — Review and confirmation (`OAK-S4-002`, `OAK-S4-003`)

- Work: brief/intake view; side-by-side fact/inference/default/unknown display with
  provenance and materiality, visually and semantically distinct per `OAK-NFR-UX-001`; the
  ranked questions (at most five) with accept/correct/reject/accept-risk actions, dependency
  impact reasons, and concurrency-conflict recovery.
- Proof: golden-fixture screens for the reference brief distinguish all claim classes with
  accessible semantics (not color alone); the confirmation flow reaches
  `ready_for_candidates` keyboard-only; a concurrent confirmation induces a 409 whose
  recovery path completes without data loss.
- Rollback: screens are additive routes; disabling the routes restores Milestone 1 behavior.

### Milestone 3 — Candidates and decision (`OAK-S4-004`, `OAK-S4-005`)

- Work: candidate comparison with topology, hard-constraint results, the simpler/non-AI
  baseline, objective ranges with units and calibration metadata, Pareto/frontier status,
  evidence, and rejected reasons with raw values always inspectable; generate/evaluate
  operation orchestration; selection with rationale entry; assurance plan display with
  controls, tests, owners, and gate blockers.
- Proof: the reference case shows all four variants including `candidate-04` infeasibility
  reasons; both 202 operations complete through the polling UI; selection and assurance
  reach `assurance_planned` with rationale and evidence visible per `OAK-NFR-UX-002`.
- Rollback: additive routes as above; no server change beyond Milestone 1 endpoints.

### Milestone 4 — Bundle, audit, and export (`OAK-S4-006`, `OAK-S4-007`)

- Work: add the missing artifact client functions; bundle review with normalized GitOps
  files, component lock, lifecycle plan, and explicit plan/approval/apply separation (apply
  shown as unavailable in Community); a semantic diff view computed from canonical
  artifacts (client-side unless a server endpoint is separately justified and recorded);
  audit lineage/timeline from the new endpoint; canonical export download.
- Proof: the compiled reference bundle renders with its lock and lifecycle plan; the
  runner plan displays as draft/unsigned with read-only operations; the timeline shows the
  audit chain for case `0.1.7`; the downloaded export's digests equal the CLI export for
  identical semantic inputs and times.
- Rollback: additive; export download uses the existing bounded endpoint.

### Milestone 5 — Accessibility evidence and browser end-to-end (`OAK-S4-008`, `OAK-S4-009`)

- Work: automated accessibility checks over the core flow plus a recorded manual review;
  browser end-to-end suite (tool selection recorded as a decision; Playwright preferred)
  driving the full reference journey against Compose, including one denied transition and
  one interrupted/cancelled operation; new Make targets; reduced-motion and responsive
  verification.
- Proof: the Sprint 4 exit demonstration — a reviewer with no CLI completes brief review
  through compiled plan keyboard-only, identifies inferred values and why `candidate-03`
  won, and exports the same canonical case as the CLI; automated a11y and browser suites
  pass locally against Compose.
- Rollback: test tooling is dev-only; removing the dev dependencies restores the prior
  workspace without production impact.

## Verification

- Python: endpoint unit/contract/integration tests for list and audit resources, including
  tenant non-enumeration, pagination determinism, and compatibility-gate runs. Existing
  integration assertions that count outbox events are updated deliberately alongside any
  event-emission change, never loosened silently.
- Web: typecheck/format/build gates; component tests for claim-class rendering, conflict
  recovery, and operation polling; automated accessibility checks; browser end-to-end
  against Compose including denied and interrupted paths.
- Repository: `make check`, `make audit`, `make sbom`, documentation policy scan,
  `.github`-unchanged check, and the Compose exit demonstration from a clean workspace.

## Security, privacy and authority review

Brief content, case fields, artifact payloads, and problem details are untrusted and are
rendered as inert text with bounded sizes; nothing from case content is interpreted as
markup, URL, or script. The web tier gains no authority: every mutation flows through the
same application services with server-side validation, and denials are displayed, not
recomputed. The same-origin proxy preserves the loopback posture; no CORS relaxation is
added. New read endpoints enforce tenant scope with non-enumerating behavior and safe
problem details. Logs and errors keep correlation IDs and stable codes, never source
bodies. No approval, signing, runner, secret, or target capability is introduced, and the
bundle screen states this explicitly.

## Operational and rollback plan

The web application remains stateless; all state stays in PostgreSQL and the artifact
store. API additions are additive and read-only, so rollback is redeploying the previous
images or reverting the branch. If a pagination index migration proves necessary it is
forward-only, with restore-forward as the documented recovery, consistent with Sprint 3.
The browser end-to-end suite runs against disposable Compose volumes and must leave no
project containers after teardown.

## Progress

- [x] 2026-08-18 13:20 BST Merged PR #5 (Sprint 3 closure docs), fast-forwarded `main` to
  `c64a86f`, and created `claude/sprint-4-web-workspace`.
- [x] 2026-08-18 13:40 BST Authored this plan from the Sprint 4 backlog, the Workspace UI
  recipe, requirements `OAK-FR-CTL-001`/`OAK-NFR-UX-001`/`OAK-NFR-UX-002`, ADRs 0002/0013/
  0014, and a full-repository readiness analysis; claimed `OAK-S4-001`–`009`.
- [ ] Milestone 1 — list/audit endpoints, proxy forwarding, workspace shell.
- [ ] Milestone 2 — brief/inference review and question/confirmation flow.
- [ ] Milestone 3 — candidate comparison, decision, and assurance screens.
- [ ] Milestone 4 — bundle review, audit timeline, and export download.
- [ ] Milestone 5 — accessibility evidence and Compose browser end-to-end.

## Decisions

- 2026-08-18 Use one plan for `OAK-S4-001`–`009` because the shell conventions, typed view
  models, and proxy plumbing established in Milestone 1 are load-bearing for every later
  screen and for the browser end-to-end exit.
- 2026-08-18 Fix same-origin `/v1` proxying instead of adding CORS to the loopback-guarded
  API.
- 2026-08-18 Extend the existing hand-maintained `CLIENT_SOURCE` client for the new
  endpoints in Milestone 1; re-evaluate real client generation before Milestone 4 and
  record the outcome here.
- 2026-08-18 Follow the established `<agent>/sprint-<n>-<short-name>` branch pattern as
  precedent (`claude/sprint-4-web-workspace`); no governance rule mandates it.
- Pending: browser end-to-end tool selection (Playwright preferred) with the exact
  `pnpm-workspace.yaml` build-allowance additions reviewed and recorded.

## Discoveries and follow-ups

- `tests/integration/test_persistent_api.py` asserts exact outbox counts and fixture
  versions; the new endpoints and any event changes must update those assertions
  deliberately as part of the same change.
- The local development host runs Node 22.17.1 while the workspace pins 24.18.0; the
  toolchain-consistency check compares documented pins with each other and the pinned Node
  runs in the web container image. Aligning the local runtime is desirable but not a
  Sprint 4 gate.
- The spec-repository root `STATUS.md` still describes Sprint 0 and predates this
  implementation repository's status file; updating it is outside this plan's scope.
