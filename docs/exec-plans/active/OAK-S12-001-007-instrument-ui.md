<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S12-001–007: OAK Studio, direction A ("Instrument")

**Authorized by the owner on 2026-10-15** by launching `SPRINT-12-PROMPT.md` (governance
root) and answering its four kickoff questions. The owner chose the look and the shape on
2026-10-12; this plan builds it faithfully, cheaply and correctly, and moves no boundary.

Execution is on branch `sprint-12-instrument-ui`, branched from `origin/main` at `50f1673`
(the merge of PR #33). `0.9.0` is the latest published release; nothing here is a release.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-15
- Last updated: 2026-10-15 (M3: Conversation)
- State: in-progress
- Claimed tasks: `OAK-S12-001`–`OAK-S12-007`

One plan covers seven task IDs because every task changes the same web source tree and is
judged by the same browser suite; splitting them would only repeat the invariants.

## Owner's answers, and what they settle

| # | Question | Answer (2026-10-15) | Effect on this plan |
|---|---|---|---|
| K1 | One read-only REST route for the final architecture document? | **Yes** | `GET /v1/design-cases/{case_id}/architecture?candidate_id=&format=json\|yaml`, composed in the shared control-plane service, registered as unreleased in the compatibility test, documented in both interface tables and the changelog. It needs no idempotency key or `If-Match`. |
| K2 | Remove the word "enterprise" from the product too? | **Separate change, after this sprint** | The variant id `balanced_enterprise` stays in the canonical schema enum. The UI never renders it: one label map shows it as "Balanced". No digest moves. |
| K3 | Dark only, or dark and light? | **Dark only**, with tokens ready for light | One theme, one contrast pass, one screenshot set. Every colour is a CSS custom property in `web/src/tokens.css`, so a light theme is a second token block later. |
| K4 | Keep today's routes or merge them into one thread? | **Keep the routes** | Deep links, `#page-heading` focus handling and the e2e pins survive. Each route is restyled as a moment of the conversation. |

## Outcome

Today the workspace is a text-heavy form sequence: unstyled headings, raw variant ids,
no downloads except the whole-case export, and no visual topology.

After this plan a user opens `http://127.0.0.1:5173/` and:

1. **Home** shows a composer labelled "Brief prompt" with an attach chip, three mode
   icons (Deterministic, Online AI, Local AI) and one brass send keycap, above recent
   cases as tiles with progress rings.
2. **Conversation** (`/cases/:id`, `/review`, `/confirm`) shows the brief as a bubble,
   each ranked question as a chip card (one `<fieldset>` per question, the current one
   open, answered ones collapsed to a reply bubble), review claims with provenance marks
   ("Fact from brief", "Inference", "Domain default" beside their symbols) and a case
   rail.
3. **Designs** (`/candidates`) shows each candidate as a card with a topology glyph and
   three range bars; cards drag onto a compare bench, with keyboard pick-up; a table
   view carries the same facts; the infeasible candidate is dashed with its reason.
4. **Architecture** (`/bundle`) draws the selected candidate's topology as SVG from
   `candidate.topology` beside a nodes-and-edges table, with prediction chips, a "Take
   it" dock, three install lights and "Copy install steps", which copies text and runs
   nothing. The sentence "the web workspace holds no runner execution authority" stays
   visible.
5. **Downloads** are one tap each: the brief as stored, the intent, each candidate, the
   decision and the assurance plan through the existing artifact read with the sha256
   verified in the browser against `X-OAK-Artifact-Digest`; the topology as SVG
   serialised from the drawn diagram; and the final architecture document through the
   K1 route, as JSON or YAML.

Proof, from a clean throwaway stack:

```bash
export COMPOSE_PROJECT_NAME=oak-s12 COMPOSE_FILE=compose.yaml:<override>
export OAK_WEB_BASE_URL=http://127.0.0.1:15174 OAK_API_BASE_URL=http://127.0.0.1:18080
make web-e2e                                   # every spec green, zero axe violations
curl -sS "$OAK_API_BASE_URL/v1/design-cases/<id>/architecture?format=yaml" -D -   # K1
```

## Context and invariants

- **Web stack.** React 19 and Vite 7 are the only runtime dependencies. The router is
  hand-rolled (`web/src/router.tsx`; routes in `web/src/main.tsx`). All styling is one
  global `web/src/styles.css` (535 lines, hard-coded hex). Pages live in
  `web/src/pages/`. There are no icons, fonts, motion or SVG, and no web unit tests
  (`RR-021`). The browser suite is `web/e2e/*.spec.ts`, driven by Playwright with
  `@axe-core/playwright`.
- **API client.** `web/src/generated/api.ts` is generated from the `CLIENT_SOURCE` string
  in `scripts/generate_openapi.py`. The generator is edited, never the output;
  `make openapi-compatibility` fails on drift.
- **Downloads that need no server change.** `GET
  /v1/design-cases/{id}/artifacts/{artifact_id}?version=&digest=` returns stored bytes
  with their media type and `X-OAK-Artifact-Digest`. The brief is `case.brief_refs` with
  `source_record.original_name` as the filename, labelled "as stored, normalised". The
  digest is verified over `response.arrayBuffer()` with `crypto.subtle`, never over
  re-serialised JSON (JavaScript drops the `.0` of whole-number floats).
- **The one new route (K1).** The composition in
  `oak.application.architecture.architecture_document` moves into the shared
  control-plane service; `app.py` and the browser do not rebuild it
  (`candidate_planning.py` holds the file-workspace version). The document is composed
  at request time, so it has no stable digest; the UI shows its parts' digests.
- **Fonts.** `@fontsource/instrument-serif`, `@fontsource/ibm-plex-sans` and
  `@fontsource/ibm-plex-mono` at exact pinned versions, OFL-1.1, no install scripts
  (pnpm builds only `esbuild`), reviewed in `docs/dependencies.md`. No CDN, no Google
  Fonts at runtime, no other dependency: icons are inline SVG components and the diagram
  is hand-built SVG.
- **Visual source of truth.** The design canvas at
  https://claude.ai/artifact/UHQT3NK53yUVZKttJdTkXN, read one artboard at a time when its
  screen is built. Tokens, copy rules and the variant-label map are in the prompt and are
  copied, not re-derived.
- **Boundaries that do not move** (prompt §7; `AGENTS.md` product boundaries;
  ADR-0016 for the token; ADR-0017 for install and observation): the web never signs,
  approves, dispatches, installs, ingests or observes and holds no runner execution
  authority; it shows only the actions the API returns and keeps the 409 recovery path;
  it stays same-origin and loopback-only with no CORS; every picture has a text
  equivalent and nothing differs by colour alone; `sessionStorage`-only token handling
  is unchanged and the page is never framed; the reference digests and the OpenAPI
  baseline stay unchanged apart from the K1 addition. `OAK-NFR-UX-*` apply.
- **Copy rules (the owner's).** Labels ≤4 words, sentences ≤10; explanations go in
  `title`, a tooltip or a disclosure. The composer is labelled "Brief prompt"; an attached
  brief shows only as a chip (name · size · remove). The word "enterprise" is never
  rendered; variant ids pass through one map (`simpler_baseline` → Baseline,
  `minimum_sufficient` → Minimal, `balanced_enterprise` → Balanced,
  `high_assurance_sovereign` → High assurance, else humanised). Candidate ids stay, in
  mono. Mode labels are Deterministic, Online AI and Local AI; no mode is called free.

## Scope

### In

- `web/src/tokens.css`, the three font packages, primitives in `web/src/ui/` (`Keycap`,
  `Chip`, `Tile`, `Card`, `Led`, `RangeBar`, `ProvenanceMark`, `CopyPlate`, `Icon`), a
  variant-label map, a reduced-motion rule.
- Every page restyled: Home, Conversation (case, review, confirm), Designs,
  Architecture, Decision, Operation, Settings.
- Downloads: artifact reads with sha256 verification, client SVG export, the K1 route
  and its sheet. The whole-case export stays exactly as it is.
- Guards G1–G4 in `scripts/check_studio_ui.py`, wired into `make validate`.
- E2e: the three deliberate pin changes with their specs; one new test that a downloaded
  candidate's sha256 equals `X-OAK-Artifact-Digest`; a Python integration test for K1.
- The 11 manual screenshots, captions, the PDF, and the docs sweep in both repositories.

### Out

- The Environments view and native install (no Environments navigation is shown).
- Bundle and case zips. A light theme (K3). The product variant rename (K2). A desktop
  app. Any release. Merging the routes (K4).

## Contract and data changes

- **REST (additive, K1):** `GET /v1/design-cases/{case_id}/architecture` with
  `candidate_id` (optional; defaults to the decided candidate) and `format` (`json` |
  `yaml`). Headers: `Content-Disposition: attachment` with an RFC 6266 filename,
  `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. Listed in
  `UNRELEASED_OPERATIONS`/`UNRELEASED_SCHEMAS` in
  `tests/unit/test_openapi_compatibility.py`; rows in `docs/interfaces.md` and the
  governance `docs/build/interface-contract.md`; a CHANGELOG entry. The compatibility
  baseline is not rewritten.
- **Schemas, canonical objects, persistence, events, CLI, MCP:** none. Checked: the route
  composes from objects the case already holds.
- **Dependencies:** three `@fontsource` packages (OFL-1.1), reviewed in
  `docs/dependencies.md`.
- **E2e pins changed deliberately:** "Brief content" → "Brief prompt"; "Describe what you
  want to build" → "What do you want to build?" ("Design cases" stays as the heading of
  the recent-cases section); `getByText("simpler_baseline")` → "Baseline". Any other pin
  that changes gets an equally strong replacement, never a deletion.

## Milestones

Each milestone ends with one commit, its exit checks green, and a line under Progress.
Before every commit: `git status --porcelain -uall`, then `scripts/check_studio_ui.py`
(from M1), no `Co-Authored-By` or "Generated with" lines.

### Milestone 0 — Kickoff (`OAK-S12-001`)

- Work: the four answers; Sprint 12 registered in `sprints.md`; the authorization in both
  `STATUS.md` files; tasks claimed; this plan; the throwaway stack (`COMPOSE_PROJECT_NAME=oak-s12`,
  api on 18080, web on 15174); baseline.
- Proof: `pnpm --dir web build` green; `e2e/journey.spec.ts` green against the throwaway
  stack, before any UI change.
- Rollback: delete the branch; `docker compose down -v --rmi local`.

### Milestone 1 — Tokens, fonts, primitives, guards (`OAK-S12-002`)

- Work: `tokens.css`; the fonts; `web/src/ui/*`; the variant-label map; the
  reduced-motion rule; `scripts/check_studio_ui.py` (G1–G4) in `make validate`.
- Proof: build green; no hex value left in `styles.css` outside the tokens; G1–G3 pass.
- Rollback: revert the commit; no server change.

### Milestone 2 — Home (`OAK-S12-003`)

- Work: the composer ("Brief prompt", attach chip, mode icons, send keycap); recent
  tiles with progress rings; the two deliberate pin changes with their specs.
- Proof: `journey.spec.ts` green.

### Milestone 3 — Conversation (`OAK-S12-003`)

- Work: brief bubble; questions as chip cards (five fieldsets, the current open, answered
  collapsed to a reply bubble); review claims with provenance marks; case rail.
- Proof: `journey.spec.ts` and `models.spec.ts` green; zero axe violations.

### Milestone 4 — Designs (`OAK-S12-004`)

- Work: candidate cards with a topology glyph and three range bars; drag to the bench
  with keyboard pick-up; cards and table views; the infeasible card dashed with its
  reason; the `simpler_baseline` → "Baseline" pin change.
- Proof: `journey.spec.ts` green, including `.nth(2)` order and the region and list names.

### Milestone 5 — Architecture (`OAK-S12-004`)

- Work: SVG topology from `candidate.topology` with a nodes-and-edges table; prediction
  chips; the "Take it" dock; three install lights; "Copy install steps"; the pinned
  sentence.
- Proof: `journey.spec.ts` green; G4.

### Milestone 6 — Downloads (`OAK-S12-005`)

- Work: artifact reads with sha256 verification; client SVG export; the K1 route moved
  into the shared service with its registrations; the downloads sheet.
- Proof: one new e2e test (downloaded candidate sha256 = `X-OAK-Artifact-Digest`); a
  Python integration test for K1; `make openapi-compatibility` green.
- Rollback: revert; the route is additive and unreleased.

### Milestone 7 — Remaining pages, screenshots, manual (`OAK-S12-006`)

- Work: Decision, Operation and Settings restyled with the tokens and primitives; the
  full browser suite; the 11 screenshots after exactly one suite run; captions; PDF.
- Proof: `make web-e2e` green on a fresh throwaway stack.

### Milestone 8 — Docs, review, gate, PR (`OAK-S12-007`)

- Work: grep both repositories for every changed label; README, tour, manual, CHANGELOG,
  both `STATUS.md`; one closing review of at most five agents; `make check` once; the
  PR. This plan moves to `completed/`.
- Proof: zero `make: ***` lines; review survivors fixed; CI green. The merge is the
  owner's. No tag, no release.

## Verification

- Build and types: `pnpm --dir web build` (tsc + vite).
- Guards: `scripts/check_studio_ui.py` (G1 no "enterprise", no raw variant id outside the
  map, no `fonts.googleapis`; G2 no new non-GET call in the generated client and no
  approve/sign/dispatch/install/apply button unless its name starts with "Copy"; G3
  every `<svg>` has `aria-hidden` or `role="img"` plus `aria-label` and every icon-only
  button has `aria-label`; G4 the pinned bundle sentence), in `make validate`.
- Browser: `web/e2e/journey.spec.ts`, `models.spec.ts`, `failures.spec.ts`,
  `hardening.spec.ts`, `compose-target.spec.ts`, `manual-screens.spec.ts`, all against
  the throwaway stack; axe with zero violations on the eight journey screens and WCAG 2
  A/AA on Settings; the new download-digest test.
- Server: the K1 integration test (json and yaml; headers; unknown case 404; unknown
  candidate 404; no `If-Match` needed); `make openapi-compatibility`; `make check` once at
  the end.
- Failure paths kept: 409 conflict recovery ("This case changed while you were viewing
  it."), long operations ("Waiting for the worker to finish…"), infeasible candidate,
  missing token.

## Security, privacy and authority review

- Input trust: the web renders API responses only; the brief's content is never rendered
  on the page (only name · size · remove). Artifact bytes are verified against the digest
  header before a download is offered.
- Authority: no non-GET call is added to the client; every mutation the UI offers is one
  the API returned as an available action. "Copy install steps" writes text to the
  clipboard and runs nothing. Selecting a candidate is visually and semantically distinct
  from approving one.
- Credentials: `sessionStorage` only, never echoed, page never framed; unchanged.
- The K1 route reads existing case objects in the caller's tenant through the same
  service as every other read; it composes at request time and carries no credential,
  no raw brief and no stable digest claim.

## Operational and rollback plan

Local-only change. No migration, no flag. The K1 route is additive and marked unreleased.
Rollback is a revert of the branch. The throwaway stack is removed at the end with
`docker compose down -v --rmi local`; the owner's `oak-community` stack is never touched.

## Progress

- [x] 2026-10-15 K1–K4 answered (all the recommended option). Branch
  `sprint-12-instrument-ui` from `origin/main` at `50f1673`. Sprint 12 registered; tasks
  claimed; authorization recorded in both `STATUS.md` files.
- [x] 2026-10-15 M0 baseline: `pnpm --dir web build` green (tsc + vite, 47 modules);
  `journey.spec.ts` green on the throwaway stack (`oak-s12`, api 18080, web 15174): 1
  passed in 15.6s, before any UI change. `OAK-S12-001` complete.
- [x] 2026-10-15 M1: `web/src/tokens.css` (every colour, radius, shadow, duration;
  reduced-motion zeroes the durations), `styles.css` rewritten on the tokens with no
  literal colour, the three `@fontsource` packages at 5.3.0 (no install scripts; OFL-1.1
  review in `docs/dependencies.md`), primitives in `web/src/ui/` (`Keycap`, `Chip`,
  `Tile`, `Card`, `Led`, `RangeBar`, `ProvenanceMark`, `CopyPlate`, `Icon`), the
  variant-label map, `ClaimBadge` now renders a `ProvenanceMark` with the same words.
  `scripts/check_studio_ui.py` (G1–G4 plus G5, the no-literal-colour check) wired into
  `make validate`; each guard mutation-checked (a planted violation per guard fails it).
  Build green (fonts bundled as woff2 in `dist/assets`); `journey.spec.ts` green with
  zero axe violations on its eight screens. `OAK-S12-002` complete.
- [x] 2026-10-15 M2 Home: `CaseListPage` is the composer ("What do you want to build?",
  "Brief prompt", an attach control that reads .md/.txt/.yaml/.yml/.json up to 256 KiB
  into a chip (name · size · remove) and never shows its text, drag-and-drop onto the
  composer, the file-name pill still labelled "Brief file name", the three modes as radio
  chips in a group named "How should this brief be read?", one round brass send keycap
  named "Create case") above recent cases as tiles with progress rings under the heading
  "Design cases". The masthead is the serif wordmark, two glyph links (Cases, Models) and
  the mono version line; the footer is two short sentences. `journey.spec.ts` and
  `models.spec.ts` green on the rebuilt stack, with the pin changes below.
- [x] 2026-10-15 M3 Conversation: `CaseRail` (ring named by its step count, raw status
  in mono, eight journey pips each with hidden words, version and age) beside a thread.
  `CasePage`: the brief as a bubble (name · size from its source record, the mode glyph
  while still a draft), machine moments per status with the pinned links and keycaps,
  candidates as chips through the label map, the audit timeline. `ReviewPage`: the
  claims table with provenance marks and the pinned headings. `ConfirmPage`: one
  `<fieldset>` per question (current, upcoming, answered), the value as chips with its
  origin mark, the reason in a disclosure, the four decisions as radio chips whose
  accessible names are unchanged, the value field only for a correction, "Done"
  collapses an answered question to a reply bubble with "Edit", progress pips named
  "Question k of n". No pin changed. `journey.spec.ts`, `models.spec.ts` and
  `failures.spec.ts` green; zero axe violations on the three screens.

## Decisions

- 2026-10-15 M2 pin changes, each with its spec in the same commit: "Brief content" →
  "Brief prompt" (journey, models ×2, manual-screens); the heading "Describe what you
  want to build" → "What do you want to build?" (models); and, because the mode chooser is
  now a group of three radio chips rather than a `<select>`, the models spec asserts
  `getByRole("group", { name: "How should this brief be read?" })` with three radios,
  "Deterministic" checked by default, and `check()` on "Local AI" where it used
  `toHaveValue`/`selectOption`/`option` count. Each replacement asserts the same fact
  about the same control; nothing was deleted. `[data-mode-detail]` and `.masthead`
  pins are untouched.
- 2026-10-15 No free-text reply composer on the conversation screens, although the
  Conversation artboard draws one: no API action backs a free-text reply, and the web
  shows only the actions the API returns (§7).
- 2026-10-15 Keep one plan for seven task IDs (one source tree, one suite).
- 2026-10-15 The K1 document shows its parts' digests, not a digest of itself, because it
  is composed at request time (prompt §3).
- 2026-10-15 The keycap travels 3px when pressed and has a 12px radius, as the Tactile
  artboard draws it; the prompt's token list says 2px and 10px for controls. The canvas is
  declared the source of truth, so the canvas wins; the tokens carry the artboard values.
- 2026-10-15 A fifth guard, G5, checks that `styles.css` paints only tokens. It is the
  M1 exit check made permanent, at the cost of one regex.

## Discoveries and follow-ups

(symptom → cause → fix; written before each fix)

- 2026-10-15 M3: the built CSS bundle kept M2's hash although the conversation styles
  had been "added" → the edit script anchored on the one-line `--shadow-send` token, which
  Prettier had reflowed onto three lines after M2, so its assertion failed; and the script
  ran inside the same backgrounded command as the verification, so the failure did not
  stop the run (environment, not product) → edits now anchor on single-line tokens or
  section comments and run in their own foreground command before any verification.

## Self-review

Answered at the end of each milestone: (1) did any pinned name change without its spec?
(2) did any new text exceed the word budget? (3) did anything touch a boundary in §7?

- M0: (1) no; (2) no new UI text; (3) no.
- M3: (1) no; (2) new text: "Ready when you are.", "N checks before I design.", "Ready
  to design.", "N designs.", "What I read, and where each value came from." (9 words),
  "Nothing read yet. Interpret the brief first.", "No open questions.", "Why it
  matters", "Done", "Edit", "Clear decision", "Five per round; N more follow."; the
  decision chips show "Confirm", "Correct", "Reject", "Accept the risk" with the rest
  of each pinned name visually hidden; (3) no: the same calls, the same conflict path.
- M2: (1) three pins changed, each with its spec in the same commit (see Decisions); (2)
  new text: "What do you want to build?" (5 words), "Describe it in your own words…",
  "No cases yet.", "Attach a brief", the two refusal sentences (≤7 words), the footer's
  two sentences (8 and 6 words); (3) no: the attach control reads a file in the browser
  and sends it through the existing create call.
- M1: (1) no, every pinned name is untouched (the journey spec passed unchanged); (2) the
  only new visible words are the copy control's "Copy", "Copied" and "Copy failed. Select
  the text." (5 words); (3) no: no call added, no button named for an authority, the copy
  control imports no client (G2 proves both).
