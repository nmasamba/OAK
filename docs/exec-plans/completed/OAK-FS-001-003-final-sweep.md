<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-FS-001–003: Final documentation sweep before the 0.7.1 owner decision

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-08-25
- Last updated: 2026-08-27
- State: complete

One plan covers three task IDs because the sweep is one coherent, documentation-only
change with a single invariant set (byte-stable digests, no new claims) and a single
close-out: neutralizing vendor references, shipping the user manual, and aligning every
status document with the post-merge state were specified together in the owner's
`FINAL-SWEEP-PROMPT.md` (governance root) and land as one PR.

## Outcome

After this plan, a reader of the public repository can follow
`docs/manual/OAK-Community-Manual.pdf` — an illustrated, end-to-end user manual whose
chapter 3 and chapter 5 commands were verified by running those journeys end to end
against this tree — and finds no AI-vendor name used descriptively anywhere in the
documentation; every status
document in both repositories states the post-merge reality (PR #13 merged as
`2d85322`; what remains is the owner's approval, tag, and publication decision).
Demonstrations: `open docs/manual/OAK-Community-Manual.pdf`;
`git grep -iE 'claude|codex|anthropic|copilot|openai'` returns only ignore-file
hygiene entries, defensive filename lists in `tools/check_repository.py`, historical
branch identifiers inside completed exec plans' progress records, and this plan's own
close-out record describing the deletion of those branches.

## Context and invariants

- PR #13 (pre-launch hardening) is merged; `main` = `2d85322`, version `0.7.1`,
  CI green. Nothing is published, no tag exists. The owner's remaining acts: approve
  `docs/release/0.7.1/release-decision.md`, tag `v0.7.1`, decide publication.
- **Neutralize descriptions; do not falsify records.** `Owner/agent:` lines become a
  neutral description that preserves the agent-versus-human distinction — that
  distinction is load-bearing for the approval story (`OAK-S8-009` was decided by a
  human, prepared by an agent). Historical identifiers — branch names in progress
  logs, commit trailers in merged history — are repository facts, kept; the merged
  remote branches are deleted instead so the identifiers leave the live repository UI.
  Rewriting merged history is destructive and remains the owner's call.
- `tools/check_repository.py`'s agent-state filename list is defensive hygiene that
  *prevents* those files being committed — kept, it is not documentation.
- The manual must not out-promise `SECURITY.md` or `docs/security/residual-risk.md`
  (no production or customer readiness claim), must describe brief intake truthfully
  (Markdown/text/YAML/JSON; the deterministic interpreter treats prose as data with
  provenance; the LLM's only seat is the optional `oak.ports.interpreter` proposal
  port; 0.7.1 ships no model adapter and makes zero model calls), and must not present
  YAML as the only or primary brief format.
- Byte-stability: nothing in this sweep may shift the four reference digests
  (`deployment_bundle sha256:570abb66…`, `runner_plan sha256:fad30959…`,
  `selected_candidate sha256:576b0ca6…`, `semantic_manifest sha256:2ef34758…`),
  verified by direct recompilation, not inferred.
- `make check` stays offline-capable, verified by counting `make: ***` lines.

## Scope

### In

- `Owner/agent:` neutralization across the ten completed exec plans.
- `docs/manual/`: authoritative `manual.html`, rendered PDF, ten live screenshots,
  `build_manual.mjs`, capture spec `web/e2e/manual-screens.spec.ts` (gated by
  `OAK_MANUAL_SCREENS=1`), rebuild documentation.
- Post-merge truth pass: `STATUS.md` (both repositories), governance `IMPLEMENT.md`
  and `docs/roadmap.md`, `CHANGELOG.md`, the `0.7.1` release-decision draft's
  "what changed" section.
- Deletion of the merged `claude/*`/`codex/*` remote branches (done; origin now serves
  only `main` and this sweep's own branch).
- Document-policy gates extended to the manual's file types (`.html` under the
  assurance-vocabulary and product-reference scans; `.html`/`.mjs` under the secret
  scan); `OAK_MANUAL_SCREENS` documented in `docs/configuration.md` and pinned by the
  configuration-reference contract test.

### Out

- Rewriting **merged** history to strip commit trailers (destructive; the owner's
  call, and not taken). The owner did later direct that this branch's own unmerged
  commits drop their trailers, which is a safe rewrite of unpublished commits — see
  the Decisions log.
- A real model interpreter adapter (natural next work item, separately scoped).
- Any code, schema, or contract change beyond the two gate files above.
- README authorship lines (the owner adds their own).

## Contract and data changes

None to any canonical surface: no schema, API, CLI, event, persistence or migration
change. `tools/check_repository.py` scans two more suffixes;
`tests/contract/test_configuration_reference.py` pins one more web-side variable.
The four reference digests were recompiled after the sweep and are byte-identical.

## Milestones

### Milestone 1 — OAK-FS-001: vendor references neutralized, gates extended

- Work: `Owner/agent:` lines in all ten completed plans read "owner-directed coding
  agent" (OAK-S3 preserves "final verification by a second agent"); merged remote
  branches deleted; `TEXT_SUFFIXES` gains `.mjs`/`.html` and a `DOCUMENT_SUFFIXES`
  set puts `.html` under the document-policy scans.
- Proof: the sweep grep described under Outcome; `uv run python
  tools/check_repository.py` exits 0 over the whole tree including `manual.html`;
  `git ls-remote --heads origin` lists no `claude/*` or `codex/*` ref (only `main` and,
  until it merges, this sweep's own `release/final-sweep`).
- Rollback: revert the branch; remote branch deletion is reversible only by re-push
  from local refs (which the clone retains).

### Milestone 2 — OAK-FS-002: the illustrated manual

- Work: nine-chapter `manual.html` (what OAK is/is not; install; CLI journey with
  real captured output; browser workspace with ten live screenshots; signed runner
  including a denial-family table mapped to the contractual verification order;
  artifact verification; troubleshooting from the runbook; complete uninstall
  mirroring `docs/operations.md`; colophon), three inline SVG diagrams (pipeline,
  trust domains, revocation manifest), rendered PDF.
- Proof: both journeys executed live against the tree — the chapter 3 CLI journey to
  `bundle_compiled` and export/import, and the full chapter 5 runner journey (keys,
  sign, approve ×3, dispatch, `run-once` creating and removing the never-started
  fixture container with the resolved-digest check, ingest, status with a verified
  hash chain, revoke-approval). Every expected-output excerpt in the manual is what
  those runs printed. Screenshots captured from the running Compose stack by the
  gated spec.
- Rollback: delete `docs/manual/` and the spec; no other surface depends on them.

### Milestone 3 — OAK-FS-003: post-merge truth pass and close-out

- Work: both `STATUS.md` files, governance `IMPLEMENT.md`/`docs/roadmap.md`,
  `CHANGELOG.md` (0.7.1 Added/Changed), release-decision "what changed" amendment
  recording the docs-only sweep, `OAK_MANUAL_SCREENS` reference row, this plan,
  session memory updated for the post-merge state.
- Proof: grep for pre-merge phrasing ("merge the PR once remote CI is green",
  "awaiting merge") returns nothing in live documents of either repository;
  `uv run pytest tests/contract/test_configuration_reference.py` passes.
- Rollback: revert the branch; governance-root edits are plain files restorable from
  this plan's description.

## Verification

- Full `make check` on the sweep tree, verified by counting `make: ***` lines
  (0 found; PostgreSQL-gated suites skip by contract without a published database).
- Direct recompilation of the reference case via the fixed-clock harness
  (`tests.runner_support.build_compiled_case`): all four digests byte-identical to the
  values pinned in `docs/release/0.7.1/release-decision.md`.
- Live execution of both documented journeys (chapter 3 and chapter 5), including the
  real Docker apply/verify/rollback cycle, leaving no fixture container behind.
- `tools/check_repository.py` and the configuration-reference contract suite green
  after the gate extensions.
- A six-dimension multi-agent review of the sweep branch preceded these fixes; its
  three confirmed blockers (a YAML-first diagram label surviving in Figure 1, an
  invalid `oak import --workspace` flag, and an over-promising macOS prerequisites
  row) and its should-fix findings (over-broad offline claim, missing denial-meaning
  coverage, missing expected output, incomplete uninstall, misstated runner exit-code
  semantics, chapter 5 working-directory break, colophon over-claim, undocumented
  `OAK_MANUAL_SCREENS`, unguarded manual source) are all fixed in this tree.
- Closing adversarial audit: see the post-implementation audit section.

## Security, privacy and authority review

Documentation-only. No input-handling, identity, tenant, or privileged-operation
change. The manual makes no claim `SECURITY.md` does not; the assurance-vocabulary
gate now guards its source. The gate extension only widens read-only scans. The
screenshots contain only synthetic fixture data; the PDF's binary content was checked
for vendor strings and tool metadata (Chromium/Skia only). No secret material: the
manual's key fingerprints are public halves of freshly generated, discarded
development keys.

## Operational and rollback plan

Local, documentation-only failure surface. The PDF is a committed convenience
rendering; if it drifts from `manual.html`, rebuild with
`pnpm --dir web exec node ../docs/manual/build_manual.mjs` (the embedded creation
timestamp is the one byte-level difference between rebuilds of identical source,
which is why the HTML is authoritative). The capture spec runs only under
`OAK_MANUAL_SCREENS=1`; `make web-e2e` collects and skips it. Rollback is reverting
the PR.

## Progress

- [x] 2026-08-25 Sweep executed prematurely in a prior session (the owner had asked
  only for the prompt); PR #14 closed at the owner's direction, work preserved on the
  local `release/final-sweep` branch, remote `claude/*`/`codex/*` branches deleted.
- [x] 2026-08-25 Owner issued `FINAL-SWEEP-PROMPT.md` for execution; the preserved
  branch was verified by a six-dimension multi-agent review instead of being redone.
- [x] 2026-08-25 Both manual journeys executed live against the tree; expected-output
  excerpts captured from the real runs; all review findings fixed; PDF re-rendered.
- [x] 2026-08-25 Gates extended and green; four reference digests recompiled
  byte-identical; full `make check` passed (0 `make: ***` lines).
- [x] 2026-08-25 Closing adversarial audit run (five lenses, refute-by-default
  skeptics): 47 raised, 21 confirmed, 26 refuted; the ten distinct confirmed defects
  fixed, screenshots re-captured and the PDF re-rendered.
- [x] 2026-08-25 Truth pass completed across both repositories, including the session
  memory; close-out committed with the audit record above.

## Decisions

- 2026-08-25 **Verify-and-extend rather than redo.** The preserved branch was closed
  for scope reasons (execution without authorization), not quality; redoing it would
  discard verified work and real screenshots. The multi-agent review substituted for
  the trust the closed PR never earned.
- 2026-08-25 **Keep historical identifiers, delete remote branches.** Branch names in
  progress logs and trailers in merged history are facts of the record, like commit
  hashes; neutralizing them would falsify records the approval story depends on. The
  live-UI concern is answered by remote deletion instead.
- 2026-08-25 **Scope the colophon claim honestly.** `oak revoke-approval` is not
  exercised by the two e2e suites; rather than adding test scope to a docs-only
  sweep, the colophon names the revocation integration suite that covers it, and the
  command was verified by direct execution.
- 2026-08-25 The sweep's own commits initially kept their `Co-Authored-By` trailers,
  on the reasoning that they matched the existing history (80 merged commits carry
  them) and that rewriting is the owner's call. **Superseded 2026-08-27 by the owner's
  instruction:** no vendor attribution on this or any future merge, while
  already-merged trailers stay. The four branch commits were rewritten to drop the
  trailers and force-pushed; the rewrite was proven content-neutral (tree hash
  `37a9d28456fc…` identical before and after, empty `git diff` against a backup ref),
  and the same attribution line was removed from the PR description. Merged history on
  `main` is untouched, exactly as the prompt requires.

## Post-implementation audit

A closing multi-agent adversarial audit ran against the full sweep change set (the three
commits plus the uncommitted close-out edits and the governance-root edits) across five
finder lenses — factual truth of every added claim, gate/CI regression risk, spec
compliance against `FINAL-SWEEP-PROMPT.md`, internal consistency and reader experience,
and honesty/security posture. Every candidate finding was then handed to an independent
skeptic instructed to refute by default and to reproduce the defect personally before
confirming it.

**47 candidate findings raised; 21 confirmed, 26 refuted.** The confirmed set
deduplicated to ten distinct defects, all fixed below. Two conflicting verdicts were
adjudicated directly rather than by vote: the chapter 5 `oak-runner status` finding
(refuted by one skeptic on the grounds that adjacent prose carried the caveat, confirmed
by another) was treated as a defect, because a printed command that cannot produce its
printed output is exactly the class of error this sweep exists to remove.

### Fixed

- **Chapter 8 ran its verification after deleting the checkout** (high). The uninstall
  sequence removed the repository, then told the reader to run
  `scripts/check_clean_machine.py` from it. The chapter is now six ordered steps with
  the clean-machine check at step 5 and the checkout removal last, mirroring
  `docs/operations.md`.
- **Chapter 8 misplaced the development private keys** (medium). It claimed step 3
  removed chapter 5's trust directory and mailbox; those live in the repository root,
  so `trust/` — which holds private keys — is now named explicitly in the removal.
- **Chapter 5's `status` command could not print its own output** (medium). The
  `OAK_RUNNER_*` variables were inline prefixes on `run-once` only, so the bare
  `oak-runner status` read the default home and would report an empty journal list.
  The command now carries `OAK_RUNNER_HOME`, and the prose states the real requirement
  and the silent-empty failure mode.
- **Chapter 6 gave consumers a command consumers cannot run** (medium). `make
  verify-release` needs the Makefile and `dist/release`; a reader who received only
  artifacts has neither. The chapter now shows `python scripts/verify_release.py
  <dir>` — standard-library only, no OAK import — with the `shasum`/`sha256sum`
  equivalents, real output, and exit codes.
- **Figure 10 showed none of what its caption promised** (low, and it uncovered more).
  The audit-timeline screenshot was framed above the entries. Fixing the capture
  revealed a second defect: the shot raced the audit fetch and rendered "No audit
  events are recorded yet" while the API held all eight events. The spec now waits for
  the rendered entries and forces the heading to the top of the viewport
  (`scrollIntoViewIfNeeded` is a no-op for an element already at the bottom edge). The
  figure shows all eight events with actor, origin, version and timestamp; the caption
  was rewritten to describe exactly that.
- **"Every documented command was verified" was broader than what was verified**
  (medium). `CHANGELOG.md`, `STATUS.md` and this plan's Outcome now scope the claim to
  the chapter 3 and chapter 5 journeys, matching the colophon.
- **`docs/manual/README.md` over-claimed reproducible rendering** (low). It said
  identical source renders the same document on any machine. The stylesheet names
  system fonts, so a host without them repaginates; the README now claims same-platform
  reproducibility and explains why the HTML, not the PDF, is authoritative.
- **`STATUS.md` asserted an audit record that did not yet exist** (medium) — this
  section. It is now written before the close-out commit, and `STATUS.md` carries the
  counts so the pointer is self-verifying.
- **This plan's demonstration grep under-enumerated its own matches** (low). The
  close-out records describing the branch deletion also match the vendor grep; the
  Outcome now says so, and `STATUS.md`'s row was reworded to "agent-named remote
  branches" so the live status document does not reintroduce the identifiers.
- **The session-memory truth-pass item was half done** (low). The memory note's lead
  paragraph, its frontmatter description and the `MEMORY.md` index line still said
  "awaiting merge"; all three now state the post-merge reality.

### Refuted (not changed)

Representative of the 26: the widened `.html`/`.mjs` document scan reaching gitignored
generated reports (the mechanism predates this diff and no such directory exists in the
tree); the manual PDF and screenshots growing the sdist by ~4.3 MB (reproduced at
4,940,155 bytes — a packaging preference, and the manual is a required deliverable); the
cover's "independently verified" reading as an external-review claim (the runner is named
as the verifier throughout, and the cover box denies external review); the assurance
corpus contract test still globbing `*.md` (the gate itself runs twice in `make check`
and covers HTML, so there is no enforcement gap); the sweep's own commit trailers
(the prompt reserves history rewriting to the owner); and the untracked plan file
(the close-out commit is the next step, and `main` is unaffected).

### Verification after the fixes

`tools/check_repository.py` exit 0 over the extended scope; the configuration-reference
contract suite green; the ten screenshots re-captured from a live Compose stack
reporting `0.7.1`; the PDF re-rendered from the corrected source; full `make check`
re-run and verified by counting `make: ***` lines; the four reference digests
recompiled byte-identical.

## Discoveries and follow-ups

- `oak import` takes `--directory`, not `--workspace` — the premature sweep's manual
  documented an invocation that had never been run. The colophon's "every command
  verified" claim is only as good as actually running every command; this plan's
  verification section now records exactly that discipline.
- The document-policy gates were `.md`-scoped, so the manual's authoritative HTML
  source shipped outside every honesty gate until Milestone 1 extended them.
- A real `oak.ports.interpreter` model adapter remains the natural next work item;
  nothing in this sweep changes that seam.
