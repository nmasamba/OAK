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
- Last updated: 2026-10-23 (M0)
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
- 2026-10-23 M0. No version bump, tag, decision record or publication, and no change to the
  compatibility policy: the owner asked for this pass "in anticipation of" 1.0, and each of
  those is an owner act. They are prepared as the readiness list instead.

## Discoveries and follow-ups

## Self-review
