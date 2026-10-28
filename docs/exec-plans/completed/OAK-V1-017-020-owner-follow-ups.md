<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-017–020: the owner's follow-ups to the pre-1.0 engineering batch

**Directed by the owner on 2026-10-26**, after PR #39 merged (`2d5ec62`). The batch's PR
left three questions for the owner, and the owner answered each:

- the unknown-case code: change the server side now, while the downside is still low, and
  run the comprehensive gates to show nothing broke;
- the release workflow's `make check`, which ran without a database: the final checks must
  run the database suites;
- the original spec repo's dormant workflow, still on unpinned Node-20 actions: update it.

This plan starts from `origin/main` at `2d5ec62`. It bumps no version, cuts no tag,
writes no release decision record and publishes nothing.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-26
- Last updated: 2026-10-26 (M4, gates and PR)
- State: complete (PR #40 open, https://github.com/nmasamba/OAK/pull/40; the merge is the owner's)
- Claimed tasks: `OAK-V1-017`–`OAK-V1-020`

One plan covers four task IDs because they answer one set of owner questions, land as one
change and are judged by one set of gates.

## Outcome

After this plan:

1. **REST and MCP answer `OAK-CASE-NOT-FOUND` for a case the server does not hold**
   (`OAK-V1-017`). Before, a well-formed case id that named no stored case reached the
   store and came back as `OAK-WORKSPACE-NOT-FOUND`, a local-workspace code whose remedy
   ("run oak init") is wrong for a server, while a malformed id already answered
   `OAK-CASE-NOT-FOUND`. Every case-scoped entry point of the shared control plane now
   answers `OAK-CASE-NOT-FOUND`, still `404` with the opaque detail, on both stores, so
   REST, MCP and the remote CLI agree with the local CLI. `OAK-WORKSPACE-NOT-FOUND` keeps
   one meaning: no workspace at this location.
2. **The release workflow's gate runs the PostgreSQL suites** (`OAK-V1-018`). Its
   `artifacts` job starts the same pinned `postgres` service as CI, migrates it and sets
   `OAK_TEST_DATABASE_URL` before `make check`. `make toolchain-check` refuses either
   workflow without them. A sprint's closing `make check` runs them too, and a pytest
   summary line counts the database tests a run skipped, so a skip no longer looks like a
   pass.
3. **The original spec repo's workflow is pinned** (`OAK-V1-019`). `spec-quality.yml` in the
   original spec repo names Node-24 releases of `actions/checkout` and
   `actions/setup-python` by commit SHA, with each release in a comment, and caches on
   `requirements-dev.txt`. The original spec repo's validator refuses an unpinned action.
4. **Gates and PR** (`OAK-V1-020`): `make check` with `OAK_TEST_DATABASE_URL` on a fresh,
   migrated throwaway PostgreSQL, `make audit`, `make web-e2e` on a throwaway Compose
   project, the plan closed and the PR open with CI green. The merge is the owner's.

## Context and invariants

- `docs/compatibility.md`: `OAK-*` codes are part of the public surface, and an existing
  code may not change meaning or disappear while a documented flow uses it. The REST and
  MCP answer for an unknown case is documented in `docs/error-codes.md`, so this is a
  breaking change to the error contract, recorded as such. 1.0 is not cut, so no released
  1.0 client depends on it. The status (`404`) and the opaque detail do not change.
- REST and MCP replace the message of every not-found code with one opaque detail, so on
  those transports the code is the client's only signal (`OAK-S8-006`).
- AGENTS.md: no interface-specific policy. The translation belongs in the shared
  application facade (`oak.application.control_plane.CommunityControlPlane`), which REST,
  MCP and the worker all call, not in each transport.
- `docs/error-codes.md` is generated and line-sensitive; regenerate it after every `src/`
  edit.
- The original spec repo is not a git repository; it is edited in place and validated with
  `uv run --project OAKCommunity python scripts/validate_repo.py`.
- Standing rules: never touch the owner's `oak-community` Compose stack (ports 8080 and
  5173) or its database on port 15432; never run `tests/live` with
  `OAK_LIVE_MODEL_TESTS=1`; never run two `make check` at once; no vendor attribution
  lines in commits or the PR body.

## Scope

### In

- `src/oak/application/control_plane.py`: a decorator that turns a store's
  `OAK-WORKSPACE-NOT-FOUND` into `OAK-CASE-NOT-FOUND` on every public method that takes a
  `case_id`.
- `src/oak/interfaces/cli/remote.py`: the remote CLI names the case for either code, so a
  `1.0` client against a `0.9` server still reads well.
- Tests: an application-level table over every case-scoped method on the file store, a
  guard that the table covers every method with a `case_id`, the PostgreSQL REST path,
  and the existing REST, MCP and remote-CLI pins tightened to the one code.
- `.github/workflows/release.yml`, `tools/check_toolchains.py` and its contract tests.
- `tests/conftest.py`: the skipped-database-tests summary line.
- Docs: `scripts/generate_error_reference.py` and the regenerated `docs/error-codes.md`,
  `docs/compatibility.md`, `docs/interfaces.md`, `CONTRIBUTING.md`, `docs/development.md`,
  `docs/security/residual-risk.md` (`RR-019`), `CHANGELOG.md`, `STATUS.md`; in the
  original spec repo, `AGENTS.md`'s definition of done, `.github/workflows/spec-quality.yml`,
  `scripts/validate_repo.py`, and the status records.

### Out

- Removing `OAK-WORKSPACE-NOT-FOUND` from the REST `404` family or MCP's opaque set: it is
  still the local answer, and any path that still raises it must stay a `404`.
- The worker's `execute_operation`: an operation is accepted only for a held case, and the
  server never deletes one, so the worker cannot meet an unknown case through the API.
- Any version bump, tag, release decision record or publication.

## Contract and data changes

- No schema, OpenAPI document, MCP tool definition or digest changes.
- The REST and MCP error contract changes for one flow, recorded in
  `docs/compatibility.md` and `CHANGELOG.md`: a well-formed case id the server does not
  hold answers `OAK-CASE-NOT-FOUND` where it answered `OAK-WORKSPACE-NOT-FOUND`.

## Milestones

### M0 — Kickoff (`OAK-V1-017`–`020` claimed)

- Work: branch `pre-v1-follow-ups` from `origin/main` (`2d5ec62`); this plan; the STATUS
  rows.
- Proof: `git log -1` shows the plan and the rows.
- Rollback: delete the branch.

### M1 — The unknown-case code (`OAK-V1-017`)

- Work: the decorator, the remote-CLI mapping, the tests, the error reference and the
  compatibility notes.
- Proof: the new tests fail on `2d5ec62` and pass after; the REST, MCP and remote-CLI pins
  assert `OAK-CASE-NOT-FOUND` alone.
- Rollback: revert the commit; clients see `OAK-WORKSPACE-NOT-FOUND` again.

### M2 — The release gate runs the database suites (`OAK-V1-018`)

- Work: the service, migration and variable in `release.yml`; `tools/check_toolchains.py`
  checks both workflows; the summary line; the rule in AGENTS.md and the contributor docs.
- Proof: contract tests refuse a release workflow without the variable or with a different
  image; a run without the variable prints the skipped count.
- Rollback: revert the commit.

### M3 — The original spec repo's workflow (`OAK-V1-019`)

- Work: the pins, the cache path and the validator check, in place in the original spec repo.
- Proof: `validate_repo.py` passes, and fails on a copy with `actions/checkout@v4`.
- Rollback: restore the two `uses:` lines.

### M4 — Gates and PR (`OAK-V1-020`)

- Work: the full gate, the PR and its CI.
- Proof: the numbers below, recorded in Progress.
- Rollback: none needed; nothing is published.

## Verification

- `make check` with `OAK_TEST_DATABASE_URL` on a fresh, migrated throwaway PostgreSQL on
  port 15433, with zero `make: ***` lines.
- `make audit` clean.
- `make web-e2e` on a throwaway Compose project with its own name and ports.
- CI green on the PR, with the database suites running.

## Security, privacy and authority review

- The translation runs after every authority check a method makes and adds none; it never
  turns a denial into a success.
- Existence: a case held for another tenant is invisible to the store's predicate, so it
  answers the same code as a case that does not exist, as before. The detail stays
  opaque on REST and MCP.

## Operational and rollback plan

A client or script that matched `OAK-WORKSPACE-NOT-FOUND` on a case route must match
`OAK-CASE-NOT-FOUND`; one that matched the `404` status sees no change. Reverting the
commit restores the old code.

## Progress

- [x] 2026-10-26 M0 — branch `pre-v1-follow-ups` from `origin/main` at `2d5ec62`; plan and
  STATUS rows.
- [x] 2026-10-26 M1 — `_case_scoped` wraps the 19 public control-plane methods that take a
  `case_id`. The new table test failed for all 19 on `2d5ec62`
  (`'OAK-WORKSPACE-NOT-FOUND' == 'OAK-CASE-NOT-FOUND'`) and passes; a guard pins the
  table to every such method. The REST (file and PostgreSQL), MCP and remote-CLI pins
  assert the one code. Mutation checks: dropping the decorator from `research_plan`
  fails its row; reverting the remote mapping fails the client test and the live-server
  test. The affected suites pass against a migrated PostgreSQL 17.6 on port 15433.
- [x] 2026-10-26 M2 — `release.yml`'s `artifacts` job runs the same `postgres` service as
  CI, migrates it and sets `OAK_TEST_DATABASE_URL`, and fetches the runner journeys'
  stand-in image, before `make check`. `tools/check_toolchains.py` holds both workflows to
  the database suites (`_check_database_suites`) and the release workflow to CI's image
  fetch; four new contract cases refuse a release workflow without the variable, without
  the migration, with another image, or without the fetch. A run without the variable
  ends with `PostgreSQL-gated tests skipped: N (OAK_TEST_DATABASE_URL is not set)` (12 for
  `test_operations.py` and `test_readiness_revision.py`), and a contract test keeps every
  gated skip on the counted reason. The rule is in the original spec repo's `AGENTS.md` definition
  of done, `CONTRIBUTING.md`, `docs/development.md` and `docs/release-process.md`; `RR-019`
  records both of its limits lifted.
- [x] 2026-10-26 M3 — in the original spec repo (edited in place): `spec-quality.yml` pins
  `actions/checkout` v7.0.1 and `actions/setup-python` v7.0.0 (the newest release at least
  two weeks old; its `action.yml` runs on `node24`) by commit SHA, caches on
  `requirements-dev.txt`, and runs Python 3.13. `validate_workflows` in
  `scripts/validate_repo.py` refuses an action with no ref, a movable ref, or a SHA
  without its release; three mutations were each refused, the restored file passes, and
  the workflow's own steps (`pip install -r requirements-dev.txt`, `make validate`) pass in
  a clean Python 3.13 environment.
- [x] 2026-10-26 M4 — `make check` with `OAK_TEST_DATABASE_URL` on a fresh, migrated throwaway PostgreSQL 17.6 (port 15433) green on the code tree (`4a54e78`) with zero `make: ***` lines: 1,198 unit and contract passed (1 skipped), 457 integration passed (4 skipped, the PostgreSQL-only assertions on the file store), 43 end-to-end passed with none skipped; `make audit` clean after `filelock` 4.2.4 (`7db8170`); `make web-e2e` 33 passed, 2 skipped, on the throwaway Compose project `oak-v1c` built from `7db8170`; on that stack REST, `oak-mcp` and the remote CLI each answered `OAK-CASE-NOT-FOUND` for a case it does not hold. PR #40 opened; the original spec repo moved to `0.4.0-draft.17`.
- [x] 2026-10-27 At the owner's request, the specification repository is called the
  "original spec repo" everywhere both repositories named it "the governance repository"
  (or "governance root" or plain "governance"): the mirrored ADRs' headers and the
  contract test that reads them, `tools/check_repository.py`'s mirror helper
  (`_is_spec_mirror`), STATUS, the ADR index, the completed plans and the changelog.
  "Governance" as a subject (the report section, policy-pack governance, the contributor
  guide's section) is unchanged.
- [x] 2026-10-27 CI failed `make audit` on both runs of `3a644e0` (`make check` with the
  database and `make build` passed in both): `CVE-2026-114613`, published that day,
  against `msgpack` 1.2.1, which only `pip-audit`'s cache uses. `msgpack` moved alone to
  1.2.3, the release with the fix; `make audit` clean locally on it.

## Decisions

- 2026-10-26 Translate in the shared control plane, by a decorator on each public method
  that takes a `case_id`, rather than in each transport (AGENTS.md: no interface-specific
  policy), in the stores (a workspace is the store's own concept, and the local CLI's
  answer must not change), or by an existence query before each call (one more round trip
  per request, and still racy).
- 2026-10-26 The original spec repo's workflow runs Python 3.13, not 3.12: the validator is only
  ever run on 3.13 (`uv run --project OAKCommunity`), only 3.13 is installed here to prove
  the workflow's steps, and 3.12 would be an untested interpreter.
- 2026-10-26 The release gate fetches the runner journeys' image as well as running the
  database: the owner's point was that the final checks must be complete, and the
  real-daemon journeys skipped there for the same reason.

## Discoveries and follow-ups

- The release gate had a second silent skip of the same kind: CI fetches the pinned
  stand-in image the real-daemon runner journeys need, the release workflow did not, so
  those journeys skipped at release. Fixed in M2.
- `make audit` failed on the gate: three advisories published since 2026-10-23
  (`CVE-2026-112907`, `CVE-2026-112913`, `CVE-2026-112940`) against `filelock` 3.32.3,
  which only `pip-audit`'s cache uses. CI runs `make audit`, so it would have failed this
  PR and the next push to `main`. `uv lock --upgrade-package filelock` moved it alone to
  4.2.4 (MIT, unchanged), recorded in `docs/dependencies.md` as the `urllib3` lift of
  2026-09-30 was; `make audit` is clean on it.
- A second advisory landed between gates: `CVE-2026-114613` against `msgpack` 1.2.1, also
  reached only through `pip-audit`'s cache, was published on 2026-10-27 and failed CI's
  `make audit` on the rename commit. It moved to 1.2.3, the fixed release, rather than the
  day-old 1.2.4, whose changes are not security fixes; recorded in `docs/dependencies.md`.
- `make toolchain-check` failed once in the fresh worktree, then passed unchanged: pnpm
  printed its first-use download progress for Node 24.18.0 ahead of the version, and the
  runtime check compares the whole output. Environmental; it passes once Node is cached.

## Self-review

- **Boundary.** The translation is in the shared application facade, which REST, MCP
  and the worker call; no transport gained a rule of its own, and the stores still
  answer their own code. Every REST route and MCP tool that takes a case id reaches one
  of the 19 wrapped methods; the others (create, list, import, operations, outbox) take
  none.
- **Authority.** The decorator only renames one refusal; it never turns a refusal into a
  success and runs no check of its own. No write happens before a case is found: every
  wrapped method reads the case first, and a submission's precondition runs before its
  operation is queued (the table test drains the queue and finds nothing).
- **Leakage.** The REST and MCP detail stays opaque, and a case held for another tenant
  is invisible to the store's predicate, so it answers as an absent one, as before.
- **Compatibility.** Breaking for a client that matched the old code on a case route,
  recorded in `docs/compatibility.md` and the changelog; the status and detail are
  unchanged, and the remote CLI still reads a `0.9` server's answer.
