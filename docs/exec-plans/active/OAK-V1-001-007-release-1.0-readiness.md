<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-001–007: 1.0 readiness — coherent documentation and a reviewed, polished product

**Directed by the owner on 2026-10-23**, in their words: "ensure coherence of documentation,
then thoroughly review and polish functionality in anticipation of publicly releasing
version 1.0". The work starts from `origin/main` at `a479780` (the merge of PR #37, Sprint
14). `0.9.0` is the latest published release (GitHub Releases only); nothing here bumps the
version, cuts a tag or publishes anything.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-23
- Last updated: 2026-10-23 (M1–M4 in progress)
- State: in-progress
- Claimed tasks: `OAK-V1-001`–`OAK-V1-007`

One plan covers seven task IDs because they are one pass over one tree, judged by one set of
gates: the documentation is made coherent first, then every interface is exercised and
reviewed, the verified findings are fixed, and the result is handed to the owner with the
list of what only they can do to cut 1.0. It follows the precedent of the pre-launch
hardening (`OAK-PL-001`–`007`) and the final sweep (`OAK-FS-001`–`003`): a release-readiness
series of its own, so the planned Sprint 15 keeps its number.

## Outcome

After this plan:

1. Every document in both repositories agrees with the code and with every other document:
   states and dates, versions, commands and the output they print, routes, variables,
   counts, cited tests, risk entries and ADR mirrors. A reader who follows the README, the
   tour or the manual on the current tree gets what the page says they will get.
2. Every interface's main journey has been run end to end on the current tree — the CLI
   locally and with `--server`, REST, MCP, the web workspace, the signed runner, install and
   observe, the report and research — and what was rough is fixed with a test or recorded.
3. A reviewed list of defects found by independent finders, each verified before any fix,
   each fix carrying a test.
4. The owner holds one list of what remains to cut 1.0: the decisions and acts that are
   theirs, with what each would take.

Demonstrated by: the mechanical documentation checks (links and anchors, cited tests,
cited files, command names) green and kept as a guard where cheap; the walkthrough log and
the review table in this plan; `make check` with the test database and `make audit`;
`make web-e2e` on a fresh throwaway stack; a PR with CI green.

## Context and invariants

- **Assumptions this pass does not settle** (owner decisions, listed in the readiness
  section at M5): the `VERSION` bump and its touch-list; whether 1.0 changes the
  compatibility policy's pre-1.0 wording and promises; the release decision record and its
  three signatures; the publication channels (GitHub Release, PyPI, an image registry);
  the review of the draft harness list.
- **Invariants.** The four reference digests and the reference report golden stay
  byte-identical unless a fix declares the move; no production or customer readiness claim
  anywhere; no authority bypass; the default path stays deterministic and offline; exactly
  one egress module; no AI-vendor attribution in public-facing documentation (the final
  sweep's rule: neutral descriptions, history left as history); `make check` is judged by
  counting `make: ***` lines, never by exit code, and never two at once; the owner's
  `oak-community` Compose stack and its database are never touched (a throwaway project
  only).
- **Requirement and ADR scope.** Documentation follows the "Documentation and ADR" recipe in
  `skills.md` ("no stale readiness/licence/production claim remains"); behaviour fixes follow
  the recipe of the module they touch. Nothing planned changes a contract; a fix that must
  is listed under Contract and data changes first.

## Scope

### In

- Both repositories' documentation: the implementation README, CONTRIBUTING, SECURITY,
  CHANGELOG and STATUS; `docs/` including the manual, the security records, the ADRs and
  their mirrors; the schemas, examples and catalogue READMEs; the governance repository's
  status, roadmap, handbook, backlog, traceability and build documents.
- Behaviour fixes and polish across the CLI, REST, MCP, the web workspace, the runner,
  install and observe, the report and research, each with a test.
- A cheap documentation guard if the mechanical checks find drift a test can hold.

### Out

- New features: Sprint 15 (selecting a researched design), native installation, hardware
  scanning, the backlog in `sprints.md`.
- The version bump, a tag, a release decision record, publication of any kind.
- A change to the compatibility policy's promises; a new dependency (unless a security
  advisory forces an upgrade, as `make audit` did in Sprint 14).
- Rewriting merged history.

## Contract and data changes

None planned. Checked at kickoff: the pass is documentation, behaviour polish inside
existing contracts, and tests.

## Milestones

### M0 — Kickoff and truth pass (`OAK-V1-001`)

- Work: the branch from `origin/main`; this plan; the series recorded in both `STATUS.md`
  files, `IMPLEMENT.md` and the governance changelog; the post-merge truth pass (Sprint 14 is
  merged as PR #37 at `a479780`, so every "awaiting the owner's merge" and "in progress"
  about it is now false).
- Proof: `scripts/validate_repo.py` and `make validate` green.
- Rollback: revert the kickoff commits; nothing else depends on them.

### M1 — Documentation coherence (`OAK-V1-002`)

- Work: mechanical checks over every Markdown and HTML document (local links and anchors,
  cited test names, cited source paths, `oak` subcommands, `OAK_*` variables and `OAK-*`
  codes against the code); a semantic sweep in four clusters by independent readers
  (journeys, reference, records, governance), every finding verified before it is fixed.
- Proof: the checks green; the findings table in this plan.
- Rollback: documentation only.

### M2 — Walkthrough (`OAK-V1-003`)

- Work: run every documented journey on the current tree and record what each step really
  does.
- Proof: the walkthrough log in this plan, with the commands and outcomes.
- Rollback: none needed; nothing is changed by running.

### M3 — Review (`OAK-V1-004`)

- Work: independent finders by subsystem, briefed with what the walkthrough showed; every
  finding verified by reproducing it before it is accepted.
- Proof: the review table (raised, verified, refuted, fixed).
- Rollback: none needed.

### M4 — Fixes and polish (`OAK-V1-005`)

- Work: each verified finding fixed with a test, in the smallest change through the real
  boundary; documentation follows each fix.
- Proof: the tests; the goldens unchanged unless a move is declared here first.
- Rollback: one commit per coherent group of fixes.

### M5 — The 1.0 readiness list (`OAK-V1-006`)

- Work: what remains to cut 1.0 that only the owner can decide or do, with what each takes.
- Proof: the list in this plan, linked from both `STATUS.md` files.
- Rollback: documentation only.

### M6 — Gates and PR (`OAK-V1-007`)

- Work: `make check` with the test database, `make audit`, `make web-e2e` on a fresh
  throwaway stack (the manual's screenshots after one suite run and its PDF if the
  workspace changed), the plan to `completed/`, both `STATUS.md` files, the changelogs, a
  PR with CI green. The merge is the owner's.
- Proof: zero `make: ***` lines; CI green on the PR.

## Verification

- Documentation: the mechanical checks; every command a document tells a reader to run is
  run on the current tree, and its printed output compared with the page.
- Behaviour: each fix has a test on its failure path as well as its happy path, plus the
  idempotency and authorization paths where they apply; the full gates once at the end.
- The browser suite on a fresh throwaway stack; the hand-run live research check only if a
  fix touches research egress.

## Security, privacy and authority review

The pass changes no authority, no egress and no data boundary by design. Every fix is
reviewed against the Code Review Rules in `AGENTS.md`. Documentation must not claim a
control the code does not enforce, nor omit a residual risk the code still has: the
residual-risk register is checked against the code in both directions.

## Operational and rollback plan

Local-only change; the failure surface is the branch. Each milestone is its own commit
group and can be reverted alone. No migration, no flag, no release.

## Progress

- [x] 2026-10-23 M0 — kickoff and truth pass: branch `release-1.0-readiness` from
  `origin/main` (`a479780`); this plan; the series in both `STATUS.md` files, `IMPLEMENT.md`,
  `docs/roadmap.md`, a note in `sprints.md` and the governance changelog (`0.4.0-draft.15`);
  Sprint 14 recorded as merged everywhere it was "awaiting the merge" or "in progress", and
  the governance STATUS's stale `active/` path for its plan corrected. `validate_repo.py`,
  `make validate` and `tools/check_repository.py` green.
- [ ] M1 — documentation coherence.
- [ ] M2 — walkthrough.
- [ ] M3 — review.
- [ ] M4 — fixes and polish.
- [ ] M5 — the 1.0 readiness list.
- [ ] M6 — gates and PR.

## Decisions

- 2026-10-23 M0. A release-readiness series (`OAK-V1-001`–`007`) rather than a sprint,
  following `OAK-PL` and `OAK-FS`: the backlog's planned Sprint 15 (selecting a researched
  design) keeps its number, and `spec-manifest.yaml` names no `next_task`, since every
  sprint task is delivered and the validator allows null in exactly that case.
- 2026-10-23 M1. While the independent readers and finders read the main checkout, every
  edit goes to a separate worktree on branch `v1-fixes`, merged into `release-1.0-readiness`
  once they report: their line numbers stay valid and nothing they read changes under them.
- 2026-10-23 M4. A server started without `OAK_DATABASE_URL` keeps starting (readiness
  already reports 503 then, and `/version`, the health checks and the model settings need
  no database), and every design-case route now refuses with a new code,
  `OAK-DATABASE-UNCONFIGURED`, answered as 503. `OAK-DATABASE-CONFIG` stays the startup-only
  refusal of `oak-db-migrate`, as `docs/error-codes.md` describes it.
- 2026-10-23 M4. A missing input file keeps its existing `…-UNSAFE-PATH` code (scripts may
  match on it) and gains a message that says the file does not exist.
- 2026-10-23 M0. No version bump, tag, decision record or publication, and no change to the
  compatibility policy: the owner asked for this pass "in anticipation of" 1.0, and each of
  those is an owner act. They are prepared as the readiness list instead.

## Discoveries and follow-ups

### Mechanical documentation checks (M1, 2026-10-23)

A read-only script over the 151 Markdown and HTML documents in both repositories: local
links and anchors, cited test files and test names, cited source paths and line ranges,
`oak` commands and options against the CLI's own command tree, `OAK_*` variables against
the code that reads them, and AI-vendor names. What it found, after removing false
positives (MCP method names read as paths, the Vite entry script, a negative mention of
`oak apply`, vendor names that are Sprint 9 provider facts inside dated records):

- `docs/security/threat-coverage.md` TM-13 attributed
  `test_a_deterministic_report_never_imports_a_hosted_model_module` to
  `test_model_preflight.py`; it lives in `test_offline_boundary.py`. Fixed.
- TM-20 cited a nonexistent `tests/unit/test_secrets.py` "equivalent coverage inside"
  `test_model_configuration.py`; the redaction tests are
  `tests/unit/test_credential_store.py::test_secret_value_never_renders_its_content`. Fixed.
- The governance `STATUS.md` reading-order paragraph still had Sprint 14 in progress with its
  plan under `active/`. Fixed with the governance findings below.
- `OAK_LIVE_RESEARCH_TESTS`, the hand-run research check's gate, was documented nowhere public;
  `docs/configuration.md` and `CONTRIBUTING.md` now name it, and the configuration contract
  test knows it is read by the test suite.

### Walkthrough log (M2, 2026-10-23)

Run on `release-1.0-readiness` at `e23d005`, with a throwaway Compose project `oak-v1`
(API on 18080, web on 15174, the fixture research source on `api` and `worker`).

| Journey | Result |
|---|---|
| Tour Part 1, offline CLI, brief to bundle and export | Every printed line matches `docs/tour.md`; semantic fingerprint `sha256:2ef34758…34d63` |
| Tour Part 2, browser/REST, `curl`, remote CLI, MCP over `docker compose exec` | Every printed line matches; the audit trail and the export fingerprint are identical to Part 1 |
| Tour Part 3, the MCP tool list | The eleven tools, exactly |
| Tour Part 4, REST headers, `/docs`, ETag | As described; the 16-character idempotency key and the stale-version refusal hold |
| Manual ch. 6, the signed runner on the mutation fixture | Keys, sign, four approvals, dispatch, `run-once`, ingest, `oak-runner status`, revoke: as printed (dispatch numbers 14 and 12 reproduce) |
| Manual ch. 6, install, observe and rollback on the started fixture | Containers installed, smoke-tested, observed and removed; nothing left behind |
| Manual ch. 3, the report and export/import | `oak report --record`, the PDF and JSON downloads (digests match), export and import work |
| CLI failure paths (outside a workspace, wrong state, missing inputs, local-only over `--server`, server down) | Stable codes, no tracebacks, apart from the findings below |
| REST failure paths (unknown case or route, bad JSON, short idempotency key) | Stable codes and statuses |

Findings from the walkthrough (verified by running them; fixed in M4 unless noted):

- **W-1 (docs, low).** Manual ch. 6: the sample `oak observe` output shows the repeated
  install (`EV-DEP-02 pass (1/1)`, smoke test `2/2`) that the prose makes optional and no
  code block runs; following the blocks prints `unknown` and `1/1`.
- **W-2 (docs, low).** Manual ch. 3: the export example prints `@0.1.7`, but the step
  before it (recording the report) moves the case to `0.1.8`.
- **W-3 (CLI, low).** `oak import` prints the destination unnormalised
  (`…/tour-offline/../restored`).
- **W-4 (web, low).** A page opened directly shows the browser's focus box around its
  `h1` (the programmatic focus after navigation): the home page and Models.
- **W-5 (web, low).** The brass link keycap inside a moment ("Answer the 5 ranked
  questions") sits its label against the top edge instead of centring it.
- **W-6 (web, low).** Candidate cards run each satisfied requirement's reason straight into
  its requirement ids ("…snapshot policy.Requirements: OAK-FR-CAT-001").
- **W-7 (web, low).** The Online AI "not ready" reason shows literal backticks around
  `oak models set-key` and tells a reader on Settings to "store one in Settings".
- **W-8 (web, low).** Question cards and the claims table show raw escaped JSON pointers
  (`/spec/data/extensions/oak.community~1production_data_permitted`).
- **W-9 (web, low).** The operation page's heading is the raw kind in lower case
  ("generate candidates").
- **W-10 (docs, low).** The tour's REST summary lists generate, evaluate and compile as the
  slow jobs; research is one too.
- **V-1 (API, medium).** `oak serve` (and `oak-api`) without `OAK_DATABASE_URL` starts,
  then answers every design-case request with `500 OAK-INTERNAL` and logs a traceback: the
  control plane raises a bare `RuntimeError`. Its help still calls it "the read-only local
  API harness"; it serves the full REST API.
- **V-2 (CLI, low).** `oak research --plan` ends with "To run: oak research --consent …"
  even when its first line says research is not allowed at the case's status.
- **V-3 (CLI, low).** `oak models status`, a read, aborts with
  `OAK-MODEL-KEYCHAIN-UNAVAILABLE` when the configuration names the keychain but the
  keychain library is absent from the running environment.
- **V-4 (CLI, low).** A missing brief or answers file is reported as
  `OAK-INTAKE-UNSAFE-PATH` / `OAK-CONFIRM-UNSAFE-PATH` "must be a regular non-symlink file";
  the code is right, the message never says the file does not exist.

All fourteen are fixed on `v1-fixes` (`71015b7`, `edb20e6`, `a16d160`): W-1 by showing the
repeated install the sample assumes (run on the started fixture, it prints exactly the
manual's sample), the rest as described in the commit, each behaviour change with a test
(`tests/integration/test_api.py`, `test_research_cli.py`, `test_cli_inputs.py`,
`tests/unit/test_intake.py`, `test_model_configuration.py`); the workspace changes are
checked by `tsc`, the G1–G5 guards and, at M6, the browser suite and the recaptured figures.

## Self-review
