<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-047: the inventory scan runs its commands through the run's own executor

## Status

- Owner/agent: coding agent, on a follow-up the coherence sweep (`OAK-V1-046`) recorded
- Started: 2026-11-10
- Last updated: 2026-11-10
- State: complete (the PR's merge is the owner's)

## Outcome

`oak-runner run-once` makes one executor per run, and every command the run starts goes
through it: the command sees only `PATH=/bin:/usr/bin` and
`DOCKER_CONFIG=$OAK_RUNNER_HOME/docker-config`, an empty configuration the runner owns, and it
starts in the run's private `run-*` directory, which the run removes when it ends. After this
change that includes the commands of the hardware scan inside an `inventory` operation:
`docker version`, plus `sysctl` and `system_profiler` on macOS or `lscpu`, `nvidia-smi` and
`rocm-smi` on Linux.

Before it, `run_once` handed its executor to the container adapter but not to
`execute_dispatch`, whose `executor` then defaulted to `default_executor`: one built per process
over a private directory under the system's temporary directory (`oak-runner-*`), with a Docker
configuration of its own. The new test shows the difference. Without the fix it reports the
scan's `DOCKER_CONFIG` as `.../T/oak-runner-qd2fthft/docker-config` where the runner home's
`docker-config` was expected.

## Context and invariants

- `src/oak/runner/main.py`, `_run_once_locked`: `executor = isolated_executor(home /
  "docker-config", working_directory=work)`, built once for the whole run (`RR-002`), then
  `ContainerFixtureAdapter(executor)` and `execute_dispatch(...)`.
- `src/oak/runner/execution.py`, `execute_dispatch(..., executor=default_executor, ...)`: the
  scan is `lambda: scan_hardware(executor=executor)` unless a `scanner` is injected.
- `src/oak/runner/hardware.py`, `scan`: runs the platform's tools and `docker version` through
  the executor it is given; `uv` is looked up and never run.
- `src/oak/runner/adapters.py`: `isolated_executor` fixes the child's environment and working
  directory and resolves each allowlisted executable once; `default_executor` is the same over a
  private temporary directory, for a caller with no run: the local `oak scan`, and tests.
- The documents already described the fixed behavior: the `OAK_RUNNER_HOME` row and the note on
  the runner's `docker` commands in `docs/configuration.md`, and `RR-013`, `RR-027` and `RR-055`
  in `docs/security/residual-risk.md`. The sweep left them stating the intent.
- Kept: no shell, the allowlist, the fixed argument vectors, the evidence's shape, and the
  verification order in `docs/signed-runner.md`, which nothing here moves.

## Scope

### In

- `run_once` passes its executor to `execute_dispatch`.
- An integration test through the real `run_once` over a signed `inventory` dispatch.

### Out

- `oak scan`, the local command. It has no runner home and no run, so the default executor's
  private temporary directory is the right one for it.
- `execute_dispatch`'s defaults for `executor` and `scanner`, which tests use.
- The documents, which already say what the code now does.

## Contract and data changes

None to a schema, an API, an event, a stored document, an exit code, the output or the
evidence. The scan reads the same tools' output; only where they run changes. Two side effects
are visible on disk: an `inventory` run now creates the runner home's empty `docker-config`
(mode 0700) when the scan runs a tool, as a container operation already did, and a run no
longer creates an `oak-runner-*` directory under the system's temporary directory.

## Milestones

### Milestone 1: the scan gets the run's executor

- Work: `executor=executor` in `run_once`'s call to `execute_dispatch`.
- Proof: `tests/integration/test_runner_inventory_executor.py`.
- Rollback: revert the commit. Nothing stored depends on it.

## Verification

- Integration: a signed, approved `inventory` dispatch through the real `run_once`. A `docker`
  first on `PATH` makes the scan ask for the daemon's version on any machine; nothing executes
  it, because `subprocess.run` records each child the run's real `isolated_executor` would
  start. `docker version` runs once, with only `PATH` and the runner home's `docker-config` in
  its environment, from the run's `run-*` directory while that exists; every other command the
  scan starts runs the same way; the published completion says `succeeded` and carries the
  scan's `docker: present`. The process-wide default executor is reset for the test and
  restored after it, so a regression cannot leave the test's `PATH` in it.
- Seen to fail first: without the fix the test fails on `DOCKER_CONFIG`, as quoted above.
- Mutation: three mutants of `main.py`, each killed by the test: no executor handed to the
  dispatch; the run's executor working in the runner home itself; and its Docker configuration
  in another directory.
- `make check` with the PostgreSQL-gated suites on a fresh, migrated database.

## Security, privacy and authority review

- **Authority.** No change: the same allowlisted tools with the same fixed argument vectors and
  no shell; no new input reaches an argument.
- **Credentials.** None became reachable or unreachable. Both Docker configurations were empty
  and the runner's, so the operator's `~/.docker/config.json`, credential helpers and contexts
  were never read either way (`RR-013`).
- **Location.** The scan's children start in the run's private, owner-only directory under the
  runner home, removed when the run ends, instead of one under the system's temporary directory,
  removed when the process exits (`RR-027`).
- **Resolution.** The scan runs the executables the run resolved when it started, as every other
  command of the run does (`RR-002`); the default executor resolved them again at its first use.

## Operational and rollback plan

Local only, with no flag. Reverting the commit restores the previous behavior and leaves every
record readable.

## Progress

- [x] 2026-11-10 Branch `runner-inventory-executor` cut from `origin/main` at `3fa08b7`, PR #46's
  merge.
- [x] 2026-11-10 The test written and seen to fail without the fix. With the fix it passes,
  beside the 82 tests of the neighbouring runner and scan suites.
- [x] 2026-11-10 Three mutants, all killed.
- [x] 2026-11-10 `make check` on `a953984`, the code commit, in a detached worktree, with
  `OAK_TEST_DATABASE_URL` on a fresh, migrated PostgreSQL on 127.0.0.1:15436: 1,567 unit and
  contract (1 skipped), 639 integration (4 skipped: the four PostgreSQL-only assertions on the
  file harness, by design, so no PostgreSQL-gated test skipped) and 47 end-to-end, the runner
  journeys included; no `make: ***` line. `make validate`, the
  repository checks and the contract tests passed on `236795b`, which adds only this plan, the
  changelog and the status, and `make audit` was clean.
- [x] 2026-11-10 A trial merge with the sweep's branch, `coherence-sweep`, made locally and
  never pushed, conflicts only in `CHANGELOG.md` and `STATUS.md`; `docs/error-codes.md` merges
  cleanly and is current on it.

## Decisions

- 2026-11-10 **Record the children, not the executor object.** The test checks what the
  documents promise, each child's working directory and `DOCKER_CONFIG`, through the real
  `isolated_executor`, rather than which object was passed along.
- 2026-11-10 **A `docker` stub on `PATH`.** Whether the scan asks for the daemon's version
  depends on finding `docker`, which not every machine that runs the suite has; with the stub
  the test does the same everywhere, and nothing executes it.

## Discoveries and follow-ups

- None. The sweep's other follow-ups stay in its own plan.
