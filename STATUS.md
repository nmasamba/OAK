<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build status

- **Updated:** 2026-10-29
- **Repository version:** `0.9.0`
- **Phase:** **Tier 3, Batch A** (`OAK-V1-029`–`037`: the workspace format migration (`RR-017`), the bundle's assurance-plan edge (`RR-008`), the catalogue boundary (`RR-025`, with `RR-004`'s catalogue clause), bounded workspace reads (`RR-030`), runner and worker soak limits (`RR-031`), budgets and rate limits (`RR-024`, with `RR-041`), reproducible images (`RR-006`) and Tier 2's restore follow-up), directed by the owner on 2026-10-29 from the original spec repo's `TIER-3-PROMPT.md` after the owner moved Tier 3 of the 2026-10-23 ranking ahead of 1.0, is **in progress** on branch `tier3-formats` off `origin/main` at `e8f98da`; it bumps no version, cuts no tag, signs nothing and publishes nothing. The owner's kickoff answers (2026-10-29): **Q0** Batch A, then Batch B, both before 1.0, and Batch C's Sprint 15 before 1.0 so that 1.0 can promise that a reviewed researched design is selectable; the PPTX, report tools over MCP, metrics, web unit tests and the PDF's structure tree after 1.0 unless one turns out cheap; **Q1** one recorded move of the four reference digests before 1.0, in the one milestone that lands A2 and A3 together, with the goldens regenerated and the move written into the changelog and `compatibility.md`, and `RR-004`'s catalogue-feed clause joins: an activated component-manifest or architecture-pattern extension feeds the compiler's catalogue only when its pack is signed by an identity in the operator's trust anchors, with the provenance recorded in the snapshot; **Q2** budgets on by default, generous, every value configurable, and `RR-041` joins as a per-case daily count of billable model requests; **Q3** pin the images' package snapshots by date, the date moving at each release. Batch B (hardware scanning, then native installation) and Batch C's Sprint 15 follow, each from the merged `main` with its own kickoff, each merge the owner's. The **pre-1.0 assurance batch** (`OAK-V1-021`–`028`, Tier 2 of the owner's cost-benefit ranking of the backlog), directed by the owner on 2026-10-28 (the browser suite and a second platform in CI, a cut runner journal noticed, application logging, a local case moved onto a server, a Unicode PDF, and release artifacts the owner can sign), was completed on branch `pre-v1-assurance` off `origin/main` at `ab101ab` and merged by the owner as PR #41 (https://github.com/nmasamba/OAK/pull/41, merge commit `e8f98da`, 2026-10-29). It closes `RR-014` and `RR-054` and the browser clause of `RR-021`, the logging clause of `RR-015` and the Unicode clause of `RR-046`, mitigates `RR-005` until the owner pins a release key, and moves no reference digest and no report golden; its closing adversarial review's 21 distinct findings (23 reported, three of them one defect seen twice, and one found while fixing) were all confirmed and fixed, with a test where they were code; a second, wider review of the finished batch confirmed 57 more, and a review of those fixes 25 more, all fixed the same way. It bumps no version, cuts no tag, signs nothing and publishes nothing. The owner's kickoff answers: Q1 an owner-held SSH key signs `SHA256SUMS`; Q2 a bundled font for Latin, Greek and Cyrillic (reversing Sprint 13's K5), the PDF's tagging left open for a pass after 1.0; Q3 a local export is re-created on a server from its brief and confirmed answers; Q4 JSON log lines on stderr at `INFO` with the access log on; Q5 both a macOS and an arm64 Linux CI job. The owner deferred Tier 1's owner half (the K2 rename, the harness-list review, the `@role` names) until the 1.0 launch. The **owner's follow-ups to the pre-1.0 engineering batch** (`OAK-V1-017`–`020`), directed by the owner on 2026-10-26 after PR #39 merged (REST and MCP answer `OAK-CASE-NOT-FOUND` for a case the server does not hold, the release workflow's gate runs the PostgreSQL suites, and the original spec repo's dormant workflow is pinned), were completed on branch `pre-v1-follow-ups` off `origin/main` at `2d5ec62` and merged by the owner as PR #40 (https://github.com/nmasamba/OAK/pull/40, merge commit `ab101ab`, 2026-10-28). They change one error answer on REST and MCP, lift the development-only `filelock` and `msgpack` for four advisories, move no digest, and bump no version, cut no tag and publish nothing. The **pre-1.0 engineering batch** (`OAK-V1-008`–`016`), directed by the owner on 2026-10-23 after the readiness pass was merged (the cheap, high-value items from the top of the owner's cost-benefit ranking of the backlog: CI runs the PostgreSQL suites, Node-24 actions pinned by commit SHA, the runner's trust boundary narrowed, readiness that checks the schema revision, a read-only `oak keys show`, CLI and Report-screen polish, and reportlab's settings pinned), was completed on branch `pre-v1-polish` off `origin/main` at `885c96a` and merged by the owner as PR #39 (https://github.com/nmasamba/OAK/pull/39, merge commit `2d5ec62`, 2026-10-26). It closes `RR-002`, `RR-016`, `RR-018`, `RR-019`, `RR-027` and `RR-033`, changes no contract and moves no digest, and it bumps no version, cuts no tag and publishes nothing. The 1.0 readiness pass (`OAK-V1-001`–`007`) is **merged** as PR #38 (merge commit `885c96a`, 2026-10-23). the **1.0 readiness pass** (`OAK-V1-001`–`007`), directed by the owner on 2026-10-23 ("ensure coherence of documentation, then thoroughly review and polish functionality in anticipation of publicly releasing version 1.0"), was completed on branch `release-1.0-readiness` off `origin/main` at `a479780` and merged by the owner as PR #38 (https://github.com/nmasamba/OAK/pull/38). It made the documentation of both repositories coherent (86 findings), ran every documented journey, and fixed or documented the 64 defects four independent finders reproduced (8 high, among them forged runner completions believed by `oak ingest`, a revocation that a deleted notice could undo, and HTML served from an imported export); it bumps no version, cuts no tag and publishes nothing, and its plan's readiness list names what only the owner can do to cut 1.0. Sprint 14 (`OAK-S14-001`–`007`, research at the point of design, authorized 2026-10-21) is **complete and merged** by the owner as PR #37 (https://github.com/nmasamba/OAK/pull/37, merge commit `a479780`, 2026-10-22) from branch `sprint-14-research` off `origin/main` at `671d4a4`: on the user's consent, for one case before its candidates are generated, OAK reads a fixed set of public sources (the Hugging Face Hub and router, and GitHub's REST API, all anonymously) for open models and harnesses that fit the confirmed intent, turns each into an untrusted component proposal checked by deterministic gates, and generates candidates from a digested snapshot that merges the curated entries with the passing researched ones, so a newly released model or harness surfaces as an alternative design with its source, its date and how each claim is backed; the default path stays deterministic and offline. The owner's kickoff answers: Q1 Hugging Face and GitHub, anonymous, within a request budget and a 24-hour cache; Q2 two tiers (trusted namespaces and an owner-reviewed harness list pass on their own; anything else is unvetted until the user records a review); Q3 per run at `ready_for_candidates` only, behind a consent card that names every host and term, off by default; Q4 first "selectable once reviewed", which conflicts with the prompt's invariants, and on the follow-up question **the compare-only rule now and selection next sprint**: unknown estimates in the compiler, at most two researched designs from `candidate-05` labelled like "Balanced, new", each shown with its estimates and every reason, and a researched design whose only failures are pending reviews or unknown values joins the frontier comparison but stays unselectable. Sprint 13 (`OAK-S13-001`–`007`, the architecture report, authorized 2026-10-16) is **complete and merged** as PR #36 (https://github.com/nmasamba/OAK/pull/36, merge commit `671d4a4`, 2026-10-19) from branch `sprint-13-architecture-report` off `origin/main` at `6142270`: a decision deck about one design case, composed only from the case's records, recorded beside the case by an explicit command (no status change), read on a Report screen, and downloaded as a PDF or as the report document. The owner's kickoff answers: K1 record in the case; K2 server-side rendering, narrowed after the dependency review to **PDF only** (`python-pptx` failed maintenance, so PPTX is a follow-up); K3 an opt-in model mode adding one checked note per main slide, labelled "Proposed by model"; K4 recordable from `candidate_selected`; K5 the print palette with no font file; K6 MCP unchanged. The closing review's 14 surviving findings are fixed. Sprint 12 (`OAK-S12-001`–`007`, authorized 2026-10-15) is **complete and merged** as PR #34 (https://github.com/nmasamba/OAK/pull/34, merge commit `6142270`, 2026-10-15) from branch `sprint-12-instrument-ui` off `50f1673`: the web workspace rebuilt in direction A ("Instrument") — conversation first, symbols over text, tactile, with one-tap downloads of the brief, each design and the final architecture — plus one read-only REST route for the final architecture document (`json` or `yaml`), with no boundary moved; the owner answered the four kickoff questions with the recommended option each time (K1 the route, K2 the variant rename stays a separate later change, K3 dark theme only, K4 today's routes kept). `0.9.0` is **published as a GitHub Release** (2026-10-01, https://github.com/nmasamba/OAK/releases/tag/v0.9.0) and approved by `nmasamba` in all three roles the same day (`OAK-S11-009`). It was cut at the owner's instruction on 2026-09-30, with the version touch-list, the changelog section, a fresh image scan, the release build, a clean-room rehearsal and `docs/release/0.9.0/release-decision.md`. `v0.9.0` was tagged on 2026-10-01 on `ff7d4df`, minutes before the signatures. The published wheel is byte-identical to the approved build. Sprint 11 (`OAK-S11-001`–`008`, authorized 2026-09-29) is merged as PR #30 (`cb28160`): after a user has approved the architecture and the installation step separately, OAK installs the chosen candidate's topology on the acknowledged non-production local target as network-isolated containers (started and smoke-tested only where the profile acknowledges it), and `oak observe` records what was observed beside what was predicted; `oak architecture` lets a user stop at the design. Sprint 10 (`OAK-S10-001`–`008`) is merged as PR #22 (`052211e`). Sprint 9 (`OAK-S9-001`–`009`) is merged as PR #21 (`88fa876`). `0.8.0` is tagged `v0.8.0` and was approved on 2026-09-23, and was never published: `0.9.0` superseded it. `0.7.1` was approved by `nmasamba` on 2026-08-27 and published as a GitHub Release on 2026-09-03, and is the release before `0.9.0`
- **Completed plans:** `docs/exec-plans/completed/OAK-S0-001-009-walking-skeleton.md`, `docs/exec-plans/completed/OAK-S1-001-010-local-design-case.md`, `docs/exec-plans/completed/OAK-S2-001-011-candidate-planning.md`, `docs/exec-plans/completed/OAK-S3-001-009-persistent-rest-jobs.md`, `docs/exec-plans/completed/OAK-S4-001-009-web-workspace.md`, `docs/exec-plans/completed/OAK-S5-001-011-signed-runner.md`, `docs/exec-plans/completed/OAK-S6-001-008-policy-adapter-sdk.md`, `docs/exec-plans/completed/OAK-S7-001-008-mcp-portal-interface-parity.md`, `docs/exec-plans/completed/OAK-S8-001-009-community-release-hardening.md`, `docs/exec-plans/completed/OAK-PL-001-007-pre-launch-hardening.md`, `docs/exec-plans/completed/OAK-FS-001-003-final-sweep.md`, `docs/exec-plans/completed/OAK-S9-001-009-model-provider-intake.md`, `docs/exec-plans/completed/OAK-S10-001-008-huggingface-only-modes.md`, `docs/exec-plans/completed/OAK-S11-001-008-install-test-observe.md`, `docs/exec-plans/completed/OAK-S12-001-007-instrument-ui.md`, `docs/exec-plans/completed/OAK-S13-001-007-architecture-report.md`, `docs/exec-plans/completed/OAK-S14-001-007-research-at-the-point-of-design.md`, `docs/exec-plans/completed/OAK-V1-001-007-release-1.0-readiness.md`, `docs/exec-plans/completed/OAK-V1-008-016-pre-1.0-engineering.md`, `docs/exec-plans/completed/OAK-V1-017-020-owner-follow-ups.md`, and `docs/exec-plans/completed/OAK-V1-021-028-pre-1.0-assurance.md`
- **Active plan:** `docs/exec-plans/active/OAK-V1-029-037-tier3-formats-bounds-catalogue.md` (Tier 3, Batch A). The pre-1.0 assurance batch's plan is `docs/exec-plans/completed/OAK-V1-021-028-pre-1.0-assurance.md` (its decisions, the closing review's findings table and the follow-up on restored history). The owner's follow-ups to the pre-1.0 engineering batch are in `docs/exec-plans/completed/OAK-V1-017-020-owner-follow-ups.md`. The pre-1.0 engineering batch's plan is `docs/exec-plans/completed/OAK-V1-008-016-pre-1.0-engineering.md` (its decisions, mutation checks and follow-ups). The 1.0 readiness pass's plan is `docs/exec-plans/completed/OAK-V1-001-007-release-1.0-readiness.md` (its findings table, decisions and the 1.0 readiness list). Sprint 14's plan is `docs/exec-plans/completed/OAK-S14-001-007-research-at-the-point-of-design.md` (with its closing review table and retro). Sprint 13's plan is `docs/exec-plans/completed/OAK-S13-001-007-architecture-report.md`; Sprint 12's is `docs/exec-plans/completed/OAK-S12-001-007-instrument-ui.md`
- **Next task:** `OAK-V1-029`–`037`, Tier 3's Batch A in the active plan, then its PR, whose merge is the owner's; then, per the owner's Q0 answer of 2026-10-29, Batch B (hardware scanning, then native installation) and Batch C's Sprint 15 (a reviewed researched design becomes selectable), each branched from the merged `main` and launched with its own kickoff questions. After those, the owner's: when cutting 1.0, pin the release key in `keys/allowed_signers` and sign `SHA256SUMS` (`docs/release-process.md`, Signing); then the 1.0 readiness list in the 1.0 readiness pass's completed plan (the version, what 1.0 promises, the decision record and its signatures over 54 register entries, the release evidence, publication, and the open product decisions). Still with the owner: the review of the draft harness list `catalogue/research/harness-repositories.yaml` (`reviewed_by` and `reviewed_at` are null until then, so every harness is unvetted). The owner's order of 2026-10-16 (Sprint 15, then native installation and hardware scanning) is superseded by the Q0 order above: Batch B runs before Sprint 15, because the scan proposes the target the install goes onto and Sprint 15 needs the installation path and the hardware class. The rest of Batch C (the PPTX, report tools over MCP, the external review package, metrics, web unit tests and the PDF's structure tree) comes after 1.0 unless one turns out cheap. Still open from Sprint 12's kickoff: the product variant rename (K2), a light theme (K3) and one thread route (K4). PyPI and a container registry remain separate owner decisions. What remains after the release, each needing an owner decision: observing cost, latency, quality and energy under a representative workload (every calibration row is `unknown` today), a web observation view, and evidence-backed change proposals.

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
| `OAK-S8-003` | complete | Threat-model coverage index, dependency and container scans, secret/log and runner review, residual-risk register |
| `OAK-S8-004` | complete | Reproducible artifacts with SBOM, licence inventory, checksums and tested verification |
| `OAK-S8-005` | complete | Provenance-stamped performance and soak measurements |
| `OAK-S8-006` | complete | Operator documentation from install through uninstall |
| `OAK-S8-007` | complete | Contributor documentation and the release process |
| `OAK-S8-008` | complete | Clean-room release-candidate rehearsal with archived evidence |
| `OAK-S8-009` | complete | Evidence, P0 proposal and known limitations published; approved by `nmasamba` in all three roles, 2026-08-22, with RR-001/RR-003 accepted only for a local-first release |
| `OAK-PL-001` | complete | Unpublished `0.7.0` re-cut as `0.7.1` with a draft (unsigned) decision record under `docs/release/0.7.1/`, covered by the residual-risk count gate |
| `OAK-PL-002` | complete | pnpm provisions the pinned Node (`devEngines.runtime`); `make toolchain-check` fatally compares the running Python and pnpm-provisioned Node against the pins (`RR-034` closed) |
| `OAK-PL-003` | complete | Web image runs unprivileged (uid 101, verified in the running container); Compose applies `cap_drop`/`no-new-privileges`/read-only/limits per service; nginx, postgres and build-stage pins join the drift check (`RR-037` closed) |
| `OAK-PL-004` | complete | Revocation notices signed in the `approver` role, inventoried by a signed monotonically sequenced manifest, and verified against pinned anchors; the revocation channel fails closed against deletion, tampering and rollback (`OAK-RUNNER-REVOCATION`; `RR-001` closed) |
| `OAK-PL-005` | complete | Post-create resolved-digest verification (`OAK-RUNNER-IMAGE`) and target-profile registry allowlist (`OAK-RUNNER-REGISTRY`); TM-08 direct (`RR-003` closed) |
| `OAK-PL-006` | complete | Verification policy derived from the target and enforced per requested kind (`OAK-RUNNER-POLICY`); the one sanctioned digest migration, recorded in `CHANGELOG.md` (`RR-032`/`RR-011` closed); signed examples regenerated and cryptographically gated |
| `OAK-PL-007` | complete | Per-image CycloneDX SBOMs and unsigned provenance from `make scan-images` and the release workflow; `0.7.1` rescan: zero fixable findings, web image clean at every severity (`RR-038` closed, `RR-036` re-confirmed) |
| `OAK-FS-001` | complete | AI-vendor names neutralized in the completed plans' `Owner/agent:` descriptions (agent-versus-human distinction preserved); historical branch identifiers kept as repository facts; the merged agent-named remote branches deleted; document-policy gates extended to `.html`/`.mjs` |
| `OAK-FS-002` | complete | Illustrated user manual at `docs/manual/` — authoritative HTML source, rendered PDF, live-capture screenshot spec — its chapter 3 and chapter 5 commands verified by running the CLI and signed-runner journeys end to end against the tree, with the expected output captured from those runs |
| `OAK-FS-003` | complete | Post-merge truth pass: both repositories' status documents, `CHANGELOG.md`, and the `0.7.1` release-decision draft state the merged reality; `OAK_MANUAL_SCREENS` documented and pinned by the configuration-reference gate |
| `OAK-S9-001` | complete | Reference digests and deterministic intent bytes pinned by a test; provider state isolated in tests; secret-scan, boundary and egress gates widened before any adapter exists |
| `OAK-S9-002` | complete | Loopback hardening (Host/Origin/Fetch-Metadata) and a per-process capability token for credential, discovery, selection and model-mode interpretation |
| `OAK-S9-003` | complete | Keychain and 0600 file credential stores, closed model-configuration schema, `oak models` local-only command |
| `OAK-S9-004` | complete | Proposal merge inside `interpret` with `model_proposed` provenance, per-section confirmation questions, all interfaces plumbed (`--interpreter`, REST query + token, MCP opt-in) and a byte-identical deterministic path |
| `OAK-S9-005` | complete | Standard-library transport with a fixed egress allowlist, seven provider profiles (narrowed to two in Sprint 10), hosted interpreter, Hugging Face free-model lookup, egress gates rewritten, `TM-13` direct, `RR-039`/`RR-041` recorded |
| `OAK-S9-006` | complete | Additive `/v1/models` resources with the token as a dependency, regenerated OpenAPI and web client, api-only Compose volume, structural dependency gate, and the fixes from the provider-layer adversarial review |
| `OAK-S9-007` | complete | Models settings page, natural-language default intake, provenance on the confirmation screen, model-failure recovery, browser tests |
| `OAK-S9-008` | complete | Manual chapter and screenshot, ADR-0003 and ADR-0016, `TM-20`, security invariants, interface contract, `OAK-FR-INT-009`/`OAK-NFR-SEC-007`, `AGENTS.md`, `skills.md`, terminology, evidence |
| `OAK-S9-009` | complete | Closing adversarial audit (20 findings, 11 confirmed, all fixed with regression tests), status and changelog in both repositories, PR |
| `OAK-S10-001` | complete | Branch `hf-only-modes` from `origin/main` (`3430c71`), the ExecPlan, Sprint 10 registered in the original spec repo, tasks claimed, baseline gates green |
| `OAK-S10-002` | complete | The five hosted families other than Hugging Face removed with their fixtures, variables, rows, enum members and tests |
| `OAK-S10-003` | complete | `deterministic` (default), `online` and `local` modes replace `auto`/`model` on every interface; preferred and pinned model × provider pairs |
| `OAK-S10-004` | complete | Token corroborated with the Hub's `whoami-v2`; verdict stored with its time, stale after a day; pre-flight before an online interpretation; refusal before spend |
| `OAK-S10-005` | complete | Mode dropdown on intake and case pages; Settings with verdict, Refresh, pairs and Local AI model; masthead label repurposed; browser tests and manual capture |
| `OAK-S10-006` | complete | Documentation, ADRs, threat model, register (`RR-039`, `RR-042`), evidence, generated artifacts in both repositories |
| `OAK-S10-007` | complete | Live run against the real Hub and router (two product defects found and fixed), closing adversarial audit (27 distinct findings), corpus-wide documentation sweep, full gate green at HEAD, PR from `hf-only-modes` |
| `OAK-S10-008` | complete | `0.8.0` cut on `main`, tagged `v0.8.0` and approved: version touch-list, `0.8.0` changelog section, `docs/release/0.8.0/release-decision.md` with its evidence table filled and all three rows signed by `nmasamba` on 2026-09-23, regenerated OpenAPI, manual and error reference, a clean-tree image scan and a reproducible release build. The tag was cut the day before the signatures, at the owner's instruction, and has not been moved; publication stays a separate owner decision |
| `OAK-S11-001` | complete | Branch `sprint-11-install-observe` from `origin/main` (`3f47312`), the ExecPlan with the owner's four answers, Sprint 11 registered in the original spec repo, tasks claimed, baseline gates green |
| `OAK-S11-002` | complete | The selected candidate's topology installed as one labelled container per node from the target profile's acknowledged images, installation-scoped names, idempotent apply that adopts only its own container after reading its configuration back, verified owned-only removal, `preflight.installation`, and a separate signed `architecture` approval required by approve, dispatch and the runner |
| `OAK-S11-003` | complete | Opt-in hardened start and a smoke test inside `apply` with `test_result` and `aggregate_metric` evidence, key-based redaction, a lease-deadline guard, an isolated `DOCKER_CONFIG` for the Docker child |
| `OAK-S11-004` | complete | `observation-record` schema and kind, the pure builder, local-only `oak observe`, `deployed → observing`, rollback and destroy approvals after install |
| `OAK-S11-005` | complete | The journey reaches `deployed` and `observing`; assurance `gate_3` corrected under the declared digest shift; truthful bundle and case pages; `oak architecture`, local and remote |
| `OAK-S11-006` | complete | Full gate with PostgreSQL, the real-daemon journey, the browser suite on a throwaway stack, mutation checks on every new guard and fix, six-lens adversarial audit (28 of 29 findings survived; all fixed) |
| `OAK-S11-007` | complete | Documentation and coherence in both repositories, `RR-043` (count 43), `RR-023` re-scored, threat-coverage verdicts, ADR-0017 and its mirror, the manual's chapter 6 run against Docker, screenshots and PDF regenerated |
| `OAK-S11-008` | complete | Plan in `completed/`, status and changelogs in both repositories, PR opened for the owner's merge; no tag, no release |
| `OAK-S12-001` | complete | Branch `sprint-12-instrument-ui` from `origin/main` (`50f1673`), the ExecPlan with the owner's four answers, Sprint 12 registered in the original spec repo, tasks claimed, the throwaway stack on 18080/15174, and the baseline (web build and `journey.spec.ts`) green before any UI change |
| `OAK-S12-002` | complete | `web/src/tokens.css` (every colour, radius, shadow and duration; motion off under reduced motion), `styles.css` on tokens only, the three `@fontsource` packages at 5.3.0 (OFL-1.1, no CDN), primitives in `web/src/ui/`, the one variant-label map, and guards G1–G5 in `scripts/check_studio_ui.py` wired into `make validate`, each mutation-checked |
| `OAK-S12-003` | complete | Home ("What do you want to build?" over a "Brief prompt" composer with an attach chip, three mode chips and one brass send keycap; recent cases as tiles with progress rings) and Conversation (the brief as a bubble, machine moments per status, questions as chip cards with origin marks and reply bubbles, the review table with provenance marks, the case rail) |
| `OAK-S12-004` | complete | Designs (cards with a topology glyph and three range bars on one scale, a table view, the infeasible card dashed with its reason, a bench that compares two designs by drag or keyboard) and Architecture (the topology as SVG with its nodes-and-edges table, prediction chips, the "Take it and install" dock with three install lights and "Copy install steps", which runs nothing) |
| `OAK-S12-005` | complete | One-tap downloads: stored artifacts fetched raw and saved only when their sha256 equals `X-OAK-Artifact-Digest`, the drawn topology serialised to SVG, the downloads sheet, and the read-only `GET /v1/design-cases/{case_id}/architecture?candidate_id=&format=json\|yaml` composed in the shared control-plane service (integration-tested, listed as unreleased in the compatibility gate) |
| `OAK-S12-006` | complete | Decision, operation and settings pages on the tokens and primitives with every pinned string kept; `make web-e2e` green on a fresh throwaway stack; the 11 manual screenshots captured after that one run, captions rewritten, PDF rebuilt |
| `OAK-S12-007` | complete | Docs sweep in both repositories, the closing review (three finders, each with a refute-by-default skeptic) with its survivors fixed, `make check` green once, merged as PR #34 (`6142270`) on 2026-10-15, then a documentation coherence pass on the merged tree; no tag, no release |
| `OAK-S13-001` | complete | The owner's six kickoff answers (2026-10-16), branch `sprint-13-architecture-report` from `origin/main` (`6142270`), the ExecPlan, Sprint 13 registered in the original spec repo, tasks claimed, the throwaway stack on 18080/15174 and a green baseline |
| `OAK-S13-002` | complete | `architecture-report` and `report-narrative` schemas, the three kinds, `report_recorded`, and the pure composer: twenty sections each with a "Not yet" state, quantities with unit, basis and source, and the report guards R1–R4 in `make validate` (`d3fee4c`, `67ca147`) |
| `OAK-S13-003` | complete | The PDF renderer behind `ReportRendererPort` (`reportlab` 5.0.1), byte-stable across processes, with the layout agreement test against `web/src/topology.ts`. The PPTX was deferred by the owner after `python-pptx` failed the maintenance review (`770d941`) |
| `OAK-S13-004` | complete | `ReportService.record`, `POST /v1/design-cases/{case_id}:record-report` (unreleased), `oak report` locally and with `--server`, and the opt-in narrator, whose checked notes are labelled "Proposed by model" (`dd78cfb`) |
| `OAK-S13-005` | complete | `/cases/:caseId/report` with keyboard paging, the record keycap and notes chooser, the stale notice, PDF and JSON downloads that read "digest matches", the rail link and the Report tiles; `report.spec.ts` green (`255c90f`) |
| `OAK-S13-006` | complete | Docs (manual section and twelfth figure, README, interfaces, architecture, compatibility, dependencies, platforms, threat coverage, `RR-044`–`RR-047`, CHANGELOG); `make web-e2e` green on a fresh throwaway stack, the twelve screenshots captured after that one run, the manual PDF rebuilt (`35c042a`, `38975e6`) |
| `OAK-S13-007` | complete | The closing review (three finders, one refute-by-default skeptic: 21 raised, 14 fixed with tests, 7 refuted), `make audit` and `make check` once each, `make web-e2e` again on a fresh stack, the plan moved to `completed/`, and PR #36, merged by the owner on 2026-10-19 as `671d4a4` with CI green; no tag, no release |
| `OAK-S14-001` | complete | The owner's four kickoff answers and the Q4 follow-up (2026-10-21), branch `sprint-14-research` from `origin/main` (`671d4a4`), the ExecPlan, Sprint 14 registered in the original spec repo, the throwaway stack and a green baseline; ADR-0018 and its mirror, the threat and risk entries (`RR-048`–`RR-053`), the capability map, the hardware classes, the research bindings, the draft licence and harness lists, and `derive_research_terms` with its digest |
| `OAK-S14-002` | complete | The `research-snapshot` and `research-review` schemas, kinds, audit events and case extensions; nullable objective values with `unknown_reason` (K4) in the compiler, the Pareto rules, the report and `oak architecture`; the compare-only rule typed as `oak.community/comparison`; the report schema at twenty or twenty-one sections with the basis words |
| `OAK-S14-003` | complete | The research adapter through the one transport (30 requests, 60 s, size caps, a 24-hour cache, stable non-retriable refusals), allowlist normalisation, the research gates, the family-token pairing rule, honest quarantined manifests, the fixture source selected only by `OAK_RESEARCH_FIXTURES`, guards S1–S5, the live check |
| `OAK-S14-004` | complete | `ResearchService` (plan, run, review), the `research_catalogue` operation at one attempt, the merged `catalogue.research.<case>` snapshot, researched designs `candidate-05`/`06`, `GET …/research-plan`, `POST …:research` and `POST …:review-research-item`, the `oak research` CLI group locally and with `--server`, the PostgreSQL journey on the throwaway database |
| `OAK-S14-005` | complete | The Research moment (the consent card, **Run research**, the run watched in place, results as chips, every claim beside its evidence word, **Accept for comparison** / **Reject** with a rationale), the **New** chip and "Balanced, new", evidence chips, Source and Release date columns, the compare-only sentence, the Research tile; `research.spec.ts` |
| `OAK-S14-006` | complete | Appendix G, the K4 and basis rules, six options at most and unique labels, the two declared golden moves, the acceptance golden, guard R5; `docs/research.md`, the manual's section 2b with its thirteenth figure, threat-coverage rows with the Sprint 14 tests; the browser suite on a fresh stack, the figures recaptured in one run, the manual PDF |
| `OAK-S14-007` | complete | The closing review (three finders, one refute-by-default skeptic: 21 raised and merged to 18, 15 fixed with tests, 3 refuted), `make audit` (Pillow, certifi and vite lifted) and `make check` with the test database, the live check again, and PR #37, merged by the owner on 2026-10-22 as `a479780`; no tag, no release |
| `OAK-V1-001` | complete | The 1.0 readiness pass registered in both repositories (a release-readiness series like `OAK-PL` and `OAK-FS`), branch `release-1.0-readiness` from `origin/main` (`a479780`), the ExecPlan, and the post-merge truth pass for Sprint 14 |
| `OAK-V1-002` | complete | Documentation coherence: mechanical checks over every document, and four independent readers whose 86 findings were each checked against the code and fixed, in both repositories |
| `OAK-V1-003` | complete | Walkthrough: every documented journey run on the tree; V-1–V-4 and W-1–W-10 fixed (a server without a database answers 503 with a reason, among them) |
| `OAK-V1-004` | complete | Review: four independent finders (local CLI, server and upgrades, web, runner and release) reproduced 64 defects, 8 high |
| `OAK-V1-005` | complete | Fixes and polish: every finding fixed with a test or, for three, documented, each disposition naming its commit; runner enrollment before ingest is the one operator-visible change; the researched report golden moved with the consent digest (declared), the reference digests did not |
| `OAK-V1-006` | complete | The 1.0 readiness list in the completed plan: what only the owner can decide or do to cut 1.0, with what each takes |
| `OAK-V1-007` | complete | `make check` with the test database green once on the final tree (1,175 unit and contract, 417 integration, 43 end-to-end), `make audit` clean, `make web-e2e` 33 passed on a rebuilt and then a fresh throwaway stack, twelve manual figures re-captured and the PDF rebuilt, the plan closed, PR #38; the merge is the owner's |
| `OAK-V1-008` | complete | CI runs the PostgreSQL-gated suites: a pinned `postgres:17.6-alpine` service, `oak-db-migrate` and `OAK_TEST_DATABASE_URL` in the `check` job, refused by `make toolchain-check` if dropped; CI's integration run went from 389 passed and 32 skipped to 410 and 11 (`RR-019` closed) |
| `OAK-V1-009` | complete | Both workflows on Node-24 actions pinned by commit SHA with their release named, refused by `make toolchain-check` when unpinned; the tests on `httpx.ASGITransport` instead of the deprecated Starlette test client |
| `OAK-V1-010` | complete | The runner verifies against its bundled schemas only (`RR-033` closed); `docker` and `opa` resolved once to absolute paths, OPA below `1.0.0` refused (`RR-002` closed); both subprocess sites in a private working directory removed afterwards (`RR-027` closed); the verification order unchanged |
| `OAK-V1-011` | complete | `/readyz` is not ready while the database's schema revision is not this binary's, in either direction or never migrated (`RR-016` closed) |
| `OAK-V1-012` | complete | `oak keys show` reads only and refuses with `OAK-KEYS-UNINITIALIZED`; `oak keys init` creates (`RR-018` closed) |
| `OAK-V1-013` | complete | CLI polish: `models set-key` checks `--store` first, `policy packs` outside a workspace, `--server …/v1`, an unknown remote case is `OAK-CASE-NOT-FOUND`, `validate bundle` on an export says so, `report --narrative` without `--record` warns |
| `OAK-V1-014` | complete | The Report screen keeps focus at the pager's ends, the Take it sheet's Report tile hands focus to the record control on the Report screen, and recording refreshes in place (Sprint 13 notes A-2, A-4, A-5); each mutation-checked against a rebuilt image |
| `OAK-V1-015` | complete | reportlab's settings and the standard fonts' encoding pinned inside the PDF renderer; the two-process byte test sets eight `RL_*` variables; the golden bytes unchanged |
| `OAK-V1-016` | complete | `make check` with `OAK_TEST_DATABASE_URL` on a fresh, migrated throwaway PostgreSQL green on the final tree with zero `make: ***` lines (1,192 unit and contract, 435 integration with 4 skipped, 43 end-to-end), `make audit` clean, `make web-e2e` 33 passed on a throwaway stack recreated from nothing; the race in the PostgreSQL store's object writes that CI exposed once it ran the database suites fixed with a test; the plan closed and PR #39 opened. The merge is the owner's |
| `OAK-V1-017` | complete | REST and MCP answer `OAK-CASE-NOT-FOUND` for a case the server does not hold, at all 19 case-scoped entry points of the shared control plane and on either store (still `404`, opaque detail); the remote CLI names the case for either code |
| `OAK-V1-018` | complete | The release workflow's gate runs CI's PostgreSQL service, migration and variable and fetches the runner journeys' image; `make toolchain-check` refuses either workflow without the database suites; a run without the database counts the tests it skipped; the rule is in the definition of done (`RR-019`'s two limits lifted) |
| `OAK-V1-019` | complete | The original spec repo's dormant `spec-quality.yml` names `actions/checkout` v7.0.1 and `actions/setup-python` v7.0.0 by commit SHA, caches on `requirements-dev.txt` and runs Python 3.13; its validator refuses an unpinned action |
| `OAK-V1-020` | complete | `make check` with `OAK_TEST_DATABASE_URL` on a fresh, migrated throwaway PostgreSQL 17.6 (port 15433) green on the code tree (`4a54e78`) with zero `make: ***` lines: 1,198 unit and contract passed (1 skipped), 457 integration passed (4 skipped, the PostgreSQL-only assertions on the file store), 43 end-to-end passed with none skipped; `make audit` clean after `filelock` 4.2.4 (`7db8170`); `make web-e2e` 33 passed, 2 skipped, on the throwaway Compose project `oak-v1c` built from `7db8170`; on that stack REST, `oak-mcp` and the remote CLI each answered `OAK-CASE-NOT-FOUND` for a case it does not hold |
| `OAK-V1-021` | complete | `RR-021`'s browser clause: `scripts/run_browser_suite.py` (`make web-e2e-isolated`) runs the suite on a Compose project built from the commit, `/version` naming it, the skips exactly the two manual captures, nothing uploaded; CI's `web-e2e` job and the release gate run it, `make toolchain-check` enforces it; green in every CI run since `5f869ec` |
| `OAK-V1-022` | complete | `RR-054` closed: completions name the journal head (`journal_sequence`); `oak-runner status` reports `truncated` and `missing_journals`; `oak ingest` refuses a rewound or headless completion (`OAK-INGEST-JOURNAL`) |
| `OAK-V1-023` | complete | `RR-014` closed: `check-macos-arm64` (`macos-15`) and `check-linux-arm64` (`ubuntu-24.04-arm`, PostgreSQL, Docker journeys, native image builds); every check job and the release gate count skips against `tests/expected-skips.json`; four fully green CI runs |
| `OAK-V1-024` | complete | `RR-015`'s logging clause: allowlisted JSON lines on stderr from `oak-api`, `oak serve`, `oak-worker` and `oak-mcp`, an access line per request with `X-OAK-Request-ID`; the sentinel journey logs no secret or content; MCP's stdout only frames; a failure to start is a `startup_failed` line by type and code, or plain text for a refusal before logging is set up |
| `OAK-V1-025` | complete | `oak --server import` of a local export re-creates the case from its brief and digest-checked answers through the server's own steps, origin recorded; `OAK-IMPORT-REPLAY`; a relabelled export holding local authority records is refused (`OAK-IMPORT-AUTHORITY`); tested on the file and PostgreSQL stores and through the remote CLI |
| `OAK-V1-026` | complete | `RR-046`'s Unicode clause: IBM Plex (OFL-1.1) vendored, pinned by SHA-256 and embedded as subsets; text prints as written, anything the font lacks as its plain form or U+FFFD; byte-stable across processes, the environment and concurrent renderings; the PDF's bytes change, and with them the digests of what records a new one. Tagging open |
| `OAK-V1-027` | complete | `RR-005` mitigated: `make verify-release` checks `SHA256SUMS.sig` against `keys/allowed_signers`; only the 0.7.1 and 0.9.0 manifests, by digest, verify unsigned; no key pinned, nothing signed |
| `OAK-V1-028` | complete | Closing review: four lens reviewers and a skeptic, 21 distinct findings, all confirmed and fixed; then a second review of the finished batch, seven lenses and three skeptics per finding over three rounds, 57 confirmed and fixed, and a review of those fixes 25 more, fixed the same way (each code fix with a test and a mutation check). `make check` with the test database green (1,323 / 522, 4 skipped / 46, zero `make: ***`), `make audit` clean, the browser suite 33 passed on a throwaway project, the 43 reference artifacts byte-identical to `main`'s; PR #41, merged by the owner as `e8f98da` on 2026-10-29 |
| `OAK-V1-029` | complete | `RR-017` closed: the file adapter reads the manifest's format first; an older format the chain knows is refused on every command but `workspace status` and `export`, which copies it as it is (`OAK-WORKSPACE-MIGRATE`), a format no step accepts is refused everywhere, `export` included (`OAK-WORKSPACE-FORMAT`); `oak workspace migrate` alone runs the chain of pure, idempotent steps, never rewriting a stored object, recording a reshaped case as a successor with `workspace_migrated`, twice a no-op, byte-identical across hash seeds; the shipped chain holds no step; the `0.9.0` reference workspace is the corpus (`tests/fixtures/workspaces/0.9.0/`) |
| `OAK-V1-030` | complete | `RR-008` closed: `deployment-bundle.json` carries `assurance_plan_ref` and `oak validate bundle` checks it (`OAK-VALIDATE-DIGEST` on a substituted plan, `assurance_plan: bound`); a `0.9.0` bundle validates and reports `assurance plan unbound`, never verified; nothing is re-signed |
| `OAK-V1-031` | complete | `RR-025` closed and `RR-004`'s catalogue clause closed: `oak candidates` and the server read every active component-manifest and architecture-pattern extension into the catalogue after re-checking its activation record, its steward signature against the trust directory and its payload digests (`OAK-CATALOGUE-EXTENSION` otherwise; a curated id shadowed is `OAK-CATALOGUE-DUPLICATE`); the snapshot records each entry's provenance and lists its patterns; one shared pinned-signature check; the four reference digests moved once, recorded with before and after values |
| `OAK-V1-032` | complete | `RR-030` measured and bounded, its growth clause open: the first manifest read in a process verifies the lineage at about 4.4 ms per audit event, linearly from the reference journey (8 events, 43 indexed artifacts, 34 ms) to 500 events (2.2 s), with hardware provenance in `docs/performance/workspace-growth-2026-10-29.json`; a per-process cache keyed on the manifest's path and the digest of its bytes makes later reads in that process a parse (under 6 ms at 500 events); a mutation's validation and an export never consult it, object reads keep checking digests |
| `OAK-V1-033` | complete | `RR-031` bounded: a consumed nonce kept until its lease's expiry plus five minutes of skew (for ever when unknown); processed dispatches removed after `OAK_RUNNER_DISPATCH_RETENTION_DAYS` (default 30), never the newest, an un-ingested one or a journal; the journal verified once per run and appended from its in-memory head; the worker's lease extended between its steps; the runner's signed `heartbeat` message (`OAK_RUNNER_HEARTBEAT_SECONDS`, default 30), recorded by `oak ingest` as `runner_heartbeat` and a floor for the lease's completion |
| `OAK-V1-034` | complete | `RR-024` and `RR-041` bounded: the API admits 1,200 requests a minute per client address and 6,000 per tenant (a minute's burst, then the allowance; the probes exempt; state per process) and answers the next `429` with `Retry-After`; a tenant may have 100 operations queued or running (`OAK-OPERATION-QUOTA`); a case may record 100 billable model requests a UTC day, counted from its own history before anything is sent (`OAK-MODEL-BUDGET`); every value an `OAK_*` row, `0` off, a bad value `OAK-LIMIT-CONFIG`; every REST operation documents `429` |
| `OAK-V1-035` | complete | `RR-006` closed per platform: the API image's packages from a dated Debian snapshot (`ARG DEBIAN_SNAPSHOT`, moved at each release), a fixed user shadow date, the web image on the trixie variant of the unprivileged nginx image with the same snapshot, `SOURCE_DATE_EPOCH` from the commit with hash-based bytecode and rewritten layer timestamps; `scripts/reproduce_images.py` builds each image twice and compares, run by the release `images` job (`linux/amd64`) and CI's arm64 job on BuildKit `v0.34.0` pinned by digest, which `make toolchain-check` requires; the provenance claims reproducibility only from that record |
| `OAK-V1-036` | complete | Tier 2's restore follow-up: a server restore of a server export keeps the history as written and records one `workspace_restored` event under the importing actor (`oak.community/restored_from` names the export); the same export imports again as a duplicate under any key; `compatibility.md`, `interfaces.md` and `operations.md` say a restored history's actors are the export's claims |
| `OAK-V1-037` | in progress | Review and gates: an adversarial review of the finished diff, `make check` with the test database, `make audit`, the browser suite on a throwaway project, CI green over several runs, the PR |
| `OAK-S11-009` | complete | `0.9.0` cut after the Sprint 11 merge, at the owner's instruction: version touch-list, `0.9.0` changelog section, image scan from a clean tree, release build and verification, clean-room rehearsal, `docs/release/0.9.0/release-decision.md` with its evidence filled, the `v0.9.0` tag on `ff7d4df` (the merge commit of #31), the owner's three signatures on 2026-10-01, and the GitHub Release published that day from the verified `release.yml` artifacts |

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
- Security review produced `docs/security/threat-coverage.md`,
  `docs/security/residual-risk.md` (38 entries at the `0.7.0` release, each with a stable id;
  now 54 stable-id entries) and `SECURITY.md`. At Sprint 8 the
  coverage index mapped all nineteen threat ids then defined to tests (8 direct, 9 partial,
  2 structural, 0 uncovered, every cited test verified to exist); it now maps twenty
  (10 direct, 9 partial, 1 structural). **No
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
- Performance was measured with provenance rather than asserted: reference compiler 8.66 s
  median against a 120 s requirement, interactive read p95 30.5 ms against 500 ms, and
  workspace manifest reads growing from 3.8 ms at zero indexed artifacts to 283.3 ms at 43
  with no compaction anywhere (`RR-030`). Four measurements are published as *not measured*
  with the reason.
- Operator and contributor documentation now covers install through uninstall, every `OAK_*`
  variable (pinned to the source by a contract test), every `OAK-*` code (generated; 245 of
  the 265 codes that existed at `0.7.0` were previously undocumented), the supported
  platform matrix with architecture and
  glibc floors read from the lockfile, and the six architecture ADRs that shipped documents
  cite, mirrored so their citations resolve outside the original spec repo.
- The container scan that `OAK-S8-003` asks for was initially missed, recorded as `RR-035`,
  and then performed. It was worth doing: the first scan found 6 CRITICAL and 72 HIGH in the
  API image and 3 CRITICAL and 33 HIGH in the web image. Three causes — `uv` and `uvx`
  shipping in the runtime layer with advisories in their vendored Rust dependencies, base
  images lagging their distributions' patch streams (the pinned digests were checked and
  found *current* for their tags, so re-pinning would have fixed nothing), and a residue
  with no vendor fix. The API image is now multi-stage so the build tool no longer ships,
  and both images apply distribution security updates at build time. Result: the web image
  is entirely clean, the API image has 3 CRITICAL and 14 HIGH all with **no vendor fix
  available**, and **zero fixable findings remain** in either. `make scan-images` makes it
  repeatable and fails on anything fixable; `RR-036` tracks the residue, and `RR-037` recorded
  that the web image still ran nginx as root — closed at `0.7.1` by rebasing onto
  `nginxinc/nginx-unprivileged` (uid 101, verified in the running container).
- `OAK-S8-009` was decided by a human, not by the agent that prepared it. `nmasamba`
  approved `0.7.0` on 2026-08-22 in all three roles — maintainer, security and licence —
  after review. All three roles being held by one person is recorded in the decision record
  itself, because it means the security and licence judgements were not independent of the
  maintainer judgement. The approval accepts `RR-035` (images unscanned) and accepts
  `RR-001` and `RR-003` as non-blocking **for a local-first developer release only**; both
  become P0 before any release permitting a runner off the operator's machine. Approval is
  not a Gate 2/3 deployment approval and does not authorise publication.
- The pre-launch hardening plan (`OAK-PL-001`–`007`, 2026-08-24) closed seven register
  entries before anything was published, with every milestone gated by a full
  `make check` (final: 419 unit/contract + 191 integration, 4 by-design skips, + 42
  e2e, PostgreSQL suites enabled) and a direct recompilation of the reference case.
  The four reference digests were held byte-stable through every milestone except the
  one sanctioned digest migration (`OAK-PL-006`), whose before/after values are
  recorded in the exec plan and `CHANGELOG.md`: `deployment_bundle` and `runner_plan`
  moved; `selected_candidate` and `semantic_manifest` were recompiled on both sides and
  are byte-identical. The `0.7.1` image rescan after the web base change reports zero
  fixable findings with the web image clean at every severity; per-image SBOMs and
  unsigned provenance live in `docs/release/0.7.1/`. `make audit` re-ran clean. The
  runner now enforces the compiled verification policy, verifies the runtime's resolved
  image digest after creation, honours a target registry allowlist, and consumes only
  signed revocation notices matched against a signed, monotonically sequenced manifest
  over a fail-closed channel — each denial path
  adversarially tested, including a full `run_once` denial that leaves no journal.
  That release was approved on 2026-08-27 and published on 2026-09-03
  (`docs/release/0.7.1/release-decision.md`); `0.8.0` was approved on 2026-09-23
  (`docs/release/0.8.0/release-decision.md`), and `0.9.0` was approved by `nmasamba` on
  2026-10-01 and published the same day (`docs/release/0.9.0/release-decision.md`).
- The final documentation sweep (`OAK-FS-001`–`003`, 2026-08-25) was verified rather
  than assumed: a six-dimension multi-agent review of the sweep branch (vendor-reference
  completeness including PDF/PNG binary content, manual coverage and truthfulness
  against `SECURITY.md` and the intake/interpreter sources, every manual command against
  the tree, gate and CI risk, post-merge truth in both repositories, and close-out
  discipline) raised three blockers — a leftover YAML-first diagram label, a
  nonexistent `oak import --workspace` flag, and a prerequisites row claiming Intel
  macOS support that `docs/platforms.md` denies — all fixed, with the full CLI journey
  and the complete signed-runner journey (keys, sign, approve, dispatch, `run-once`
  against the mutation fixture, ingest, status, revoke) executed live to capture the
  manual's expected-output excerpts. `make check` passed on the sweep tree (verified by
  counting `make: ***` lines), and direct recompilation reproduced all four reference
  digests byte-identically. The closing adversarial audit (five lenses, independent
  refute-by-default skeptics) raised 47 findings, 21 confirmed and fixed, 26 refuted —
  see the completed plan's audit section. It found, among others, that chapter 8 told
  the reader to run a script it had just deleted, that chapter 6 gave consumers a
  command needing a checkout they do not have, and that the audit-timeline screenshot
  had raced its own data fetch; the screenshots were re-captured from a live stack
  reporting `0.7.1`.
- Sprint 9 delivered the optional model provider (merged as PR #21, `88fa876`): `make check`
  green on the merge tree, the four reference digests recompiled byte-identically, and a
  closing adversarial audit of 20 findings (11 confirmed, all fixed with regression tests).
- Sprint 10 narrowed the provider surface to Hugging Face and the loopback server. The
  route-timing constants in `src/oak/adapters/models/providers.py` come from one live run —
  a 15-claim, 3,074-output-token proposal on a route published at 72.5 tokens per second,
  which delivered about 1.57 times its published figure — and `tests/live/` is where that
  gets corrected. Evidence for `OAK-S10-007` is recorded in the completed ExecPlan.
- Sprint 12 (merged as PR #34, `6142270`): `make check` green once on the final tree
  (764 unit and contract, 296 integration and 42 end-to-end tests, the OpenAPI gate and the
  web build; zero `make: ***` lines); `make web-e2e` 24 passed and 1 skipped (the gated
  capture) on a throwaway stack recreated from nothing, before the 11 screenshots were
  captured from it; the closing review's 18 findings (6 refuted, 12 fixed) re-verified
  with the journey, downloads and models specs; each Studio guard mutation-checked; CI
  green after `source-map-js` was overridden to 1.2.2. The four reference digests and the
  OpenAPI baseline are unchanged; the one new route is listed as unreleased.
- Sprint 13 closed with `make check` green once on the final tree (922 unit and contract,
  318 integration with 24 skipped, 42 end-to-end with 1 skipped; zero `make: ***` lines),
  `make audit` clean, `make web-e2e` green twice on a fresh throwaway stack (M7 and M8), and
  a closing review of 21 findings (14 fixed with tests, 7 refuted). Evidence is in the
  completed ExecPlan.
- The 1.0 readiness pass (PR #38): `make check` with `OAK_TEST_DATABASE_URL` on a fresh
  throwaway PostgreSQL green once on the final tree, zero `make: ***` lines (1,175 unit and
  contract, 417 integration with 4 skipped, 43 end-to-end); `make audit` clean;
  `make web-e2e` 33 passed and 2 skipped on the rebuilt stack, and again on a stack
  recreated from nothing before the twelve changed manual figures were captured. The live
  research check was not run (see the plan's Verification). Evidence is in the completed
  ExecPlan.
- Sprint 14 (merged as PR #37, `a479780`): `make check` with `OAK_TEST_DATABASE_URL` on the
  throwaway database, zero `make: ***` lines (validate with G1–G5, R1–R5 and S1–S5);
  `make audit` green after Pillow 13.0.0, certifi 2026.10.19 and vite 7.3.7; the hand-run
  live research check passed against the three hosts; `make web-e2e` 26 passed and 2
  skipped on the rebuilt stack; a closing review of 21 findings (merged to 18; 15 fixed
  with tests, 3 refuted). Evidence is in the completed ExecPlan.

## Safety boundary

The current harness accepts bounded local architecture briefs, catalogue files, rationale, and target profiles and treats their content as untrusted data. It has no mandatory model-provider call and no secret resolution: every brief is read deterministically and offline unless the request names `online` or `local`, and only then does a user-configured provider — Hugging Face Inference Providers, or a loopback OpenAI-compatible server — receive the brief text, through the single egress module, under `RR-039`. Since Sprint 13 a report recorded in a model note mode sends its main slides' words to that same provider (`RR-045`), and since Sprint 14 a research run the user has consented to sends search terms drawn from closed vocabularies, anonymously, to the Hugging Face Hub, its router and GitHub's REST API (`RR-048`): no brief text, case id or credential is among them, every researched claim carries its evidence class, a researched component is stored quarantined and reaches comparison only, and nothing research finds is approved, selected or installed. Signing, approval, runner dispatch, and target mutation now exist in explicitly local development form: keys are labelled `development`, the runner reaches only an isolated non-production profile that opts in through an explicit acknowledgement. The only permitted mutation is installing the selected candidate's topology through fixed allowlisted argument vectors: one labelled, network-isolated container per node, from the digest-pinned image the profile acknowledges for that component, and removing only containers that carry the case's labels. A profile acknowledging `isolated-non-production-fixture-only` never starts them; one acknowledging `isolated-non-production-hardened-start` starts each under fixed hardening flags (no network, read-only root, no capabilities, no new privileges, uid 65534, memory, CPU and process ceilings, no restart, no volumes, environment or ports) and smoke-tests it inside `apply`, which runs the image's own code on the operator's machine (`RR-043`). Every mutating operation requires a separately signed, current, digest and target bound approval that the runner verifies independently before any target access, an install also requires a separately signed approval of the architecture whose decision and installation digests the runner checks against the dispatch, the compiled verification policy's clauses are enforced per requested operation kind, revocation notices are honoured only when signed by a pinned anchor and matched against a signed, monotonically sequenced manifest of the whole set over a fail-closed channel, and after creating or adopting each container the runner verifies the image digest the runtime actually resolved; a mismatch fails the install, whose compensation removes only the containers that install created. `oak observe` records what the installation was observed to do beside what was predicted; it proposes nothing and authorizes nothing. A compiled plan is inert until it is signed, approved, and independently verified by the runner. Governed extensions and policy packs are untrusted input: they are quarantined on install, verified against pinned local trust anchors, and never executed — an extension payload is data, and a deployment-adapter extension only binds configuration to an in-tree renderer identity. Policy evaluation is fail-closed, an undecidable condition can never yield an automated allow, and an optional external policy engine that disagrees with the built-in reference engine is refused rather than published. The bounded MCP server and the CLI's remote mode are additional transports onto the same application services and grant no authority: the MCP surface is design/read only with no approval, signing, dispatch, secret, policy-override, file, or command tool, and remote mode refuses the local-only signing, approval, dispatch, ingest and observe commands rather than acting on local state; the read-only `oak architecture` works in both modes. Remote mode trusts the control plane it is pointed at; a wrong-shape response is refused with a stable code rather than crashing. Signed webhook envelopes and compiled review bundles are verified against pinned keys and existing digest edges only, and are not themselves execution authority. All committed fixtures are public or synthetic, and the committed webhook publisher key is public material whose private half was discarded.
