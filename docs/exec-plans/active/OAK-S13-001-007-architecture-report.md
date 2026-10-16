<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S13-001–007: The architecture report

**Authorized by the owner on 2026-10-16** by launching `SPRINT-13-PROMPT.md` (governance
root) and answering its six kickoff questions. The prompt is the specification; this plan
records the owner's answers, the design choices the prompt left open, and the proof for
each milestone.

Execution is on branch `sprint-13-architecture-report`, branched from `origin/main` at
`6142270` (the merge of PR #34). `0.9.0` is the latest published release; nothing here is
a release.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-10-16
- Last updated: 2026-10-16
- State: in-progress
- Claimed tasks: `OAK-S13-001`–`OAK-S13-007`

One plan covers seven task IDs because they build one vertical feature, from the schema to
the screen, and are judged by one set of guards and one browser spec.

## Owner's answers, and what they settle

| # | Question | Answer (2026-10-16) | Effect on this plan |
|---|---|---|---|
| K1 | Record the report, or compose it on every read? | **Record** | `record-report` is the one new mutation: three or four artifacts, a case successor with the same status, and a `report_recorded` audit event. G2's `KNOWN_MUTATIONS` gains `recordReport`. |
| K2 | Where are the files rendered? | **Server side, in Python** | `python-pptx` and `reportlab` in one adapter behind `ReportRendererPort`; both get the full dependency review in M3. |
| K3 | Who writes the words? | **A model narrative**, then on a follow-up question: **an opt-in mode on Record**, with **a note on each main slide** | See "The opt-in notes" below. Deterministic stays the default and makes no model call. |
| K4 | How early can a report be recorded? | **From `candidate_selected`** | Earlier is `OAK-REPORT-STATE` (409) naming the missing step. A record that does not exist yet is shown as "Not yet" with the step that makes it. |
| K5 | How do the files look? | **The print palette** | Light paper, ink, one brass accent; the dark ground on the cover only. Helvetica and Courier, which PDF readers always have, so no font file is added. |
| K6 | Does MCP get the report? | **No** | The MCP tool set and its conformance tests are untouched. |

**The opt-in notes (K3).** The owner's first answer chose a model-written narrative; it
conflicted with the prompt's §7 ("no model call and no network") and §9 (narrative out of
scope), so a follow-up question asked how it should fit. The answer:

- `record-report` takes the mode Sprint 10 gave the brief: `deterministic` (the default),
  `online` or `local`. Deterministic composes and renders with no model, no network and no
  provider module imported, byte-for-byte reproducibly.
- A model mode makes one bounded, schema-constrained request to the model the user
  configured, through the existing provider profiles and the one transport module. It
  sends the composed report's main-slide text (titles, facts and table cells), never the
  brief document, a credential or a token. It asks for at most one note per main slide.
- Each note is checked before it is kept. It has at most two sentences and 280
  characters. It contains no assurance vocabulary, no "enterprise", no raw variant id, no
  URL and no claim of approval or authority. Every number in it must appear in that
  slide's own text. A note that fails is dropped and counted. If none survive, the command
  fails and commits nothing.
- The surviving notes are stored as their own `report_narrative` artifact, with the model,
  provider route, prompt and response digests, usage and the number dropped, and never the
  prompt or response text. The report document quotes each note on its slide under the
  label "Proposed by model", beside the template text, never in its place.
- Re-rendering a recorded report gives the same bytes, because the notes are a record.
  Recording again in a model mode makes a new record.
- The web keeps exactly one new non-GET call: the mode is a query parameter of
  `recordReport`. A model mode needs the capability token, as interpretation does.

## Outcome

Today a user can see a design case on screens and take its records as JSON or YAML, but
nothing gives a decision-maker one document that explains the decision.

After this plan:

1. `oak report --record` (or **Record report** on the new Report screen) composes the
   architecture report from the case's records. It stores the report document (JSON) and
   its PPTX and PDF renderings as artifacts, revises the case without changing its status,
   and appends a `report_recorded` audit event.
2. `/cases/:caseId/report` shows the report one slide at a time, with ← and →, a contents
   list and a table beside every picture. It names the case version the report was made
   from. When the case has moved on, it says so and offers **Record again**.
3. **PPTX**, **PDF** and **JSON** chips download through the verified path and read
   *digest matches*. `oak report --format pdf --output r.pdf` does the same locally or with
   `--server`, checking the bytes against the recorded digest.
4. A report can be recorded from `candidate_selected`. Earlier, the command answers 409
   and names the step that is missing.

## Context and invariants

- **The precedent.** Sprint 12's `oak.application.architecture.architecture_document` is a
  pure composer called from a service and exposed by `CommunityControlPlane`. The report
  composer follows it, in `oak.application.report`. `ReleaseService.approve` and
  `record_observation` show how a command revises the case at its current status and
  publishes one event with its artifacts.
- **Persistence.** Both adapters already store one non-JSON kind, `brief_source`: no
  schema, `canonical_document` null in PostgreSQL, bytes in the content-addressed object
  store. The renderings become a second such kind, `report_rendering`, accepted only with
  the PPTX or PDF media type. The 8 MiB artifact ceiling stays; the renderer refuses
  anything over 4 MiB.
- **Hard invariants (prompt §7), kept as written.** A report authorizes nothing: no
  signature, no status change, and nothing in approval, dispatch or the runner reads it.
  Deterministic mode is offline and byte-stable. No number appears without its unit and
  source, `unknown` stays `unknown`, no benefit is invented, and synthetic estimates are
  labelled. The web stays a REST client with one new mutation. The four reference digests
  and the OpenAPI baseline do not move. Every picture has a table; the screen works from
  the keyboard; motion stops under reduced motion; text pairs reach 4.5:1 on screen and in
  the files. Nothing private enters the report.
- **K3's relaxation, and only that.** "No model call" now reads "no model call unless the
  user picks a model mode for this recording". Everything else in §7 applies to the notes
  too.
- **Boundaries.** `pptx` and `reportlab` join the roots `tools/check_boundaries.py` forbids
  in the domain, compiler, ports, application and runner. The narrator adapter lives in
  `oak.adapters.models` and is imported only when a model mode is chosen, which the
  offline-boundary test proves.
- **Requirements touched:** OAK-FR-ARC-007 (explanations), OAK-NFR-SEC-003 (no egress by
  default), the copy and honesty rules of the prompt's §2. ADR-0009 (model proposals are
  untrusted data) and ADR-0016 (credentials) apply to the notes unchanged.

## Scope

### In

- Contract: `architecture-report` and `report-narrative` schemas with examples; kinds
  `architecture_report`, `report_narrative`, `report_rendering`; `report_recorded`; the case
  extension `oak.community/report`.
- `oak.application.report`: the composer, the variant label map in Python, the topology
  layout port and the record command.
- `oak.adapters.report`: the layout planner, the print palette, the PPTX and PDF renderers.
- `oak.adapters.models.report_narrator`: the opt-in note proposer.
- REST `POST /v1/design-cases/{case_id}:record-report`, the CLI `oak report`, OpenAPI and
  the generated client, error codes, interface tables.
- The Report screen, the rail link, the record keycap and mode choice, the stale notice,
  the download chips, and Report tiles in the sheet and the dock.
- `scripts/check_report.py` (R1–R4) in `make validate`; docs, manual, twelfth screenshot.

### Out

- Report tools over MCP (K6).
- Research beyond the catalogue snapshot the case holds (Sprint 14).
- Hardware scanning and native installation.
- Embedded brand fonts (K5), a light screen theme, any release.

## Contract and data changes

- **`schemas/architecture-report.schema.json` (0.1.0).** `{schema_version, id, version,
  case_ref, generated_at, generated_by, oak_version, composer_version, renderer, narrative,
  sections[], inputs[], extensions}`. A section is `{id, number, kind: main|appendix, title,
  subtitle, state: ready|not_yet, detail_in[], blocks[], narrative}`. Blocks are `facts`,
  `table`, `quote`, `callout`, `paragraph`, `diagram`, `commands` and `not_yet`. Every number
  is a `quantity` `{value, lower, upper, unit, basis, confidence, estimator, source, text}`.
  `basis` is one of confirmed, assumed, estimated, measured, synthetic estimate, counted or
  declared. Every cell and fact carries a `source`: `"template"` or `"<id>@<version>#<json
  pointer>"`.
- **`schemas/report-narrative.schema.json` (0.1.0).** `{schema_version, id, version, case_id,
  facts_digest, notes[{section, text}], extensions["oak.community/model"]}`, with the same
  model fields as an interpretation proposal plus `dropped_notes`.
- **Kinds** (three registration points each): `architecture_report` and `report_narrative`
  (JSON, schema-validated) and `report_rendering` (bytes, PPTX or PDF media type only, like
  `brief_source`).
- **`audit-event.event_type`** gains `report_recorded`. **No transition** is added:
  recording revises the case at its own status.
- **Case extension `oak.community/report`:** `{document_ref, pptx_ref, pdf_ref,
  narrative_ref|null, made_from_case_version, recorded_case_version}`. The report is current
  while `case.version == recorded_case_version`. Older reports stay in the artifact index
  and the audit trail.
- **REST:** `POST /v1/design-cases/{case_id}:record-report?narrative=deterministic|online|local`
  with `Idempotency-Key` and `If-Match`, plus `X-OAK-Model-Token` in a model mode. It returns
  `ReportResponse {case, report, document, duplicate}`. The files are read through the
  existing artifact route. Listed as unreleased in `test_openapi_compatibility.py`.
- **CLI:** `oak report [--record] [--narrative MODE] [--format json|pptx|pdf] [--output
  FILE] [--case ID] [--idempotency-key KEY]`, local or `--server`.
- **Errors:** `OAK-REPORT-STATE` (409: too early, closed); `OAK-REPORT-MISSING` (CLI read
  with nothing recorded); `OAK-REPORT-SIZE` (413); `OAK-REPORT-RENDER` (422);
  `OAK-NARRATIVE-MALFORMED`, `OAK-NARRATIVE-EMPTY`, `OAK-NARRATIVE-UNAVAILABLE`; and the
  existing `OAK-MODEL-NOT-CONFIGURED`.
- **Dependencies:** `python-pptx` and `reportlab`, with their transitive set, after review.
- **Compatibility:** additive. No stored object changes and no migration; an older reader
  ignores the new extension. The reference journey records no report, so its digests hold.

## Milestones

Each milestone ends with one commit, its exit check green and a line under Progress.

### Milestone 0 — Kickoff (`OAK-S13-001`)

- Work: the answers, the branch, this plan, Sprint 13 registered in governance, tasks
  claimed, and the throwaway stack `oak-s13` on 18080/15174.
- Proof: `pnpm --dir web build` green, and `journey.spec.ts` green on the throwaway stack.

### Milestone 1 — Contract (`OAK-S13-002`)

- Work: the two schemas and their examples, `EXAMPLE_BY_SCHEMA`, `schemas/README.md`, the
  three kinds in both adapters and the manifest enum, `report_recorded`, the extension's
  export-lineage check, and `pptx`/`reportlab` in the boundary roots.
- Proof: `make validate`, the contract tests and `test_reference_digests.py` green.

### Milestone 2 — Composer (`OAK-S13-002`)

- Work: `report_document(...)`, pure, with every section and its "Not yet" state; the Python
  label map with an agreement test against `variantLabel.ts`; the topology port; and the
  shared vocabulary patterns (moved to `oak.domain.vocabulary` and imported by
  `tools/check_repository.py`).
- Proof: a golden report document for the reference case, byte-stable. One unit test per
  section, run with and without its source record.

### Milestone 3 — Renderers (`OAK-S13-003`)

- Work: the dependency review and lock. `ReportRendererPort`, the layout planner, the print
  palette, and PPTX and PDF layouts for every block, with the diagram drawn from the
  report's layout.
- Proof: the same bytes from two runs in two processes; the layout agreement test against
  `web/src/topology.ts`; `python-pptx` reopens the PPTX and the PDF parses; each file 4 MiB
  or less; the API image builds.

### Milestone 4 — Record and interfaces (`OAK-S13-004`)

- Work: `ReportService.record`, `CommunityControlPlane.record_report`, the REST command,
  `oak report`, the narrator port and adapter with a fake for tests, OpenAPI, the client,
  error codes and the interface tables.
- Proof: integration tests for each of these:
  - recording;
  - an idempotent retry;
  - a stale `If-Match` (409);
  - too early (409, naming the step);
  - an unknown case (404);
  - rendering digests verified;
  - the CLI in local and remote mode;
  - model mode with a fake transport: notes kept, notes dropped, all dropped, no token;
  - a deterministic run imports no provider module.

### Milestone 5 — The Report screen (`OAK-S13-005`)

- Work: route, slides, keyboard paging, contents, record keycap with the mode choice, the
  stale notice, the chips, the rail link and the two tiles.
- Proof: a new `report.spec.ts` that records, pages through every slide by keyboard,
  downloads PPTX and PDF and matches each digest, and finds zero axe violations;
  `journey.spec.ts` green and unchanged.

### Milestone 6 — Docs (`OAK-S13-006`)

- Work: a manual section and figure (11 → 12 shots), README, interfaces, compatibility,
  dependencies, threat coverage, residual risks, CHANGELOG, both `STATUS.md` files.
- Proof: every page that lists the workspace's screens lists the Report screen.

### Milestone 7 — Full suite, screenshots, manual (`OAK-S13-006`)

- Proof: `make web-e2e` green on a fresh throwaway stack; the 12 screenshots taken after
  that one run; the manual PDF rebuilt.

### Milestone 8 — Review and close (`OAK-S13-007`)

- Work: one closing workflow (three finders, one refute-by-default skeptic), its survivors
  fixed, `make check` once, `make audit` once, the plan moved to `completed/`, a PR.
- Proof: zero `make: ***` lines; CI green. The merge is the owner's.

Rollback for every milestone: revert its commit. Nothing migrates and nothing stored
changes shape, so an older build reads a workspace that holds reports and ignores them.

## Verification

- Unit: each section with and without its record; the label map; the topology port; the
  vocabulary; the note checks; the planner's wrapping and pagination.
- Contract: schemas against their examples; the label-map and layout agreement tests; the
  boundary rules; R1–R4 mutation-checked.
- Integration: the record command in both repositories, REST, the CLI in both modes, the
  narrator through a fake transport, the offline boundary, the reference digests.
- Byte stability: render twice in two processes and compare.
- Browser: `report.spec.ts`, then the full suite once at M7.
- Failure paths: too early, stale version, retry, unknown case, a closed case, oversize,
  model not configured, a malformed answer, all notes dropped.

## Security, privacy and authority review

- **Input trust.** The composer reads canonical records only and never embeds the brief
  document. Model output is untrusted, bounded, re-validated and dropped on any failed
  check. It is never interpreted as an instruction, and no provider text reaches an
  `OAKError` message.
- **Data leaving the machine** happens only in a model mode the user chose for this
  recording, and only the report's own main-slide text. The screen says so before the call.
- **Authority.** Recording needs no signature and moves no status. No approval, dispatch or
  runner path reads the report or the extension. The web gains one mutation, guarded by G2.
- **Secrets.** Secret references appear by name only. No credential or token is stored, and
  only digests of the prompt and response.
- **Supply chain.** The two dependencies and their native wheels (`lxml`, `Pillow`) are
  reviewed in `docs/dependencies.md`, audited with `pip-audit`, and entered in the SBOM.
  Untrusted text reaches them only as strings to draw; no file is parsed except in tests.

## Operational and rollback plan

Local-only and additive. A bad rendering is recorded as a new immutable artifact, and the
fix is to record again after an upgrade. A deployment that drops the feature leaves inert
artifacts and an unknown extension behind; readers ignore both.

## Progress

- [x] 2026-10-16 M0: the six answers and the K3 follow-up recorded; Sprint 13 registered in
  `sprints.md` and both `STATUS.md` files; branch `sprint-13-architecture-report` from
  `6142270`; this plan.

## Decisions

- 2026-10-16 **The renderings are a second opaque kind, `report_rendering`,** beside
  `brief_source`, rather than one kind per format: one exemption in each adapter, gated on
  the two media types.
- 2026-10-16 **The case holds only the latest report** (`oak.community/report`); earlier
  ones stay in the index and the audit trail. "Current" is a version comparison the client
  can make without another read.
- 2026-10-16 **The layout planner is shared by both renderers** and measures text with
  `reportlab`'s font metrics, so the PPTX and the PDF paginate identically and "page n of
  N" agrees.
- 2026-10-16 **Status marks are drawn shapes plus a word.** The standard PDF fonts carry no
  check or cross glyphs.
- 2026-10-16 **The PDF's text is limited to the cp1252 character set** of its standard
  fonts (K5). Other characters print as "?"; the JSON and the PPTX keep them. This is
  recorded as a residual risk.
- 2026-10-16 **The vocabulary patterns move to `oak.domain.vocabulary`** so the runtime note
  check and the repository check share one definition.

## Discoveries

(Each line: symptom → cause → fix, written before the fix.)

## Self-review

(Three answers per milestone: pinned names changed without their spec; numbers or
sentences without a source; boundaries touched.)

## Retro

(Three lines at the end.)
