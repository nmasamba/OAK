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

- 2026-10-23 M4. Runner messages are believed only from an enrolled runner (F4-1): the
  operator pins each runner's public identity once (`oak-runner identity`, then
  `oak keys enroll-runner --identity <file>`), one file per runner under the trust
  directory's `runners/`, because the manual's two install sections use two runner homes
  against one trust directory. `oak ingest` refuses until one is enrolled. A completion may
  report only kinds its own envelope requested.
- 2026-10-23 M4. The consented research digest covers the source mode and the hosts as well
  as the terms (F1-1). This moves the researched report golden (the fixture terms digest is
  now `sha256:4b871ec5…`) and nothing on the deterministic path; the four reference
  digests are unchanged.
- 2026-10-23 M4. A revocation manifest keeps every entry the last signed manifest listed,
  whether or not the notice's file is still there, so a deleted notice leaves the runner
  denying until it is restored rather than re-signing the gap (F4-2).
- 2026-10-23 M4. The worker's lease is 120 seconds, twice the research deadline, rather than
  a heartbeat thread; one failed cycle is logged by code and retried (F2-2). A step that
  committed while cancellation was requested is recorded as succeeded with its result (F2-8).
- 2026-10-23 M4. A second or edited brief in a workspace, and a server create for a case that
  exists, are refused with a new non-retriable `OAK-CASE-EXISTS` (409) rather than the
  stale-version conflict (F1-6, F2-10). FastAPI's `/docs` and `/redoc` are switched off
  (F2-9). Every error response in the OpenAPI document names the `Problem` schema; the
  framework's validation schemas stay listed so no published name disappears (F2-7).

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

### Review findings (M3, 2026-10-23)

Four independent finders (local CLI F1, server and upgrades F2, web F3, runner and release
integrity F4) reproduced 64 defects. Each is re-checked against the code when it is taken
up, before anything changes; one that does not reproduce is marked refuted. The disposition
column is updated as each lands.

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| F1-1 | high | `oak research --consent` binds only the terms digest; hosts are copied from a recomputed plan | fixed (`7f1e62f`): the consented digest covers the source mode and hosts |
| F1-2 | high | JSON/YAML escapes put bidi and ANSI characters into the case, the GitOps description and the report | fixed (`37f711f`): refuse Cc/Cf in every parsed string of a brief, answers or target |
| F1-3 | high | Model-proposed rationales and values keep control characters; `oak questions` prints them raw | fixed (`37f711f`): a proposed claim carrying one is dropped; the CLI escapes model text |
| F1-4 | medium | `oak validate bundle` accepts an altered semantic manifest | fixed (`8ffc1fc`): its digest must match the bundle and every plan reference |
| F1-5 | medium | A bad `--idempotency-key` on local `oak design` creates the case, then fails, stranding it | fixed (`1c161f8`): the key is checked before anything commits |
| F1-6 | medium | A second brief in a workspace is refused as a retriable concurrency conflict | fixed (`1c161f8`): a non-retriable `OAK-CASE-EXISTS` naming the case (with F2-10, F3-6) |
| F1-7 | medium | The prose-brief hint suggests a re-run that is always refused | fixed (`8ffc1fc`): the hint says a model reading needs a new workspace |
| F1-8 | medium | Remote re-runs are refused with a state error; remote keys include the case version | fixed (`fd75afe`): remote keys derive from the same inputs as local ones |
| F1-9 | medium | `oak assure`/`oak plan` commit before checking `--output` | fixed (`8ffc1fc`): the destination is checked first |
| F1-10 | medium | An interrupted object write leaves a torn object; every retry reports a collision | fixed (`fd75afe`): write to a temporary file and link it into place; repair a torn object |
| F1-11 | medium | `oak research review --rationale-file` is read unbounded and unchecked | fixed (`0bb1bce`): bounded read; control characters refused in the service |
| F1-12 | medium | `oak extensions verify`/`activate` on an active policy pack fail against itself | fixed (`b0f3cc1`): the entry's own pack is excluded; activating an active version succeeds |
| F1-13 | medium | Remote `oak import` crashes on a non-list `artifact_index` | fixed (`0bb1bce`): `OAK-IMPORT-INVALID` |
| F1-14 | medium | `oak report --output` overwrites files and fails after `--record` committed | fixed (`8ffc1fc`): the destination is checked before recording; `-` is stdout |
| F1-15 | low | `oak gitops` and remote `oak export` write in place | fixed (`b0f3cc1, 572d674`): staged and renamed into place, owner-only |
| F1-16 | low | `oak policy evaluate --engine opa` replays a builtin decision | fixed (`fd75afe`): the engine is part of the request digest |
| F1-17 | low | `oak research --plan --case <other>` prints the current case | fixed (`0bb1bce`): refused |
| F1-18 | low | Two recovery hints print commands that do not work | fixed (`8ffc1fc`): quoted path; the architecture hint names a real step |
| F1-19 | low | `oak report | head` reports `OAK-INPUT-INVALID` | fixed (`0bb1bce`): a closed pipe exits quietly |
| F1-20 | low | Remote mode words two refusals worse than local | fixed (`0bb1bce`): `OAK-INTAKE-ENCODING`; the operation's own message |
| F2-1 | high | Import accepts any media type; the artifact read serves imported HTML inline in the API and web origins | fixed (`37f711f`): media type bound to kind on import; artifacts served as attachments under a sandbox CSP |
| F2-2 | medium | Worker leases are never renewed and the worker loop has no exception boundary | fixed (`e0ce87b`): a lease longer than any handler's deadline; the loop survives a failed cycle |
| F2-3 | medium | Schema-invalid REST input answers 500; create leaves a dangling workspace row | fixed (`1c161f8`): 422 `OAK-CONTRACT-INVALID`; the case id checked before anything is stored |
| F2-4 | medium | Research plan and run crash on a case with no intent | fixed (`1c161f8`): `OAK-RESEARCH-STATE` |
| F2-5 | medium | A brief id with upper case, `:` or `/` creates an unreachable server case | fixed (`1c161f8`): refused before anything is stored |
| F2-6 | medium | `:record-report` calls the model before a stale `If-Match` is refused | fixed (`1c161f8`): the version is checked first |
| F2-7 | medium | The OpenAPI contract misdescribes every error response | fixed (`065546e`): a Problem schema on every operation's error responses |
| F2-8 | medium | Cancelling a running operation reports `cancelled` although its change committed | fixed (`e0ce87b`): a committed step is recorded as succeeded |
| F2-9 | medium | `/docs` loads unpinned third-party JavaScript into the API origin | fixed (`fa02854`): the interactive docs are off unless asked for |
| F2-10 | low | Creating an existing case answers a retriable `OAK-EXPECTED-VERSION` | fixed (`1c161f8`): `OAK-CASE-EXISTS` (with F1-6) |
| F2-11 | low | An idempotency key reused with a different create or import body never conflicts | documented (`0065bc0`): create and import keys are scoped to the case the body names |
| F2-12 | low | `sequence_lag` compares maxima of different cases | fixed (`fa02854`): lag summed per case |
| F2-13 | low | A local export cannot be imported into a server (`OAK-IMPORT-SCOPE`), undocumented | documented (`0065bc0`), with the workaround |
| F3-1 | high | Decision shows the last-evaluated design's evaluation as the selected design's evidence | fix: the selected candidate's own evaluation, named |
| F3-2 | high | Reload after a conflict on the questions screen discards every draft | fix: drafts kept by question id |
| F3-3 | medium | The operation screen shows `unknown code` for every failure | fix: reads `problem.code`; no next attempt once terminal |
| F3-4 | medium | A stale model token strands the Models screen | fix: the token can be replaced or forgotten; wording by purpose |
| F3-5 | medium | The research card's Settings link is a dead route | fix |
| F3-6 | medium | Reusing a brief name is reported as a stale view | fix: names the existing case (with F1-6) |
| F3-7 | medium | Focus falls to body on every in-app move to a case screen | fix: the heading is focused when the page is ready |
| F3-8 | medium | Done, Edit and Clear decision drop keyboard focus | fix |
| F3-9 | medium | Interpret and Create the assurance plan reload the page | fix: refreshed in place and announced |
| F3-10 | medium | Confirm and Accept the risk send the placeholder `(not set)` | fix: the claim's own value; unavailable for an unset claim |
| F3-11 | medium | One failed poll ends the operation screen | fix: keeps polling with backoff |
| F3-12 | medium | A refused Select or Evaluate is reported far below the button | fix: shown in the card |
| F3-13 | medium | The home screen lists only the first page of cases | fix: follows the cursor |
| F3-14 | medium | A refused or failed download is never announced | fix: one announced outcome everywhere |
| F3-15 | medium | Long identifiers overflow cards and phone-width screens | fix |
| F3-16 | low | The target profile hint names a YAML file; the field takes JSON | fix: a visible JSON example |
| F3-17 | low | Raw document views render raw variant ids | fix: the raw views go; the Take it sheet hands over the files |
| F4-1 | high | `oak ingest` accepts a completion signed by any key and believes its claims | fixed (`f995c5b, 7bcf96c`): the runner key is enrolled and pinned; a completion is bound to its envelope |
| F4-2 | high | A later revocation re-signs whatever notices are in the mailbox | fixed (`f995c5b`): the manifest is built from the case's own record |
| F4-3 | medium | Separation of duties compares role-scoped ids, so it never fires | fixed (`f995c5b`): compares key material; refused at pinning and at approve |
| F4-4 | medium | Configuration read-back passes privileged and bind-mounted containers | fixed (`b0f3cc1`): an allowlist over the whole host configuration |
| F4-5 | medium | Overlapping or resumed runs corrupt a journal | fixed (`f995c5b`): a run lock; a finished journal is only marked processed |
| F4-6 | medium | A dispatch name with `..` wedges the runner | fixed (`f995c5b, 1c161f8`): refused at delivery; unsafe entries skipped |
| F4-7 | medium | `oak ingest` acknowledges every message before recording any | fixed (`f995c5b`): record, then acknowledge, one at a time |
| F4-8 | medium | Denial completions are always rejected | fixed (`f995c5b`): published with their lease and recorded |
| F4-9 | medium | A refused delivery still records the lease, and ingest adopts another workspace's completion | fixed (`f995c5b`): deliver before committing |
| F4-10 | medium | The GitOps description lists revoked approvals as on file | fixed (`b0f3cc1`): each approval's state |
| F4-11 | low | The denial path builds a message path from the unverified lease id | fixed (`f995c5b`): safe message names |
| F4-12 | low | `oak-runner status` cannot detect a cut journal tail | documented (`9076a18`) as a residual risk |
| F4-13 | low | Any `pack.yaml` under `extensions/active/` is used unverified | fixed (`b0f3cc1`): only an activated, digest-matching pack |
| F4-14 | low | The scanner image is pinned by a mutable tag | fixed (`b0f3cc1`): tag and digest, recorded in the evidence |

## Self-review
