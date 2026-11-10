<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-046: a coherence sweep, so that both repositories say what the code does

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-11-10
- Last updated: 2026-11-10
- State: in-progress
- Claimed tasks: `OAK-V1-046`

## Outcome

The owner asked on 2026-11-10 for a skill that keeps code and documents coherent across the
repository, and for it to be used in a final sweep. After this plan, the original spec repo has
a **Coherence sweep** recipe in `skills.md`, a lead generator in `scripts/coherence_report.py`
and a validator rule for the drift it found twice, and every living document in both
repositories agrees with the fact sheet below and with the code. A reader can check that by
running `python3 scripts/coherence_report.py` from the spec repo's root.

## Context and invariants

The recipe's rules apply: living documents follow the code; records (completed plans, release
decisions, released changelog sections, merged commits, dated prompts) are not rewritten;
generated files are regenerated; a mirrored ADR changes in the spec repo first. The sweep
changes no behavior: where the code is wrong, it records a follow-up.

## Fact sheet (2026-11-10)

- `main` is `3fa08b7`, PR #46's merge. PRs #42 to #46 are all merged; none is open.
- Releases: `0.9.0` (latest, 2026-10-01) and `0.7.1`; tags `v0.7.1`, `v0.8.0`, `v0.9.0`.
- Versions: the implementation is `0.9.0`; the spec repo is `0.4.0-draft.24`.
- No plan is active but this one.
- The consent text `consent.native-installation` is `0.1.0`, `draft`, digest
  `sha256:bbed21d565009b414adf4e6eb0ee0cbdb22f5682294a34f9afb18db11daa0603`. Its sign-off is
  the owner's and, with PR #46 merged, no longer waits on anything.
- The residual-risk register has 57 entries.
- Next, per the owner's answers: the consent sign-off, then Batch C's Sprint 15, then the 1.0
  readiness list.

## Scope

### In

- The recipe, the report script and the validator rule in the spec repo, and a thin skill that
  runs the recipe.
- Every living document in both repositories, the error reference's hand-written table, and
  docstrings and help text that state facts.

### Out

- Behavior changes, history rewrites, branch deletions and the consent sign-off: each is
  recorded for the owner.

## Contract and data changes

None intended. Any found necessary is recorded as a follow-up.

## Milestones

### Milestone 1 — the skill

- Work: the recipe, `scripts/coherence_report.py`, the `STATUS.md` version rule in
  `scripts/validate_repo.py`, the skill wrapper.
- Proof: the report runs against this branch's worktree; the spec validator passes.

### Milestone 2 — the sweep

- Work: the leads and four partitions read; each finding confirmed, then fixed or recorded.
- Proof: the findings table below, and the report's remaining leads each judged.

### Milestone 3 — the gates

- Proof: `make validate`, the contract tests and the spec validator for text; `make check` if
  code or tests changed.

## Verification

The report before and after; each fix checked against its source; the gates above.

## Security, privacy and authority review

Text only. The sweep must not weaken a security statement to make it agree with another
document: where a document and the code disagree on a control, the code decides and the
finding names the control.

## Operational and rollback plan

Revert the branch. The spec repo's edits are listed in its changelog.

## Progress

- [x] 2026-11-10 PR #46 merged (`3fa08b7`). Branch `coherence-sweep` cut from it.
- [x] 2026-11-10 M1. The recipe, the report and the validator rule. The report's first run gave
  91 leads, 76 of them its own false positives (requirement ids read as error codes, the spec
  repo's description of the implementation's tree, a research digest read as the native
  consent's, and long status lines read across clauses); fixed, it gives 20.
- [x] 2026-11-10 M2. The fact sheet; the status and planning partition read here; the user
  documentation, the reference documentation and the specification read by three readers in
  parallel, each given the recipe's brief and the fact sheet. Every finding below was
  confirmed against the code before it was fixed. The report found two defects in itself on
  the way (state documents resolved before `--implementation` applied; a task recorded in
  another plan reported as planless), and gained a check for a plan the status file does not
  name. After the fixes it reports five leads, each judged below.

## Findings

Grouped where one fact was wrong in several places. Paths without a repository are the
implementation's; `spec:` marks the original spec repo.

| # | Where | Class | Finding, with its evidence | Fix |
|---|---|---|---|---|
| 1 | `STATUS.md`; spec: `STATUS.md`, `IMPLEMENT.md`, `docs/roadmap.md`, `sprints.md` | stale | Batch B "open as PR #44" (merged 2026-11-04), #46 "open" (merged 2026-11-10), Batch B's plan "active" (in `completed/`), Batch A "the most recent completed" plan; the completed-plans list stopped at `OAK-V1-021`; the next task still a merge | Each sentence rewritten from the fact sheet |
| 2 | `README.md`, `docs/tour.md`, the manual, `docs/interfaces.md`, `docs/architecture.md` | stale | "11 tools": `src/oak/interfaces/mcp/tools.py` registers 12 with `oak_hardware_propose`, and `tests/contract/test_mcp_contract.py` pins them | 12, with the tool described |
| 3 | The manual (four places), `README.md` (three), `CONTRIBUTING.md`, `docs/signed-runner.md` | stale | The runner described as Docker-only, its sole mutation a container; four mutation profiles ship, two of them native (`examples/targets/local-native-*.yaml`), and the llama.cpp one downloads | The native path named in each, with the fourth profile and native recovery |
| 4 | spec: `docs/build/interface-contract.md` (five places), `docs/build/security-invariants.md`, `docs/threat-model.md`, `architecture.md`; `docs/architecture.md`, `schemas/README.md` | stale | The approvals an install needs omit `native_consent`, which `schemas/approval.schema.json` names and `runner/verification.py` requires for a native `apply` | Added where the approval set is stated |
| 5 | spec: `docs/build/security-invariants.md`, `AGENTS.md`; `docs/security/threat-coverage.md` | false | "That two-module set", "only through the transport", an allowlist that "gained exactly one entry": `tests/integration/test_offline_boundary.py` allows four modules, the native downloader and the stand-in among them | The four named, and what the downloader may reach |
| 6 | spec: `docs/threat-model.md` TM-09, TM-16 | overclaim | The native install "journals each download, start and stop" (`native.py` writes no journal; `execution.py` journals each operation) and "runs only as the user who signed" (nothing compares the user) | Said what the journal and the consent do |
| 7 | spec: `docs/threat-model.md` TM-02; `docs/security/threat-coverage.md` TM-18, TM-19 | stale | Starting is described for containers only, "no network" for every installed component; `RR-055`–`RR-057` unmapped | The native clause and the register's rows mapped |
| 8 | spec: ADR-0019 | false | "`oak observe` on a native installation starts it, probes it and stops it": `record_observation` reads ingested evidence only | Corrected and dated; re-mirrored |
| 9 | spec: ADR-0015; ADR-0018 and ADR-0019 mirrors | contradiction, dangling | ADR-0015 forbade downloaded code with no word of ADR-0019's exception; the mirrors cited `AGENTS.md`, `skills.md`, `sprints.md` and a build doc the implementation does not hold | The exception noted; the citations named as the spec repo's; re-mirrored |
| 10 | spec: `docs/build/interface-contract.md` | stale | Six REST routes in `openapi/oak.openapi.json` missing from its table, `workspace status|migrate` from its local-only set | Added |
| 11 | `SECURITY.md` | false | "There is no quota or rate limiter": `RR-024` and `RR-041` are bounded since Batch A | Scoped to load beyond the limits |
| 12 | `docs/development.md`, `CONTRIBUTING.md`, `docs/platforms.md` | stale | "Thirty" database-gated tests: `tests/expected-skips.json` counts 31 | 31 |
| 13 | `README.md`, the manual, `docs/operations.md` | drift | **Copy install steps** "copies the six commands" and `oak architecture` shows "the two approvals": a native plan has eight (`BundlePage.tsx`) and three | Both cases said |
| 14 | `README.md`, the manual | stale | The unreleased-work lists left out the scan, native installation, limits and migration | Completed |
| 15 | `docs/performance.md` | contradiction | "Never over an earlier report", then a command that overwrote `docs/release/0.9.0/performance.json` | A dated path under `docs/performance/`, as its other measurement uses |
| 16 | `docs/configuration.md`, `docs/operations.md` | false | The runner home's contents: "processed dispatches" (their markers are in the mailbox), no `runner.key`, `run.lock` or `native/` with its `api-key.txt`; the runner id "recorded in leases" (it is in each message) | Corrected; the backup row says what `native/` holds |
| 17 | `docs/development.md` | drift | G2's mutations list missed `confirmHardware` (`scripts/check_studio_ui.py`) | Added |
| 18 | `README.md`, `CONTRIBUTING.md` | drift | llama.cpp serving "on the backlog" while a native profile runs it | The backlog item is a renderer |
| 19 | `README.md`, the manual | false | `~/.oak` written "only once you use keys, models or the runner": `oak serve` and the API mint a token there at every start | Said |
| 20 | The manual | contradiction | Its candidates table showed research's candidates while the chapter's versions come from a run without research | The table without them, and a sentence on research |
| 21 | `docs/interfaces.md` | false | "The runner resolves them locally": it refuses any secret reference (`OAK-RUNNER-SECRETS`) | Said |
| 22 | `docs/architecture.md` | stale | Execution sites, the local-only list and the runner's checks were container-only | The native adapter, the scan and `workspace` added |
| 23 | `docs/platforms.md`, `docs/security/residual-risk.md` | contradiction, stale | "Where `0.9.0` is supported" over rows of unreleased work; "`RR-044` to `RR-054`" over 57 entries; `RR-055` without `docker version` | Scoped; `RR-057`; the tool named |
| 24 | `docs/signed-runner.md` | drift | The contractual order: the pre-step-0 handling and the per-kind `OAK-RUNNER-OPERATION` and step-7 checks were unstated | Documented as the code runs them; no check moved |
| 25 | `docs/compatibility.md` | stale | Batch B's new codes named two of eighteen; the CLI's exit `141` (`main.py:3044`) missing | Listed |
| 26 | `scripts/generate_error_reference.py`, so `docs/error-codes.md` | false | Six licence codes built from a template were missing from "every code"; the runner's exits said `70` for a refusal (a denial exits `0`); the SMOKE and STOP rows said the install is always removed | The templates declared; the text corrected; regenerated |
| 27 | `docs/security/threat-coverage.md` | dangling | A test name that does not exist and a line-number citation into the spec repo | The real name; the citation by content |
| 28 | spec: `architecture.md`, `docs/build/security-invariants.md` | contradiction, overclaim | "First release `0.7.1`" against ADR-0002's `0.7.0`; OpenTelemetry presented as in place; the allowlist without the native adapter's programs | "First published"; the telemetry row annotated with its status; the exception named |
| 29 | spec: `docs/build/testing-strategy.md`, `docs/build/repository-layout.md`, `docs/traceability.md` | false, stale | `make format` and `make validate` claimed Markdown formatting and links; `sbom/` listed as tree content; the DEP and SEC rows without ADR-0019 | Corrected |
| 30 | spec: `skills.md` | drift | The new recipe placed the assurance vocabulary in `tools/check_repository.py`; it lives in `src/oak/domain/vocabulary.py` | Corrected |

**Leads judged and kept as they are:** `docs/build/repository-layout.md` names `tests/property/`,
`tests/security/` and two `deploy/` folders in a sentence that says they do not exist;
`web/test-results/` in `docs/development.md` is Playwright's git-ignored output;
`docs/security/threat-coverage.md`'s citation of the spec repo's threat model resolves there;
`sprints.md`'s Sprint 10 task naming `active/` is history; and `RR-027`, a closed entry,
keeps its wording about the runner home, as a record.

## Decisions

- 2026-11-10 **Where the skill lives.** The implementation refuses agent-specific files by
  design (`tools/check_repository.py`), so the recipe goes into the spec repo's vendor-neutral
  `skills.md`, the script beside its validator, and only a thin wrapper into the spec repo's
  `.claude/skills/`, as `CLAUDE.md` points at `AGENTS.md`.
- 2026-11-10 **The skill was tested by its use, not by a separate evaluation loop.** Running
  the same sweep with and without the skill would cost two whole-repository sweeps; this sweep
  is the test, and the report's false positives were fixed from what it found.

## Discoveries and follow-ups

- **Behavior, for its own task:** the runner's `inventory` scan does not use the run's executor.
  `src/oak/runner/main.py` calls `execute_dispatch` without `executor=`, so the scan's `docker
  version` runs through `default_executor`, a fresh temporary directory with its own Docker
  configuration, not `$OAK_RUNNER_HOME/docker-config` and the run's `run-*` directory that
  `docs/configuration.md` and `RR-027` describe. The documents were left describing the intent.
- `tests/unit/test_model_transport.py::test_a_provider_that_trickles_its_status_line_is_cut_off_at_the_deadline`
  failed once on a shared macOS runner (8.40 s against 8) and passed on the same commit.
- `docs/release-process.md` has no step that requires the native consent text to be signed
  off before a release ships native installation.
- `docs/dependencies.md` reviews no hardware-scan tool, and nothing says whether a harness a
  profile installs, such as llama.cpp, needs one: a decision, not a fix.
- The merged branches `tier3-formats`, `tier3-machine`, `native-install-progress`,
  `tier3-native-api-key` and `fix/image-package-index` are still on the remote; deleting them is
  the owner's.
