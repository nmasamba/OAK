<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-044: a native install says which file it is fetching and how far along it is

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-11-04
- Last updated: 2026-11-04
- State: complete (the PR's merge is the owner's)

## Outcome

The hand rehearsal of `examples/targets/local-native-llama-cpp.yaml` on 2026-11-03 took 224
seconds with no output until it finished, which reads as a hang. After this plan, a person
running `oak-runner run-once` at a terminal sees each file and how far along it is:

```text
downloading qwen2.5-0.5b-instruct-q4_k_m.gguf, the model (491.4 MB)
  245.7 MB of 491.4 MB (50%)
```

The second line repaints in place. With stdout a file or a pipe nothing new is printed.

## Context and invariants

- `fetch` in `src/oak/runner/native_network.py` is the runner's one network module (ADR-0019).
  It is injected into `NativeProcessAdapter`, which is what keeps the adapter testable offline.
- `run_once` in `src/oak/runner/main.py` builds the adapter; `native_adapter` is a test seam.
- The journal, the evidence and every signed message are records. This change adds nothing to
  them: `docs/signed-runner.md` and the Controlled installation recipe in `skills.md` bound what
  evidence may hold, and evidence never names a URL.
- `docs/compatibility.md` makes the CLI's stdout/stderr split a stable surface.

## Scope

### In

- A `progress` callback on `fetch`, a `progress` reporter on `NativeProcessAdapter`, and a
  terminal reporter in `main.py`, wired only when stdout is a terminal.
- `docs/signed-runner.md`, `docs/operations.md`, `docs/compatibility.md`, `CHANGELOG.md` and
  `STATUS.md`.

### Out

- The wait for a component to answer, unpacking and the re-check of a file already on disk.
  None of them is a download. See Discoveries.
- Heartbeats during a download, which would change what is signed.
- A CLI option, a rate or an estimate of time left.

## Contract and data changes

None to a schema, an API, an event, a stored document or an exit code. `oak-runner run-once`
adds output to stdout only when stdout is a terminal, so what a script captures is unchanged;
`docs/compatibility.md` records it. `fetch` and the adapter's constructor gain optional
keyword arguments; neither is a public interface.

## Milestones

### Milestone 1: the seam and the terminal output

- Work: `fetch(..., progress=)` reports the bytes written after each chunk. `_obtain` delegates
  to `_download`, which reports a `DownloadProgress` when a download starts, after each chunk
  and when it ends, whatever the outcome. `artifact_name` gives the name a person sees.
  `_TerminalProgress` prints; `_terminal_progress` returns it only for a terminal.
- Proof: `tests/unit/test_native_download_progress.py`, `tests/unit/test_native_network.py` and
  `test_a_download_shows_on_a_terminal_and_nothing_new_is_recorded` in
  `tests/integration/test_native_install.py`.
- Rollback: revert the commit. Nothing stored depends on it.

## Verification

- Unit: the sequence of updates for each file; evidence equal with and without a reporter; a
  failed download and a refused one each end their report; a reporter that raises
  `OSError` or `ValueError` changes no outcome; a linked file and a second `apply` report
  nothing; the terminal's exact text; flushing; a real pseudo-terminal with its output stopped;
  terminal, pipe, closed and absent stdout.
- Integration: two installs through the real `run_once` over a signed dispatch, on a terminal
  and off one, with a heartbeat at every step. The journals and messages have the same shape,
  and neither names a file, the host, the query string or the temporary home.
- Mutation: each new guard broken in turn.
- Manual: the real adapter, the real `fetch` loop and the real reporter in a real pseudo-terminal,
  reading the bytes as they arrive. No real download: that needs the owner's approval of each
  file, and nothing here depends on one.
- `make check` with the PostgreSQL-gated suites.

## Security, privacy and authority review

- **Authority.** No change. Progress is an output: nothing reads it, and no check, approval or
  lease depends on it. No shell or argument vector is involved.
- **Recorded data.** `DownloadProgress` holds a role, a name, two counts and a flag, never the
  URL or a path, and only the reporter receives it. The adapter's evidence is built as before.
- **What reaches the terminal.** The name comes from the operator's own target profile, already
  checked against a schema, but it is treated as untrusted anyway: only the last path segment,
  never decoded, and only when it is printable and at most 120 characters. A signed link's
  token in the query string never reaches the name. One in a path would, on the operator's own
  terminal; that is the profile's own text and is not recorded.
- **Failure.** A reporter's `OSError` or `ValueError` is dropped in `_report`. Without that,
  `fetch` would report a failed write to the terminal as `OAK-NATIVE-DOWNLOAD` and the install
  would fail.
- **A stalled terminal.** The reporter runs inside `fetch`'s loop, so a write that blocks would
  stop the download and its lease check: a server's idle close would fail the install, and a
  terminal that never resumed would hang the run with `run.lock` held. So `_TerminalProgress`
  asks `select` first and drops what the terminal cannot take at once. A thread would not do:
  `_start_probe_stop` passes `preexec_fn`, which relies on the runner having none.

## Operational and rollback plan

Local only. There is no flag: redirecting stdout turns progress off. Reverting the commit
restores the silence and leaves every record readable.

## Progress

- [x] 2026-11-04 PR #44 confirmed merged as `e91047b`; branch `native-install-progress` cut from
  it.
- [x] 2026-11-04 Tests written first and seen to fail; seam, reporter and wiring added.
- [x] 2026-11-04 Mutation checks: 29 mutants, 28 killed. `no flush` survived, so a stream that
  shows only what was flushed was added. The reason first given for it was wrong: see the review
  below.
- [x] 2026-11-04 A real pseudo-terminal: repaints arrived about 0.25 seconds apart, at the pace
  of the slowed chunks, so none is held back until the end.
- [x] 2026-11-04 `make check` with PostgreSQL on the first commit, `e696542`: 1,539 unit and
  contract, 637 integration, 47 end-to-end, no `make: ***`. Superseded by the review's fixes.
- [x] 2026-11-04 An independent review of that commit, with these results, each checked by hand
  first. (1) **A paused terminal stalled the download**, which nothing did before: on a real
  pseudo-terminal, plain writes never finished with Ctrl-S typed, with output stopped or with
  nobody reading, and writes behind `select` finished in all three; fixed, with
  `test_a_paused_terminal_does_not_stop_the_download`, which failed first. (2) **"A terminal
  that goes away fails nothing" was false**: closing the window sends `SIGHUP`, which ends the
  run mid-download, as it always did; the sentences now claim only what the code does. (3) **The
  reason given for `flush` was wrong**: Python's line buffering also flushes a write holding
  `\r`, so the test's rationale is corrected and the flush kept, since it costs nothing and
  assumes less. (4) The plan's state and (5) two loose phrases, corrected here.
- [x] 2026-11-04 After those fixes: 31 mutants, the two new ones removing and blocking on the
  `select`, all killed. In a real pseudo-terminal, a real Ctrl-S went in 1.46 seconds into the
  run and `apply` returned at 3.51 seconds with no Ctrl-Q sent.
- [x] 2026-11-04 `make check` on `ce476e0`, on a fresh, migrated PostgreSQL on 127.0.0.1:15434:
  1,540 unit and contract (1 skipped), 637 integration (4 skipped), 47 end-to-end, no
  `make: ***`, and no count of PostgreSQL-gated tests skipped. `make validate` and the
  repository checks passed again after this entry, which changes only this plan.

## Decisions

- 2026-11-04 **Quiet when stdout is not a terminal**, rather than a plain line per file. Output
  a script captures stays byte for byte what it was, so nothing that parses `run-once` can break.
- 2026-11-04 **stdout, not stderr, and gated on stdout.** The check and the stream are the same
  object, so `\r` can never reach a file: `2> run.log` would otherwise collect repaints.
- 2026-11-04 **Two lines per file.** Only the short line repaints, and it stays under 40
  characters, so it does not wrap on a usual terminal and no terminal width need be read.
- 2026-11-04 **No throttle.** A repaint per 1 MiB chunk is about 30 bytes per MiB downloaded,
  and a terminal that cannot keep up is skipped rather than waited for.
- 2026-11-04 **`select`, not a second descriptor.** Opening the terminal again with `O_NONBLOCK`
  gives a stricter guarantee, but it needs a descriptor to own and can fail where stdout works.
  Setting `O_NONBLOCK` on stdout itself would reach the shell, which shares it. A line dropped
  while the terminal is paused is never shown; the next repaint carries the count forward.
- 2026-11-04 **The failure is dropped in the adapter**, not in the reporter, so that it holds for
  any reporter, in one place.

## Discoveries and follow-ups

- 2026-11-04 **The wait for a component to answer is still silent**: 19.8 seconds in the
  rehearsal, up to 240 for `llama-server`. It is outside this task; `docs/signed-runner.md` says so.
- 2026-11-04 **No heartbeat is published during a download.** `apply` beats once per component,
  before its downloads, so a long download goes without one until it ends. The `progress` seam
  would make it easy, but a heartbeat is signed, and this task changes nothing signed.
- 2026-11-04 **`print` can still raise on a dead terminal**, as it could before this work: a run
  that survives its terminal (disowned, say) gets `OSError` from `print(f"completed ...")`, which
  `main` does not catch. The completion is already published by then, but the run ends there,
  with a traceback, and any later dispatch waits for the next run. Closing the window kills the
  run earlier, by `SIGHUP`, and the next run reports the dispatch as needing recovery.
