<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S14-001–007: Research at the point of design

**Authorized by the owner on 2026-10-21** by launching `SPRINT-14-PROMPT.md` (governance
root) and answering its four kickoff questions, plus one follow-up on Q4. The prompt is
the specification; this plan records the owner's answers, the design choices the prompt
left open, and the proof for each milestone.

Execution is on branch `sprint-14-research`, branched from `origin/main` at `671d4a4`
(the merge of PR #36, Sprint 13). `0.9.0` is the latest published release; nothing here
is a release.

## Owner's answers, and what they settle

| # | Question | Answer (2026-10-21) | Effect on this plan |
|---|---|---|---|
| Q1 | Sources (K1, K6) | **Hugging Face and GitHub, anonymous**, within a 30-request budget and a 24-hour cache | The adapter's allowlist is exactly `huggingface.co`, `router.huggingface.co` and `api.github.com`. No token is stored; GitHub's anonymous 60-an-hour core bucket is the budget's ceiling. |
| Q2 | New repositories (K2) | **Two tiers** | The Hub's `TRUSTED_NAMESPACES` and the owner-reviewed `harness-repositories.yaml` pass the tier gate on their own. Anything else a bounded search finds is *unvetted* and enters a design only after `:review-research-item` records an accept with a rationale. The harness list is drafted here and goes to the owner in the PR; until reviewed, only the trusted namespaces form the trusted tier. |
| Q3 | When (K3, K7) | **Per run, at `ready_for_candidates` only**, behind a consent card; off by default | `research_catalogue` is refused from `candidates_ready` on (`OAK-RESEARCH-STATE`, 409). The consent is `{hosts, terms_digest}` recomputed from the current intent. A recorded report can never go stale through research. |
| Q4 | Designs (K4, K5) | First **"selectable once reviewed"**; on the follow-up, **the compare-only rule now, selection next sprint** | Unknown estimates in the compiler (`value: null` with `unknown_reason`); one researched design per pattern with a model role (at most two), `candidate-05` upward, labelled "Balanced, new" / "High assurance, new"; listed `infeasible` with every reason and its estimates, refused by `select`; and the compare-only rule (below), recorded in ADR-0018. Sprint 15 (selection) is registered in the governance `sprints.md` with its prerequisites. |

**The Q4 follow-up.** "Selectable once reviewed" conflicts with the prompt's §7 ("a
researched design is shown with its reasons and never selected") and needs an evaluation
path for non-curated ids, which does not exist (offline evaluation is `FIXTURE_RESULTS`,
keyed by the four curated ids). The owner was asked how to reconcile it and chose the
middle option. The acceptance line "the researched designs are `infeasible`, and that is
the expected result" therefore reads: they are `infeasible` and unselectable, **and they
are compared**.

**The compare-only rule (K5, as decided).** A researched candidate whose hard-constraint
results are each `pass`, or a non-pass whose cause is a pending review or an unpublished
value, is *comparable*: `_apply_pareto` includes it in dominance, so its `pareto` block
carries a real `frontier_member` and `dominated_by`, and a curated candidate's
`dominated_by` may name it. Its `status` stays `infeasible` (feasible still means every
hard constraint `pass`), `select` still refuses it with `OAK-SELECT-INFEASIBLE`, and its
`rejection_reasons` keep every reason. The classification is typed, never parsed from a
reason string: it is written to the candidate's `extensions["oak.community/comparison"]`
as `{rule, comparable, pending_review: [constraint ids], unknown_value: [constraint ids]}`.
Under K4, an objective whose value is unknown never dominates and is never dominated, so
the comparison names the objectives it could not compare in `sensitivity_summary` and in
the extension. Curated candidates never carry the extension, so their bytes do not move.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-21
- Last updated: 2026-10-21 (M4)
- State: in-progress
- Claimed tasks: `OAK-S14-001`–`OAK-S14-007`

One plan covers seven task IDs because they build one vertical feature, from the decision
record and the egress adapter to the screen and the report appendix, judged by one set of
guards, one acceptance case and one browser spec.

## Recipes and requirements

From the governance `skills.md`: **Model provider integration** (the egress, the one
transport, what leaves the machine; read first: ADR-0009, ADR-0016,
`docs/adr/0003-optional-model-provider-credentials.md`, TM-13, TM-20, `RR-042`,
`tests/integration/test_offline_boundary.py`); **Governed pack** (untrusted component
metadata, quarantine, poisoned and stale fixtures; "popularity as approval" and
"unreviewed live web content" are its Avoid list, and ADR-0018 says how research meets the
second: a researched entry reaches comparison, never approval); **Compiler stage**
(unknown estimates, Pareto, no silent defaulting); and **Contract change**, **Domain use
case**, **Persistence/migration**, **Interface adapter**, **Workspace UI**,
**Evaluation/evidence** and **Security review**.

Requirements cited in tests and the change record: `OAK-FR-CAT-001`–`005` and
`OAK-NFR-SEC-003` (untrusted manifests never select tools or grant permissions).

## Outcome

Today OAK designs only from a pinned catalogue of three synthetic components, so a model
released yesterday can never appear.

After this plan, from a case at `ready_for_candidates`:

1. `oak research --plan` (or the case page's "Look for newer options?" card) shows the
   hosts and the exact terms that would be sent, with their digest. Nothing has left the
   machine.
2. `oak research --consent <terms_digest>` (or **Run research**) sends those terms,
   anonymously, to the Hugging Face Hub, the router and GitHub's REST API, within 30
   requests and 60 seconds, and records a `research_snapshot`: the terms, hosts, request
   URLs, response digests, normalised manifests and every verdict. The case page shows
   chips: found, passed, need your review.
3. `oak research review <item-id> --accept --rationale-file f` (or the review flow)
   records a `research_review` for an unvetted item, bound to the snapshot and the item's
   response digest.
4. **Generate** compiles the merged catalogue snapshot (curated plus passing researched
   entries) and adds at most two researched designs, `candidate-05` upward, each marked
   New with its source, its date and the evidence class of every claim, listed
   `infeasible` with every reason, compared on the frontier, and refused by `select`.
5. The architecture report gains appendix G, "Research", present only when the case holds
   a research snapshot.

With the fixed clock `2026-10-20T12:00:00Z` and the owner's acceptance fixtures (a model
created on the Hub on `2026-10-19` and a harness released on `2026-10-13` whose notes name
the model's family), the run reports found 2, passed 1, need review 1; generating without a
review gives the model alone in each researched design; generating after the user accepts
the harness puts it in the serving role; and the same snapshot and reviews give the same
candidate bytes in a fresh interpreter.

## Context and invariants

- **The egress surface, pinned.** `ModelTransport` (`src/oak/adapters/models/transport.py`)
  is the one module that opens a connection. The research source readers live in one new
  file under `src/oak/adapters/models/`, parse with pure functions, import no network
  module, and are added to `ALLOWED_NETWORK_IMPORTERS`-adjacent lists
  (`DOCUMENTED_MODEL_ADAPTERS`, `HOSTED_MODEL_MODULES`) on purpose. A deterministic
  generation imports no research module (new test beside the deterministic-report test).
- **What leaves the machine.** Only search terms from a pure function of the confirmed
  intent, from closed vocabularies defined as data (`catalogue/research/capabilities.yaml`,
  the hardware classes, `catalogue/research/licences.yaml`). No brief text, no case id, no
  credential. The consent card shows the terms verbatim; the audit event records their
  digest.
- **Untrusted in, typed out.** Hub, router and GitHub text is author-controlled and
  hostile. Strings are NFKC-normalised and refused on any category C character;
  identifiers match an ASCII pattern and are refused when NFKC changes them; kept values
  are closed enum values or bounded strings from a fixed character class; forbidden words
  refuse the item; a gap is `unknown` with an `unknown_reason`, never a placeholder.
- **Nothing is approved by research.** A researched manifest is stored `quarantined`;
  `eligible` in the merged snapshot is decided by `community-research-gates-1.0.0` alone;
  nothing becomes `approved_for_context` here.
- **Deterministic given the snapshot.** Same snapshot and reviews, same candidate bytes.
  Without research, every byte is as today: the four reference digests, the curated
  candidates of an unresearched case, the reference report golden (apart from the two
  declared follow-ups) and the OpenAPI baseline do not move.
- **The web stays a REST client,** adding exactly two non-GET calls, `researchCatalogue`
  and `reviewResearchItem`, listed in G2's `KNOWN_MUTATIONS`.
- **Honest claims.** Every claim shows its evidence class; `unknown` stays `unknown` with
  its reason; nothing is "best" or "works well"; a third-party figure never reads as
  measured or declared by OAK; a model's date is "created on the Hub".
- **Requirements and decisions:** `OAK-FR-CAT-001`–`005`, `OAK-NFR-SEC-003`, ADR-0009,
  ADR-0011 (scoped for researched entries by ADR-0018), ADR-0016, ADR-0018 (new).

## Scope

### In

- ADR-0018 in both repositories with its mirror; the egress line in `AGENTS.md` and
  `docs/build/security-invariants.md`; threat rows TM-02, TM-04, TM-13 (rewritten), TM-14,
  TM-17; residual risks from `RR-048`; Sprint 13's disclosure gaps (README, `STATUS.md`
  safety boundary, threat-coverage gap table).
- Data: `catalogue/research/capabilities.yaml`, `licences.yaml`,
  `harness-repositories.yaml`, `bindings/`; the derived-terms function.
- Contract: `research-snapshot` and `research-review` schemas, kinds and examples; the
  `oak.community/research_snapshot_ref` extension and export-lineage check; the
  evidence-class enum; nullable objective values with `unknown_reason` in every reader;
  the compare-only rule; the report schema's appendix G and basis words.
- The research adapter: the three sources through the one transport, allowlist
  normalisation, the research gates, the in-process fixture source selected by
  `OAK_RESEARCH_FIXTURES`, recorded synthetic fixtures, a live test file.
- The `research_catalogue` operation, the plan read, `:research`,
  `:review-research-item`, the CLI, the audit events, the merged snapshot and generation
  against it with stable ids.
- The workspace: the Research moment, consent card, results chips, review flow, New chips
  and labels, evidence words, source and release-date columns, the Take it sheet entry.
- The report: appendix G, the unknown and basis rules, unique labels, the baseline rule,
  the six-option maximum, `gather_records`, the two declared golden moves, a second golden
  for the acceptance case, `check_report.py` composing it live (R5, R2 additions).
- `scripts/check_research.py` (S1–S5) in `make validate`; docs, manual, screenshots, PDF.

### Out

- Package registries and leaderboards as sources (K1); a GitHub token (K6).
- Research after candidates exist (K7); selecting a researched design (Sprint 15).
- Researched retrieval engines filling a retrieval role (found and listed only).
- Research or report tools over MCP; the PPTX rendering; hardware scanning; native
  installation; any release.

## Contract and data changes

- **`schemas/research-snapshot.schema.json` (0.1.0).** `{schema_version, id, version,
  case_id, intent_ref, occurred_at, source_mode: live|fixture, terms, terms_digest,
  hosts[], budget {requests_max, requests_used, deadline_seconds, elapsed_seconds},
  freshness_window_days, rule_sets[], requests[{host, path_digest, status, response_digest,
  checked_at, refusal_code|null}], items[{id, kind: model|harness|retrieval_engine,
  source, source_id, tier: trusted|unvetted, created_or_released_at, claims[{field, value,
  evidence_class, checked_at, source_pointer}], manifest_ref|null, verdict:
  passed|needs_review|failed, reasons[], response_digest}], pairings[{model_item_id,
  harness_item_id, claim_classes[]}], extensions}`. No field named `command`, `shell`,
  `executable` or `argv`; install text, where kept at all, is `hint`.
- **`schemas/research-review.schema.json` (0.1.0).** `{schema_version, id, version,
  case_id, snapshot_ref {id, version, digest}, item_id, item_response_digest, decision:
  accept|reject, rationale, actor, recorded_at, extensions}`.
- **Kinds** (three registration points each): `research_snapshot` and `research_review`
  (JSON). **Audit events:** `research_completed`, `research_item_reviewed`. **Case
  extensions:** `oak.community/research_snapshot_ref` and
  `oak.community/research_review_refs`, both in the export-lineage check.
- **`common.schema.json` objective:** `value` becomes `number|null` with an optional
  `unknown_reason` (required when `value` is null). Additive: every stored document still
  validates; a reader that assumes a number breaks only on a researched candidate.
  Classified in `docs/compatibility.md`; a pre-change export is shown to import.
- **Candidate extensions:** `oak.community/comparison` (the compare-only classification),
  `oak.community/research` (source, created/released date, tier, review state, evidence
  classes) on researched candidates only.
- **Component manifest (0.3.0):** honest values for researched manifests; a `commit_id`
  field in a namespaced `extensions["oak.community/research"]` for Hub revisions and
  GitHub tag commits (never in a sha256 field); weight-size estimate labelled with its
  estimator. Decided in M2.
- **`catalogue-snapshot`:** a second rule set `community-research-gates-1.0.0` beside
  `community-open-components-1.0.0`; a merged snapshot has its own id/version.
- **`architecture-report` (unreleased 0.1.0):** `sections` 20 or 21, `appendix-research`
  / `G` added to the ids, numbers and `detail_in`; `basis` gains "published by source"
  and "measured by source"; `source_type` printed through a closed label map (golden move
  1); `FIXED_RENDERER` drops `python-pptx` (golden move 2).
- **REST (unreleased):** `GET /v1/design-cases/{case_id}/research-plan`;
  `POST /v1/design-cases/{case_id}:research` (202, operation) requiring
  `X-OAK-Model-Token`, then consent, then `Idempotency-Key`/`If-Match`, then status;
  `POST /v1/design-cases/{case_id}:review-research-item`. Listed in
  `UNRELEASED_OPERATIONS` and `UNRELEASED_SCHEMAS` with dated comments.
- **Operation kind:** `research_catalogue`, submitted with `max_attempts=1`.
- **CLI:** `oak research --plan`, `oak research --consent <digest>`, `oak research review
  <item-id> --accept|--reject --rationale-file <file>`, local and `--server`.
- **Errors:** `OAK-RESEARCH-STATE` (409), `OAK-RESEARCH-CONSENT` (409),
  `OAK-RESEARCH-REDIRECTED`, `-OVERSIZED`, `-RATE-LIMITED`, `-UNREACHABLE` (none
  retriable), `OAK-RESEARCH-ITEM-UNKNOWN`, `OAK-RESEARCH-REVIEW-STATE`, and `OAK-CAT-*`
  gate reasons. The transport's 3xx refusal carries the status as a typed field.
- **Configuration:** `OAK_RESEARCH_FIXTURES` (safety-relevant; selects the in-process
  fixture source).
- **Compatibility:** additive everywhere. No migration. The reference journey records no
  research, so its digests hold.

## Milestones

Each milestone ends with one commit, its exit check green and a line under Progress.

### Milestone 0 — Kickoff (`OAK-S14-001`)

- Work: the ground check, the truth pass (Sprint 13 merged), the answers, Sprint 14
  registered in governance, the branch, this plan, tasks claimed, the throwaway stack
  `oak-s14` on 18080/15174.
- Proof: `pnpm --dir web build` green; `journey.spec.ts` green on the throwaway stack.
- Rollback: delete the branch; the governance edits are plain text.

### Milestone 1 — The decision record (`OAK-S14-001`)

- Work: ADR-0018 "Research at the point of design" in both repositories (mirror with SPDX
  line and the mirrored-from comment; rows in both indexes); the egress line in
  `AGENTS.md` and `docs/build/security-invariants.md`; TM-02/04/13/14/17 extended and
  `threat-coverage.md` rows; `RR-048` onward with the count updated in `STATUS.md`,
  `CHANGELOG.md`, the register and the governance `STATUS.md`; Sprint 13's disclosure
  gaps; `capabilities.yaml`, the hardware classes, `bindings/`, the draft `licences.yaml`
  (seeded from `PERMISSIVE_LICENCES`) and `harness-repositories.yaml`; the derived-terms
  function (`oak.compiler.research_terms` or similar, pure) with tests over every
  committed brief's intent and `tests/fixtures/research/intents/`.
- Proof: governance validation green; the terms function emits only vocabulary terms over
  every intent (the S2 check).
- Rollback: revert the commit.

### Milestone 2 — Contract and unknown estimates (`OAK-S14-002`)

- Work: the two schemas, kinds, examples, `EXAMPLE_BY_SCHEMA`, `schemas/README.md`; the
  extensions and the export-lineage check; the evidence-class enum; nullable objective
  values with `unknown_reason` in `candidates.py` (`_objectives`, `_dominates`),
  `planning.py`, `observation.py`, `architecture.py`, the report composer and the web
  pages; the compare-only rule; `_hardware_constraint`/`_target_requirements` treating an
  unpublished minimum as `unknown` for researched manifests only; honest manifest values
  and the commit-id decision; the report schema's appendix G and basis words.
- Proof: the four reference digests, the curated candidates' bytes and the reference
  report golden unchanged; Pareto tests: an unknown never dominates and is never
  dominated, and the frontier names the objective it could not compare; a report for a
  case with an unknown objective shows its reason.
- Rollback: revert the commit; no stored data changes.

### Milestone 3 — The research adapter (`OAK-S14-003`)

- Work: `src/oak/adapters/models/research_sources.py` (Hub, router, GitHub readers through
  `ModelTransport`, pure parsers, the request budget and one monotonic deadline, the
  24-hour cache keyed by terms digest, the per-response size caps); the normalisation by
  allowlist; the research gates `community-research-gates-1.0.0`; the fixture source
  selected only by `OAK_RESEARCH_FIXTURES`; recorded synthetic fixtures under
  `tests/fixtures/research/`; `tests/live/test_research_live.py`.
- Proof: the acceptance case passes on fixtures with the fixed clock; poisoned, lookalike,
  oversized and redirected responses are refused with stable codes; the adapter lists in
  `test_offline_boundary.py` are updated; a deterministic generation imports no research
  module; the live check ran once and is recorded below.
- Rollback: revert the commit.

### Milestone 4 — Operation and interfaces (`OAK-S14-004`)

- Work: `research_catalogue` registered in the four places; `ResearchService` (plan, run,
  review) in the application layer; the merged snapshot and generation against it with
  stable ids; the plan read, `:research`, `:review-research-item`; the CLI; the audit
  events; OpenAPI, the generated client, the error reference, interface tables.
- Proof: integration tests in the prompt's order (token, consent, idempotency and
  `If-Match`, then egress); a stale `If-Match`, a missing consent and a retry send no
  request (fake transport log); offline gives a clean refusal and the curated catalogue;
  research from `candidates_ready` is refused; the same snapshot and reviews give the same
  bytes; the CLI locally and with `--server`; the PostgreSQL path on the throwaway
  database with pass and skip counts recorded.
- Rollback: revert the commit.

### Milestone 5 — The workspace (`OAK-S14-005`)

- Work: the Research moment, consent card, results chips, review flow, New chips and
  labels, evidence words, source and release-date columns, the sheet entry; the label and
  evidence-word mirrors with their agreement tests; `KNOWN_MUTATIONS`.
- Proof: `research.spec.ts` on the throwaway stack with the fixture source: plan, consent,
  run, review the unvetted harness, generate, see the new design and why it cannot be
  selected; zero axe violations; `journey.spec.ts` and `report.spec.ts` unchanged.
- Rollback: revert the commit.

### Milestone 6 — Report and docs (`OAK-S14-006`)

- Work: appendix G, the K4 and basis rules, unique labels, the baseline rule, the
  six-option maximum, `gather_records`, the two declared golden moves, a second golden for
  the acceptance case, `check_report.py` composing it live (R5, R2 additions); docs
  (manual, README, interfaces, compatibility, threat coverage, risks, configuration,
  CHANGELOG, both `STATUS.md` files).
- Proof: a report records, validates and renders for the acceptance case at six options;
  no researched free text in `narrator_facts`; R1–R5 green over both cases; the README's
  "What OAK doesn't do (yet)" names research's limits.
- Rollback: revert the commit.

### Milestone 7 — Browser suite, screenshots, manual (`OAK-S14-006`)

- Work: `make web-e2e` on a fresh throwaway stack; the manual's screenshots after exactly
  one suite run, with a thirteenth shot for the research section; the manual PDF.
- Proof: `make web-e2e` green; the shot count matches the manual's figures.
- Rollback: revert the commit.

### Milestone 8 — Review and close (`OAK-S14-007`)

- Work: the closing review (one workflow: three finders, one skeptic); survivors fixed
  with tests; `make check` with the test database and `make audit` once each; the live
  check once more; merge `origin/main` if it moved; a PR; the plan moved to `completed/`.
- Proof: zero `make: ***` lines; CI green; the PR names the draft harness list as awaiting
  the owner's review and the §10 follow-ups closed.
- Rollback: the PR is the owner's to merge or close.

## Verification

- Unit: the terms function, the normalisation rules (fullwidth, zero-width,
  right-to-left-override, forbidden words, bounds), the parsers on recorded and poisoned
  fixtures, the gates with each reason code, the family-token rule with ADR-0018's cases,
  the weight estimate per dtype, the Pareto rules with unknowns, the compare-only rule.
- Contract: schema conformance and examples; the mirrors (labels, evidence words); the
  ADR mirror; the configuration reference; the residual-risk count; the OpenAPI baseline
  with the unreleased lists; the export-lineage check.
- Integration: the service order (token, consent, idempotency, `If-Match`, status, egress)
  with the fake transport's request log; refusals from `candidates_ready`; the merged
  snapshot's determinism in a fresh interpreter; the worker path on PostgreSQL;
  `max_attempts=1`.
- End to end: `research.spec.ts` on the throwaway stack with the fixture source; the
  reference journey unchanged.
- Guards in `make validate`: S1–S5, R5 and the R2 additions, each mutation-checked.
- Live, by hand, once at M3 and once at M8 (`OAK_LIVE_RESEARCH_TESTS=1`), recorded under
  Progress as evidence, never as a gate.

## Security, privacy and authority review

- **Egress.** Real egress exists only after the user's recorded consent for one run: the
  derived terms, anonymously, to the three K1 hosts, within 30 requests and 60 seconds.
  The REST route checks the capability token first, then consent, then idempotency and
  version, then status, so a stale or repeated request sends nothing. The local CLI needs
  no token, as `oak report --narrative` does not.
- **The live checks in this plan are real egress.** `tests/live/test_research_live.py`
  sends the reference brief's derived terms, anonymously, to `huggingface.co`,
  `router.huggingface.co` and `api.github.com` within the budget. It runs only by hand
  with `OAK_LIVE_RESEARCH_TESTS=1`, never under `make check`.
- **Input trust.** Every source byte is hostile metadata. It is bounded on read,
  normalised by allowlist, validated against a closed schema, and re-validated before it
  enters canonical state. Install text is data OAK never runs. No source text reaches an
  `OAKError` message, a log, a main slide or a model.
- **Authority.** Research proposes; the gates decide eligibility for comparison only; a
  human review records a decision bound to digests; nothing approves a component for a
  context, nothing selects, signs, dispatches or installs. MCP cannot research.
- **Failure state.** A refused or timed-out run records one attempt and no snapshot; an
  outage shows as an outage (no cached substitute); an expired cache entry is never used.
- **Audit.** `research_completed` carries the terms digest, the hosts and the snapshot
  reference; `research_item_reviewed` carries the review reference.

## Operational and rollback plan

- No migration: two new JSON kinds, two events and two extensions, all additive.
- The fixture source is selected only by `OAK_RESEARCH_FIXTURES` (documented as
  safety-relevant); the throwaway override sets it, the shipped Compose file does not.
- Rollback of any milestone is a revert; a case that holds a research snapshot keeps it in
  its index and audit trail, and generation without the feature reads the curated
  catalogue as today.
- Bounded failure surface: a local workspace or database; nothing outside the machine
  changes.

## Progress

- [x] 2026-10-21 M0: ground check (origin/main `671d4a4`, no open PR, `0.9.0` latest, CI
  green on `main`, ports free, Docker 29.8.1); truth pass on `STATUS.md` and the Sprint 13
  plan; the four answers and the Q4 follow-up; Sprint 14 registered in the governance
  `sprints.md` with its authorization paragraph and Sprint 15 listed; governance at
  `0.4.0-draft.14`; branch `sprint-14-research`; this plan; tasks claimed; the throwaway
  stack `oak-s14` healthy on 18080/15174; `pnpm --dir web build` green.
- [x] 2026-10-21 M0 exit: `journey.spec.ts` green on the throwaway stack (1 passed, 16.7 s).
- [x] 2026-10-21 M1: ADR-0018 in the governance tree and mirrored (both indexes, the
  traceability row); the egress rule in `AGENTS.md` and `security-invariants.md` now covers
  research sources; `TM-02`, `TM-04`, `TM-13` (rewritten), `TM-14` and `TM-17` extended in
  place, line numbers unchanged; `RR-048`–`RR-053` (register at 53, quoted in both `STATUS.md`
  files); Sprint 13's disclosure gaps closed (README report notes and limits, `STATUS.md`
  safety boundary, threat-coverage gap rows and "What changed" for `RR-044`–`RR-047`);
  `catalogue/research/` (capabilities, hardware classes, draft licences, draft harness list,
  two bindings) read by `ResearchVocabularyLoader`; `oak.compiler.derive_research_terms`
  with `terms_digest` and `classify_hardware`; `tests/unit/test_research_terms.py` (35) over
  the reference brief's intent, the example intent and four synthetic intents; `make
  validate`, the unit and contract suites and governance validation green.
- [x] 2026-10-21 M2: `research-snapshot` and `research-review` schemas (`0.1.0`) with
  examples, registered in `EXAMPLE_BY_SCHEMA`, `schemas/README.md`, both kind tables, the
  workspace-manifest enum and the export-lineage check (`oak.community/research_snapshot_ref`,
  `oak.community/research_review_refs`); `research_completed` and `research_item_reviewed`
  in the audit-event enum; the evidence-class enum and its `source_type` map in
  `oak.domain.research`, held equal to the schema by a contract test; an objective's
  `value` nullable with `unknown_reason` required exactly when null (`common.schema.json`
  `if`/`then`); the compiler writes `unknown` with a reason for an unpublished figure,
  never zero (objectives, hardware minimums, compatibility, deployment, target
  requirements), and only when a manifest carries `oak.community/research`; `_dominates`
  returns false whenever either value is unknown; `_apply_pareto` includes comparable
  candidates, names the uncompared objectives and records them on the comparison
  extension; `classify_comparison` is the typed compare-only rule; the report composer
  shows an objective's own reason with its unit and `oak architecture` prints `unknown`
  with the reason; the report schema takes 20 or 21 sections with appendix G, the two
  basis words and a unit on an unknown. Proof: `test_reference_digests.py` green (the
  four digests and the case digest unchanged), the report golden byte-identical, 16
  candidate-compiler tests including the K4 and compare-only cases, 8 contract tests in
  `test_research_contract.py` (a pre-change export imports unchanged), and the composer
  test for an unknown objective's reason. `docs/compatibility.md` classifies the change.
- [x] 2026-10-21 M3: `oak.domain.research_rules` (normalisation by allowlist, the
  family-token rule, the weight floor, the research gates with their `OAK-CAT-RESEARCH-*`
  reasons, the honest manifest), the curated eligibility rules moved into
  `oak.domain.catalogue_rules` and shared; `oak.adapters.models.research_sources` (the Hub,
  router and GitHub readers through the one transport, 30 requests under one 60-second
  deadline with per-kind size caps, the 24-hour in-memory cache keyed by the terms digest,
  stable refusals `OAK-RESEARCH-REDIRECTED|OVERSIZED|RATE-LIMITED|UNREACHABLE|BUDGET`,
  claims with evidence classes, pairings by family token, manifests and the snapshot);
  the transport's `RedirectRefusedError` carrying the 3xx status; the in-process
  `FixtureResearchSource` selected only by `OAK_RESEARCH_FIXTURES` (documented as
  safety-relevant) with offset dates; `create_research_source` in bootstrap, imported
  lazily; the recorded synthetic fixtures under `tests/fixtures/research/live` (absolute
  dates) and `e2e` (offsets); `scripts/check_research.py` (S1–S5) in `make validate`,
  mutation-checked; the adapter lists in `test_offline_boundary.py` and the test that a
  deterministic generation imports no research module. Proof: the acceptance case on
  fixtures with the clock at `2026-10-20T12:00:00Z` reports found 2, passed 1, needs
  review 1, pairs the model and the harness with four claim classes, and gives the same
  bytes twice; poisoned, lookalike, oversized, redirected and rate-limited inputs are
  refused with stable codes and a refused item is listed by digest only; a timed-out or
  refused run records one attempt and the fake transport's log shows no second request.
- [x] 2026-10-21 M3 live check (real egress, by hand, `OAK_LIVE_RESEARCH_TESTS=1`): the
  reference brief's derived terms went anonymously to `huggingface.co`,
  `router.huggingface.co` and `api.github.com`. The first run was refused after 6.9 s
  with `OAK-RESEARCH-OVERSIZED` (a GitHub release page; see Discoveries). After the
  recalibration (one release per repository, a 512 KiB cap on that answer) the second run
  passed in 7.1 s: the snapshot and every manifest validated, every request host was one
  of the three, and the run stayed inside 30 requests and 60 seconds. The printed summary
  of found, passed and unvetted counts was not kept (the console tail cut it); the M8
  run saves its summary to a file. A two-request size probe (the Hub listing: 66 384
  bytes for 50 entries; the router: 91 473 bytes for 138 routes) preceded the fix.
- [x] 2026-10-21 M4: `oak.application.research.ResearchService` (`plan`, `run`, `review`,
  `latest`), revising the case at `ready_for_candidates` with `research_completed` and
  `research_item_reviewed`; `oak.compiler.research_designs` (effective verdicts after the
  reviews; at most one design per binding, newest passing model, the paired harness in the
  serving role) and `compile_catalogue(..., research=)` (the merged snapshot
  `catalogue.research.<case>` under both rule sets, curated reasons kept as review items,
  blocking reasons still blocking); `generate_candidates(..., research_designs=)` numbering
  from `candidate-05` with the research and comparison extensions; the
  `research_catalogue` operation kind in all four places, submitted with one attempt; the
  control plane's `research_plan`, `submit_research` (token, consent, idempotency and
  `If-Match`, status, in that order) and `review_research_item`; the runner, the source
  factory and the vocabulary injected through `oak.ports.research`, so the application
  imports no adapter; `GET …/research-plan`, `POST …:research` (202) and
  `POST …:review-research-item`, listed as unreleased with their five schemas; the
  generated client's `researchPlan`, `researchCatalogue` and `reviewResearchItem` (the two
  mutations in G2); `oak research --plan | --consent <digest>` and `oak research review
  <item> --accept|--reject --rationale-file`, locally and with `--server` (the token from
  `OAK_MODEL_TOKEN`); interface rows in both repositories. Proof: 19 service tests (a
  wrong consent, a stale version and a repeated request send nothing, counted at the
  source; research from `candidates_ready` is refused; a second run keeps the first
  snapshot; reviews bound to digests; generation with and without the accept; the same
  snapshot and reviews give the same bytes in a fresh interpreter; an unresearched case
  still gives four candidates), 4 API tests (the token before the body, consent then
  version then status, one attempt, an idempotent retry, the review, `select` refusing
  `candidate-05` with `OAK-SELECT-INFEASIBLE`), 2 CLI tests (local and `--server`), and
  the PostgreSQL journey on the throwaway database (the worker runs the research once
  under its lease, a tampered research index entry is refused on import). PostgreSQL
  pass and skip counts are in the M4 integration line below.
- [x] 2026-10-22 M4 integration run with `OAK_TEST_DATABASE_URL` on the throwaway database
  (port 15433): 365 passed, 4 skipped, 0 failed. The four skips are the file backend's
  parametrisations of the PostgreSQL-only assertions in
  `tests/integration/test_workspace_repository_contract.py`; no research test skipped.
  (The first full run showed the PostgreSQL research journey failing on a tampered
  import answered 500; the `OAK-IMPORT-INVALID` mapping fixed it and the module was
  re-run twice, green both times.) `make format-check`, `make lint` and
  `make typecheck` were green at the commit.
- [x] 2026-10-22 M5: `web/src/ResearchMoment.tsx` (the consent card with hosts, verbatim
  terms and digest; **Run research** needing the capability token; the operation polled
  in place, never through the loading state; the result chips found / passed / need your
  review; each item with source, tier, date, verdict, reasons and every claim beside its
  evidence word; **Accept for comparison** / **Reject** with a rationale; focus moved and
  the change announced; no keycap once a snapshot exists), `CasePage.tsx` (a refresh in
  place), `CandidatesPage.tsx` (the New chip, "Balanced, new", the Source and Release date
  columns, evidence chips, an unknown's own reason, bars for a researched design, the
  compare-only sentence from `oak.community/comparison`), `DownloadsSheet.tsx` (the
  Research tile), `web/src/research.ts` (the evidence, tier, verdict, source and kind
  words and `whyNotSelectable`), the suffix `RESEARCHED_SUFFIX` in `ui/variantLabel.ts`
  and `report/labels.py` with `is_researched`, `is_baseline` false for a researched
  design, and three agreement tests (evidence words, suffix against the compiler's
  `LABEL_SUFFIX`, never a baseline). Proofs: `web/e2e/research.spec.ts` green on the
  throwaway stack with the fixture source (plan read, consent, run, the unvetted harness
  reviewed, generation, six designs with "Balanced, new", the table columns, the sheet;
  axe clean on seven screens); `journey.spec.ts` and `report.spec.ts` unchanged and
  green on the same stack; unit and contract suites 1080 passed; `make validate` (G1–G5,
  R1–R4, S1–S5) and `make web-build` green; tsc green.
- [x] 2026-10-22 M6: appendix G (`_appendix_research`: the run with its budget in words
  and its figures as quantities, the items table with the gates' verdict and the recorded
  review, a claims table per item with the evidence word and an array-index pointer, the
  outcomes, the pairings, every request), slide 2 naming the run and both rule sets,
  appendix E with the researched evidence under closed source-type words and the research
  snapshot, appendix F binding the snapshot, manifests and reviews through
  `records.gather_records` (reached through the catalogue snapshot the selected design
  names); the K4 rules (the chart names each option without a bar and why; best and worst
  skipped on an objective any feasible option leaves unknown; a differing unit makes the
  value unknown; the flag names the compare-only rule and the uncompared objectives); the
  six-option maximum and unique labels refused in `_Context`; `estimator_word` for a null
  estimator; the two declared golden moves (`source_type_word`, `FIXED_RENDERER` without
  `python-pptx` and the package docstring); `check_notes` and the narrator rule refusing
  superlatives; `fit()` on the PDF diagram's component label; the second golden
  `public-manual-qa-research.report.json` from `tests/report_support.build_researched_case`;
  `scripts/check_report.py` R5 and the research basis rule in R2 (`SYNTHETIC_SOURCES` gains
  `component.research.`); the research words mirrored in `labels.py` with agreement tests
  and `number_words`. Docs: `docs/research.md` (linked from the README table and limits, the
  docs index and the ADR index), the manual's section 2b with a real fixture-source
  transcript and the thirteenth figure's caption (the shot is captured at M7), threat
  coverage rows TM-02, TM-04, TM-13, TM-14 and TM-17 with the Sprint 14 test names, the
  CHANGELOG. Proofs: the reference golden moved only by the two declared changes (checked
  field by field before it was rewritten); the acceptance report records, validates and
  renders at six options with appendix G on its pages; no researched free text reaches
  `narrator_facts`; R1–R5 green live over both cases; the counts are in the M6 checks line.
- [x] 2026-10-22 M6 checks: `make format-check`, `make lint` and `make typecheck` green;
  `make validate` green (G1–G5, R1–R5 over the reference case at three stops and the
  acceptance case at two, S1–S5, the error reference regenerated); `make test` 1117 passed;
  the report, research and offline-boundary integration suites 57 passed (two
  offline-boundary tests first failed because `tests/report_support` imported the research
  readers at module level; they are imported inside `build_researched_case` now).
- [x] 2026-10-22 M7: the throwaway stack recreated from scratch (`docker compose down -v`,
  then `up -d --build --wait`, with the fixture source on `api` and `worker`); `make web-e2e`
  on it: 26 passed, 2 skipped (the two gated screenshot tests), in one minute, with
  `research.spec.ts` among them. Then exactly one screenshot run (`OAK_MANUAL_SCREENS=1`,
  `manual-screens.spec.ts`, 2 passed): the twelve figures recaptured on the same stack and
  the thirteenth, `assets/13-research.png`, captured by the spec's second test on the
  fixture source (it skips when the plan is not `fixture`, so a live run is never made for
  a picture); the figure shows the chips, both items, the harness's claims with their
  evidence words and the review form, as its caption says. Thirteen `shoot` calls, thirteen
  figures. The manual PDF rebuilt with the pinned Chromium (`build_manual.mjs`).
- [ ] M8 — closing review, gates, PR.

## Decisions

- 2026-10-21 M0, Q4. The owner's first answer, "selectable once reviewed", conflicts with
  §7 and needs an evaluation path that does not exist. One follow-up question offered:
  shown now and selectable next sprint; the compare-only rule now and selectable next; or
  selectable this sprint with the acceptance case rewritten. The owner chose the
  compare-only rule now and selection as Sprint 15, which is registered in the governance
  `sprints.md` with its prerequisites (a declarations review, an evaluation path for
  non-curated ids, installation image mapping, what `approved_for_context` requires).
- 2026-10-21 M0, the compare-only rule's shape (to be recorded in ADR-0018 at M1 and built
  at M2): `status` stays `infeasible`; the classification is typed in
  `extensions["oak.community/comparison"]`; `_apply_pareto` compares comparable
  candidates with unknown-aware dominance; `select` is unchanged. Alternatives: a new
  `status` value (a closed enum in the schema and the web; a conditionally compatible
  change for no gain) or a parsed reason string (refused by the Normalisation rules).
- 2026-10-21 M1, the hardware class. An intent that declares no accelerator list at all is
  `unknown`, not CPU-only: `absent` matches only a declared empty list. Alternative: treat a
  missing list as none, which would size a weight floor against hardware nobody declared.
- 2026-10-21 M1, the vocabularies are shape-checked in code, not by a JSON schema. They are
  internal data, not a contract any other reader consumes; the loader holds every value to a
  closed ASCII token shape and `test_research_terms.py` mutates each rule. A schema can be
  added if a second reader appears.
- 2026-10-21 M1, the hardware class is never sent. Neither source has a hardware qualifier,
  so the class is recorded under `local` in the terms and used only to compare a weight
  floor; the consent card shows it as used on this machine.
- 2026-10-21 M1, test citations in `threat-coverage.md` wait for the tests. The rows cite
  only tests that exist, so the research tests join `TM-02`, `TM-04`, `TM-13`, `TM-14` and
  `TM-17` at M6; the gap table and "What changed" are mapped now.
- 2026-10-21 M2, where a pending licence review counts. `classify_comparison` calls a
  failed licence constraint "pending" only when a researched manifest is in the design and
  every shortfall is a `pending` review or an `unknown` availability class; a curated
  manifest never stands on a pending review, and a `failed` review, a restricted class or a
  blocked licence is a real failure. The classification is computed from the manifests
  and the typed constraint results, never from a reason string.
- 2026-10-21 M2, commit ids and honest values (as ADR-0018 says). A researched manifest's
  `artifact.digest` holds a published asset digest or the digest of the source's own
  listing, with `extensions["oak.community/research"].digest_covers` saying which; the
  git commit id is `commit_id` in the same extension; no sha256 field ever holds one. A
  researched manifest publishes no `oak.community/objectives` figure it cannot stand on,
  so every objective of a design that holds it is `unknown` with the manifest named, and
  the router's price and throughput are shown as claims with their class, never as a
  monthly cost or a p95.
- 2026-10-21 M3, a licence is never sent. GitHub's `license:` qualifier takes one keyword,
  and combining three needs `OR` operators whose precedence beside other qualifiers is
  undocumented, while the search answer already carries each repository's detected
  licence. So the licence list is checked on this machine, the terms carry it under
  `local`, and `sent.github` holds topics, the archived flag and the freshness window only.
- 2026-10-21 M3, one search per kind and topic. A GitHub search `q` with `OR` between
  topics beside `pushed:` and `archived:` qualifiers has an undocumented precedence, so each
  topic is its own request (nine for three kinds of three topics), and each kind keeps its
  three most recently pushed hits. With one Hub tag the plan is at most 2 + 9 + 9 + 9 = 29
  requests, inside the budget by construction; a run that would need more is refused with
  `OAK-RESEARCH-BUDGET`, a fifth stable code beside the four the prompt names.
- 2026-10-21 M3, which refusal fails the run. A refused Hub listing, router read or search
  fails the run with its code and nothing else is sent; a refused release or commit read
  fails that one harness with `OAK-CAT-RESEARCH-UNREACHABLE` and the run goes on, so one
  repository's outage does not hide the rest. Nothing is retried, and no refusal is cached.
- 2026-10-21 M3, a refused item is listed by digest. An item refused for a forbidden word
  or a malformed id keeps its response digest and its reason and nothing else: no claim,
  no id and no family token, since those strings are what the refusal is about.
- 2026-10-21 M3, the gates and the manifest live in the domain. Adapters may not import the
  compiler, and the merged snapshot (M4) must apply the same gates, so the rules are pure
  domain functions both import; the curated eligibility rules moved beside them with
  byte-identical output (the four reference digests hold).
- 2026-10-21 M4, a manifest per run. A researched manifest's artifact version is its
  release version (the workspace's identity rule for `component_manifest`), and its content
  carries the time it was checked, so a second run of the same source would collide with an
  immutable artifact. Each run's manifests therefore carry the run's ordinal in their id
  (`…fixturelm-4b.run-1`): a later run is a later observation and keeps its own record.
- 2026-10-21 M4, the fixture clock. A fixture run measures no time: `elapsed_seconds` is
  `0.0` and the cache is not used, so two workspaces produce the same snapshot bytes and
  the acceptance golden (M6) is stable. A live run keeps its monotonic clock.
- 2026-10-21 M4, the fixture dates in service, API and CLI tests. Those tests run the worker
  on the support module's fixed clock (`2026-08-21`) or the real one, so they use the e2e
  fixture set with offset dates; the unit tests keep the absolute dates with the clock at
  `2026-10-20T12:00:00Z`, as the prompt's acceptance case states it.
- 2026-10-21 M4, the runner is a port. `tools/check_boundaries.py` forbids the application
  from importing an adapter even lazily, so `run_research`, the source factory and the
  source mode are injected through `oak.ports.research`; bootstrap wires the real ones.
- 2026-10-21 M4, reviews re-evaluate nothing. A review changes one verdict (`needs_review`
  to `passed` on accept, anything to `failed` on reject); the gates are not re-run at
  generation, so the snapshot stays the record of what the gates said at run time.
- 2026-10-21 M0, the throwaway override. Written with the ports only; the worker's
  `OAK_RESEARCH_FIXTURES` and the fixture volume are added at M3 once the directory exists,
  so Docker does not create an empty directory in the tree.
- 2026-10-22 M6, manifest ids on main slides. A researched design's rejection reasons and
  constraint reasons name its component manifests (`component.research.<source>.<slug>.run-n`).
  Those ids are OAK identifiers made by the allowlist normalisation (ASCII, bounded, no
  forbidden word), not an author's text, so the main slides keep them as the record states
  them; the test that no researched free text reaches `narrator_facts` strips them before it
  looks for the quoted claims, names, descriptions and the reviewer's rationale, all of which
  live in appendix G only.
- 2026-10-22 M6, a fixture snapshot's figures. The prompt's rule that every figure from a
  fixture research snapshot reads "synthetic estimate" applies to the run's own counts too
  (requests used, time taken), with the estimator `fixture-research-source` so R2's
  "an estimate names no estimator" holds; the budget itself is words, never a bare digit.
  A live snapshot's figures keep "published by source", "measured by source" or "counted".
- 2026-10-22 M6, the research records are reached through the design. `gather_records`
  reads the catalogue snapshot the selected candidate names (the case's own reference is
  the fallback), then the research snapshot that catalogue names, its manifests and the
  reviews bound to its digest, in that order after every other read, so an unresearched
  report's record appendix does not move. The planning service now carries the research
  snapshot reference with its media type into the merged catalogue and the designs.
- 2026-10-22 M5, the fixture source on both processes. The prompt's override mounts the
  fixtures on the worker only, but the API computes the plan the consent card shows and
  the worker re-checks the consent against its own plan before the first request; with
  the API in live mode the card would name the three real hosts while the worker expected
  none, and every run would be refused `OAK-RESEARCH-CONSENT`. The override therefore
  sets `OAK_RESEARCH_FIXTURES` and the read-only volume on `api` and `worker` alike.

## Discoveries and follow-ups

- 2026-10-21 M3, live. Symptom: the first live run was refused with
  `OAK-RESEARCH-OVERSIZED` after 6.9 s. Cause: a GitHub release page for a large runtime
  carries release notes well over the 128 KiB cap the prompt's "about 60 KB each"
  measurement suggested, and `per_page=2` doubled it. Fix: read one release per repository
  (the newest published one is all that is read) under a 512 KiB cap, and name the source
  kind in every refusal message so the next refusal needs no probe. The refusal itself
  behaved as designed: nothing was retried and no snapshot was written.
- 2026-10-21 M3, process. The live test prints its summary and the console tail dropped
  it. Lesson: pipe a hand-run live check to a log file in the scratchpad and read the file.

- 2026-10-22 M5, the agreement test's literal finder. `_object_literal` in
  `tests/contract/test_report_agreement.py` takes the first mention of a name, so a doc
  comment that names `EVIDENCE_WORDS` before its definition made the parsed map empty;
  the test passes `"export const EVIDENCE_WORDS"`. Worth remembering for any mirror whose
  module comment names it.
- 2026-10-22 M5, strict locators. The claims table's hidden caption repeats the item's
  source id, so an item-scoped `getByText` without `exact` matched two elements; the
  spec uses `{ exact: true }` for every word it looks for, as the prompt asks.

- 2026-10-22 M6, the chart text's limit. Naming every missing bar with its full reason ran
  past the chart description's 2,000 characters; the text now names each option once with
  the objectives it has no bar for and a short why, and the table beside it carries each
  cell's own reason (R3 still ties the two).
- 2026-10-22 M6, ruff drops an import it has not seen used yet. A patch that adds an import
  before the code that uses it, then runs `ruff check --fix`, loses the import; add both in
  one patch or fix after.

## Self-review

Answered at the end of each milestone: (1) did any pinned name change without its spec;
(2) did any claim appear without its evidence class, or any `unknown` without its reason;
(3) did anything touch a §7 boundary: egress, what leaves the machine, authority or
determinism?

- **M0.** (1) No. (2) None appeared; no code yet. (3) No egress: the stack build pulled
  pinned base images only, and no research request exists yet.
- **M1.** (1) No pinned name changed; `LocalCatalogue` keeps its behaviour and shares its
  bounded reader. (2) No claim exists yet; the hardware class `unknown` carries its meaning
  in the ADR and the docstring. (3) What leaves the machine is now defined, as data and a
  pure function, and nothing can send it yet: no transport call exists. The egress rule in
  both governance files was widened on purpose, and the deterministic path imports nothing
  new.
- **M2.** (1) No pinned name changed: the four reference digests, the case digest and the
  report golden are byte-identical, and every curated reason, label and id is as before.
  (2) Every `unknown` the compiler now writes carries a reason that names the manifest; no
  claim exists yet. (3) Determinism: the new code paths run only for a manifest that
  carries the research extension, and a test shows the designs without one are unchanged.
  No egress and no authority change; `select` is untouched and still refuses `infeasible`.
- **M3.** (1) No pinned name changed; the transport's redirect refusal keeps its code and
  message and only gains a typed status. (2) Every claim carries a class from the closed
  enum (S4 proves it live), and every gap in a manifest is the schema's honest value or
  the one sentence saying the source did not publish it; a refused item carries only a
  digest and a reason. (3) Egress now exists as code but nothing calls it yet: the live
  transport is built only by `create_research_source`, scoped to the three hosts (S1), and
  a deterministic generation imports neither reader. What leaves is unchanged from M1,
  minus the licence keywords, which are now local.
- **M4.** (1) No pinned name changed: the curated ids `00`, `01`, `03`, `04` and their
  bytes hold, an unresearched case gives four candidates, and the reference digests pass.
  (2) Every researched design names its snapshot, item, source, date, tier and evidence
  classes in `oak.community/research`; the comparison extension names every pending and
  unknown constraint and the objectives it could not compare. (3) Egress exists now and is
  gated in order: the capability token as a dependency, the consent against the recomputed
  plan, the idempotency key and version, the status, and the worker's own state check
  before the first request; one attempt, never retried. Authority: `select` is unchanged
  and refuses a researched design; a review admits an item to comparison only.
- **M5.** (1) No pinned name changed: `report.spec.ts` still finds "Balanced" for
  `candidate-03`, the curated labels and ids are untouched, and `journey.spec.ts` passes
  unchanged. (2) Every word the workspace shows for research is a closed one: the
  evidence words, tier words, verdict words, source and kind words, and the one suffix;
  a label is never built from a model or repository name, and the plain reason a design
  cannot be selected is derived from the typed comparison, never typed by hand. (3)
  Egress from the browser: the consent card shows the plan's own response verbatim, the
  run sends exactly `{hosts, terms_digest}` from it with the capability token, and the
  web gains the two non-GET calls G2 lists and no other. No button approves, signs,
  dispatches, installs or applies; a review admits an item to comparison only, and the
  Select keycap never appears on a researched design.
- **M6.** (1) The reference golden moved only by the two declared changes, proved field
  by field before the file was rewritten; `COMPOSER_VERSION`, `schema_version` and the
  twenty-section order for an unresearched case are untouched, and `report.spec.ts` still
  finds "Balanced". (2) Every research figure in a report carries its unit, its source as
  an array-index pointer and a basis the source can stand behind (or synthetic for the
  fixture), every claim its evidence word, every count a word; no number is invented for a
  figure no source published. (3) No egress and no authority change: the report is still
  composed from records alone, the main slides carry a researched design only by its id,
  closed label, evidence word, date, licence id and digest, and a researched option is
  flagged infeasible with the compare-only rule named.
