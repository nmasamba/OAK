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
- Last updated: 2026-10-21
- State: complete (merged by the owner as PR #36, `671d4a4`, on 2026-10-19)
- Claimed tasks: `OAK-S13-001`–`OAK-S13-007`

One plan covers seven task IDs because they build one vertical feature, from the schema to
the screen, and are judged by one set of guards and one browser spec.

## Owner's answers, and what they settle

| # | Question | Answer (2026-10-16) | Effect on this plan |
|---|---|---|---|
| K1 | Record the report, or compose it on every read? | **Record** | `record-report` is the one new mutation: three or four artifacts, a case successor with the same status, and a `report_recorded` audit event. G2's `KNOWN_MUTATIONS` gains `recordReport`. |
| K2 | Where are the files rendered? | **Server side, in Python**, then **PDF only** (after the M3 review) | `reportlab` in one adapter behind `ReportRendererPort`. `python-pptx` failed the maintenance review in M3, and the owner chose to ship the PDF now and the PPTX later. |
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

The Outcome and Contract sections are the plan as first written, so they still describe a
PPTX rendering; the M3 dependency review narrowed the renderings to PDF only (see
Decisions, 2026-10-16 M3), and the PPTX items below are deferred, not delivered.

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
- [x] 2026-10-16 M1: `architecture-report` and `report-narrative` schemas `0.1.0` with examples, registered in `EXAMPLE_BY_SCHEMA` and `schemas/README.md`. The kinds `architecture_report` and `report_narrative` (JSON) and `report_rendering` (bytes, PPTX or PDF magic only) are registered in both adapters and the manifest enum, with `report_recorded` and the `oak.community/report` export-lineage check. `lxml`, `PIL`, `pptx` and `reportlab` are forbidden outside adapters. Tests: `tests/contract/test_report_contract.py` (9); `make validate`, all contract tests, the reference digests and mypy are green.
- [x] 2026-10-16 M2: `oak.application.report`. The pure `report_document` has twenty section builders, each with its "Not yet" state, and `gather_records` reads every record through the repository port by digest. Also: the Python variant-label map, provenance words and install steps, held equal to the web's by `tests/contract/test_report_agreement.py`; the topology port; the web's three-significant-digit number format; `narrator_facts`, which redacts digests. The vocabulary patterns moved to `oak.domain.vocabulary`. `scripts/check_report.py` (R1–R4) is in `make validate` and composes the reference report live at `candidate_selected`, `assurance_planned` and `bundle_compiled`. The golden is `tests/fixtures/report/public-manual-qa.report.json`, and the example is generated from it. Tests: `test_report_composer.py` (53), `test_report_guards.py` (17 planted violations), `test_report_agreement.py` (3). Live composer mutations for R1, R2 and R3 were all killed. 848 unit and contract tests are green.
- [x] 2026-10-16 M3: the dependency review stopped on `python-pptx` (maintenance), and the owner chose PDF only. `reportlab` 5.0.1 (with `Pillow` 12.3.0) was reviewed in `docs/dependencies.md` and locked, and `docs/platforms.md` records the new floors: Linux x86_64 glibc 2.27 (Pillow), and armv7l now unsupported. `ReportRendererPort` (`oak.ports.report`) and `oak.adapters.report.pdf`. The renderer has its own paginator with continuation pages and repeated table headers, shape-and-word status marks, the workspace's provenance shapes, the topology drawn from the report's layout, range bars, the print palette, Helvetica and Courier with none embedded, and dates from `generated_at` in invariant mode. The reference PDF is 31 pages and 60 KB. Tests: `test_report_pdf.py` (12): two processes give the same bytes under different hash seeds and time zones; a standard-library read-back of xref offsets, pages, footers, titles and dates; fonts, size and refusals. `test_report_layout_agreement.py`: the Python layout and number format equal `web/src/topology.ts` and `formatQuantity`, run through Vite in Node, on four reference candidates, four awkward shapes and twenty numbers; mutation-checked. The API image builds clean (`--no-cache`) and imports the renderer.
- [x] 2026-10-16 M4: `ReportService.record` and `CommunityControlPlane.record_report`. Recording checks status and idempotency, composes, renders, writes the document, the PDF and (in a model mode) the checked notes, revises the case at its own status under `oak.community/report`, and appends `report_recorded`. Too early is `OAK-REPORT-STATE`, naming the missing step. The opt-in narrator is `ReportNarratorPort`: `HostedReportNarrator` makes one bounded, schema-constrained request through the existing provider profiles and transport, `FakeReportNarrator` serves tests, and `check_notes` keeps a note only if every rule passes. `create_report_narrator` and `create_report_renderer` live in bootstrap, behind a shared `_model_route`. Interfaces: `POST /v1/design-cases/{case_id}:record-report` (with `narrative` and the capability token in a model mode), listed as unreleased with `NarrativeMode` and `ReportResponse`; `recordReport` in the generated client and in G2's `KNOWN_MUTATIONS`; `oak report [--record] [--narrative] [--format json|pdf] [--output]`, local and `--server`, with a digest-checked read of the bytes; interface rows in both repositories; error codes regenerated. The narrator is registered in the offline boundary's adapter list. Tests: `test_report_service.py` (11), `test_report_api.py` (7), `test_report_cli.py` (2), `test_report_narrator.py` (12), `test_report_notes.py` (21), and the offline-boundary check that a deterministic report loads no provider module. 893 unit and contract tests and 72 affected integration tests are green.
- [x] 2026-10-16 M5: `/cases/:caseId/report` (`ReportPage`, `ReportSlide`). The screen shows one section per slide, with ←, →, PageUp, PageDown, Home and End on the slide region, "Slide n of N" announced politely, and a contents list. Values are drawn as shape and word: `Led` for statuses and `ProvenanceMark` for marks. The topology uses the workspace's own `TopologyDiagram`, beside its nodes and edges tables. Quoted notes carry their "Proposed by model" label, and "Not yet" boxes name the next step. The record keycap ("Record report" or "Record again") comes with the notes chooser (`ModeChooser` with the new `purpose="report"`; the brief's pinned legend is unchanged). A recorded report names its source version, and a stale one says the case moved on. PDF and JSON tiles go through `downloadVerified` and read "digest matches". The case rail links to the report, and a Report tile appears in the Take it sheet and the dock. `report.spec.ts` covers recording, all twenty slides by keyboard, the diagram beside its tables, PDF and JSON matched to `X-OAK-Artifact-Digest`, the sheet tile, the stale notice, and four axe scans with zero violations. `journey.spec.ts`, `downloads.spec.ts` and `models.spec.ts` are green and unchanged. G1–G5 pass.
- [x] 2026-10-16 M6: manual: "6 · Record the architecture report" in the CLI chapter and the twelfth figure (`12-report.png`, captured by `manual-screens.spec.ts` after the timeline shot). Docs: README (step 7 and everyday use), `docs/interfaces.md`, `docs/architecture.md`, `docs/compatibility.md` (schema, REST and CLI additions), `docs/dependencies.md` and `docs/platforms.md` (M3), `docs/security/threat-coverage.md` (TM-13 cites the narrator and deterministic-report tests), the residual-risk register (`RR-044` to `RR-047`; the live count is now 47), CHANGELOG, both `STATUS.md` files, and the governance interface contract's routes and views list and the roadmap. Every page that lists the workspace's screens lists the Report screen.
- [x] 2026-10-16 M7: the throwaway stack was recreated empty (`down -v --rmi local`, then `up -d --build`) and `make web-e2e` ran once: 25 passed, 1 skipped (the gated capture), zero `make: ***` lines. On that same stack the twelve manual screenshots were captured (`OAK_MANUAL_SCREENS=1`, including the new `12-report.png`), and `docs/manual/OAK-Community-Manual.pdf` was rebuilt.
- [x] 2026-10-16 M8: one closing workflow (three finders, one refute-by-default skeptic) raised 21 findings; 14 survived and are fixed with tests (see Closing review). The golden moved only where a fixture-sourced figure is now labelled "synthetic estimate" (18 values). `make audit` ran once: no known vulnerabilities, zero `make: ***` lines. Because M8 touched the web, the stack was recreated empty and `make web-e2e` ran once more: 25 passed, 1 skipped (the gated capture), zero `make: ***` lines. `make check` ran once: 922 unit and contract tests, 318 integration tests (24 skipped) and 42 end-to-end tests (1 skipped) passed, with every guard (G1–G5, R1–R4) green and zero `make: ***` lines. After PR #35 (the Sprint 12 docs coherence pass) merged into `main`, `origin/main` was merged into this branch. README, `docs/architecture.md` and `STATUS.md` were resolved by keeping both sides. The manual PDF was rebuilt from the merged HTML, and the development guide, new on `main`, now lists the report guards and `recordReport`. On the merged tree, `make validate`, the 922 unit and contract tests, the web type check, Prettier and the web build are green.

## Decisions

- 2026-10-16 **PDF only (owner, after the M3 dependency review).** The report records the
  document (JSON) and one rendering, the PDF. `report_rendering` accepts only `application/pdf`;
  the case extension holds `pdf_ref` and no `pptx_ref`, so a PPTX added later is additive.
  The Report screen offers PDF and JSON. `ReportRendererPort` names its formats, so a PPTX
  renderer can join without changing the port.
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
- 2026-10-16 **`SchemaRegistry.validate` meta-checks each schema once and reuses its
  validator.** It ran `check_schema` on every call, which took almost all of a report's
  record reads (46 s for the guard, 4.7 s after). The schemas are fixed for the registry's
  life, so the answer cannot change. Every other path through the registry gets faster too.
- 2026-10-16 **An offline evaluation's figures are synthetic.** Every evaluation result names
  the fixture set it ran over (`fixture_version` is required), so its metric values and
  sample sizes are "synthetic estimate" with that fixture as estimator, and a fixture
  component's inputs and measurements likewise. The basis word "measured" is kept for a
  figure that came from a real run; R2 refuses it on a fixture source.
- 2026-10-16 **A model's note must stay inside its slide.** The note checks were rewritten from
  naming forbidden things to requiring the note's numbers, number words, units and host
  names to be on the slide it describes, with control and format characters, authority
  words and benefit words refused outright. A dropped note costs a reader one sentence; a
  kept wrong one costs trust, so the checks lean to dropping.
- 2026-10-16 **Report text holds up to 12,000 characters, a decision rationale's limit,** and
  record text beyond a field's limit is shortened with a visible marker naming where the
  full text is. The PDF splits any unit taller than 280 points into continuing pieces.
- 2026-10-16 **The print palette landed in M2 rather than M3**, so R4 could join
  `make validate` with the other guards. It is a small module of colours and pairs; the
  renderers that draw with it follow in M3.

## Discoveries

(Each line: symptom → cause → fix, written before the fix.)

- 2026-10-16 M1, spec pin. `test_no_committed_schema_permits_execution_fields` failed. Cause: the "Not yet" block named a field `command`, and no committed schema may name an execution field outside a denial. Fix: rename it `hint`. It is display text, and the name should not suggest otherwise.
- 2026-10-16 M3, dependency review. `python-pptx` fails maintenance: its last commit and release were 2024-08-07, and it has 541 open issues with no maintainer reply since. Licence, OSV and wheels are clean for it and for `reportlab` 5.0.1, `lxml`, `Pillow`, `XlsxWriter` and `charset-normalizer`. Cause: the library is dormant. Under the prompt's stop rule I stopped and asked the owner. Fix: the owner chose **PDF only this sprint**. `python-pptx` is not added; PPTX becomes a follow-up that needs a library decision.
- 2026-10-16 M5, product defect (presentation). `report.spec.ts` matched "Slide 1 of 20" twice. Cause: the slide marker repeated the position ("Section 1 · slide 1 of 20") that the counter under the slide already announces. Fix: the marker names only the section; the counter alone carries the position, and the spec matches it exactly.
- 2026-10-16 M8, product defects (closing review, 14 of 21 findings survived the skeptic). Logged here before any fix:
  - **Model-note checks (H-1 to H-4), one class:** a denylist over untrusted text is incomplete.
    - Symptoms: invisible Cf characters split a forbidden word; "cleared for deployment" and "secure" pass; bare domains and emails pass; spelled-out numbers, a unit swapped from another row, and an invented saving all pass.
    - Root cause: the checks name forbidden things instead of requiring the note to stay inside its slide.
    - Fix: refuse every Unicode control or format character. Widen the authority words to cover the narrator's own rule 3. Refuse `@`, schemes and any dotted host the slide does not hold. Require spelled-out numbers to appear on the slide. Pair a number's unit word with the slide line that holds the number. Refuse benefit and return words. The parametrised tests carry every probe.
  - **Composer honesty (H-5, H-6, H-9), one class:** labels that contradict the records.
    - Fixture evaluation results and fixture component measurements were labelled "measured". Numbers whose field has no known suffix got the unit "as recorded". Slide 3's title ignored its "Not stated" rows.
    - Fix: label fixture-sourced numbers "synthetic estimate", naming the fixture as estimator. Map the admissible numeric intent fields to real units and show anything else as `unknown`. Count missing values in the title.
    - New guard rules: R2 refuses the unit "as recorded" and a "measured" or "counted" quantity sourced from an evaluation result or a fixture component.
  - **PDF robustness (R-1 to R-4):**
    - A unit taller than a page was drawn past the footer. Fix: units split by lines, and a test that nothing crosses the content edge.
    - A rationale over 4,000 characters failed the schema, so the case could never get a report. Fix: report text to 12,000, and record text clipped with a visible marker.
    - A long case title pushed "page n of N" off the page. Fix: the page number is right-aligned and the title is truncated.
    - `wrap()` was cubic on unbroken text. Fix: one normalisation pass and per-character widths.
  - **Interfaces (A-1, A-3, R-6):** the slide's arrow keys swallowed table scrolling, the diagram scroller was not focusable, and `oak report --output` wrote through a predictable temp name. Fix: nested scroll regions keep their keys, the scroller is a named focusable region, and the CLI uses `mkstemp` beside the target.

## Self-review

(Three answers per milestone: pinned names changed without their spec; numbers or
sentences without a source; boundaries touched.)

- **M1.** (1) No pinned name changed; no UI was touched. (2) The schema makes every number a `quantity` with a unit, basis and source, and every cell carry a source; a contract test proves a quantity without them is refused. (3) Boundaries were tightened only: the document libraries are now forbidden in the domain, compiler, ports, application and runner.
- **M2.** (1) No pinned name changed. The report reuses the web's words through a contract-tested mirror (Balanced, Baseline, the provenance words and the six install steps). (2) Every number is a quantity, with R2 and the schema enforcing it. Template counts are words. Every sentence the composer writes is either fixed template text or a record value with its pointer, and the golden holds no unsourced cell. (3) No boundary moved. The composer is pure and reads through the repository port; the shown-to-a-model facts exclude digests and appendices.
- **M3.** (1) No pinned name changed. The PPTX chip the prompt pinned for M5 is now out of scope by the owner's decision, recorded before any UI work. (2) The renderer adds no words of its own beyond layout furniture: "(continued)", "Detail in appendix", "page n of N", "Not yet" and the mark words. Every figure it draws comes from a quantity's own text. (3) Boundaries: the document libraries are reachable only from `oak.adapters.report`, which `tools/check_boundaries.py` enforces. The Linux glibc floor moved and is documented.
- **M4.** (1) No pinned name changed. The only new mutation in the generated client is `recordReport`, added to `KNOWN_MUTATIONS` with a comment. (2) The command adds no words to the report. A model's notes pass `check_notes`, which drops any note with a number its slide does not hold, and they are quoted under "Proposed by model" with the model named. (3) Boundaries: recording needs no signature and moves no status; approval, dispatch and the runner never read `oak.community/report`. The narrator is reached only in a model mode, the offline-boundary test proves the default loads no provider module, and the capability token is demanded before any model call.
- **M5.** (1) No pinned name changed. The brief chooser keeps "How should this brief be read?" (the default purpose). "Take it", "Copy install steps" and the journey pins are untouched, and the new copy control is named "Copy the next steps", starting with "Copy" as G2 requires. (2) The screen writes no number or sentence of its own beyond navigation words ("Slide n of N", "Section 9", "Detail in appendix", "Not yet") and the stale notice, which quotes the two versions from the case. (3) The web adds exactly one mutation, `recordReport`. It signs, approves and installs nothing, and the model token is sent only in a model mode.

- **M6.** (1) No pinned name changed; the manual and README name the screen and command as they ship. (2) Every number in the docs is the reference case's own (pages, sizes, counts), re-read after the final run. (3) No boundary moved; the docs describe the one new mutation and the opt-in model mode as they are.
- **M7.** (1) No pinned name changed; the twelve screenshots were captured from one suite run on a fresh throwaway stack. (2) The manual's figures are captures, not drawings. (3) Only the throwaway stack (`oak-s13`, ports 18080 and 15174) was used; the owner's stack was not touched.
- **M8.** (1) No pinned name changed. The Report screen's keys and the diagram scroller's name ("Topology diagram") are new, both covered by `report.spec.ts`. (2) The fixes make more numbers honest, not fewer: fixture-sourced figures now say "synthetic estimate", and a number without a unit is `unknown`. (3) No boundary moved; the narrator's rule 3 now names the same words the note check refuses.

## Closing review

One workflow: three finders (honesty of the composed report, robustness of the PDF and the
CLI, the web's keyboard and accessibility) and one skeptic told to refute each finding by
default. 21 findings were raised; 7 were refuted (A-2, A-4, A-5, R-5, H-7, H-8, H-10) and
14 survived. Each survivor's fix and its proof:

| Finding | Fix | Proof |
| --- | --- | --- |
| H-1 invisible characters split a forbidden word | refuse any Unicode category C character after NFKC | `test_report_notes.py`: zero-width space, soft hyphen, word joiner, right-to-left override |
| H-2 authority in other words | `AUTHORITY` widened (secure, safe, cleared, endorsed, vetted, verified, validated, …); narrator rule 3 names them | four probe sentences dropped |
| H-3 addresses and hosts | refuse `@`, any scheme, `mailto:` and a dotted host the slide does not hold | four probes dropped; a host on the slide kept |
| H-4 numbers in words, moved units, benefits | number words must be on the slide; a number's unit must sit beside it on one slide line; benefit words refused | six probes dropped |
| H-5 fixture runs labelled "measured" | evaluation metrics and samples, fixture component inputs and measurements, and calibration against a fixture are "synthetic estimate" | composer tests; R2 rule, mutation-checked |
| H-6 "as recorded" for a unit | every numeric intent field has a unit (schema-walk test); no unit means `unknown` | composer tests; R2 rule, mutation-checked |
| H-9 slide 3 title ignored unstated values | the title counts them | composer test |
| R-1 a unit taller than a page | units split by lines; a too-tall group may break | `test_no_unit_runs_off_its_page…`, killed by an unbounded limit |
| R-2 a long rationale failed the schema | report text to 12,000; visible clipping elsewhere | composer test with a 12,000-character rationale and a long reason |
| R-3 the page count pushed off the page | page count right-aligned, title truncated | footer test on every page |
| R-4 cubic wrapping | one normalisation, per-character widths | measuring-call count test |
| R-6 a predictable temporary file | `mkstemp` beside the target | planted-link test |
| A-1 slide keys swallowed table scrolling | nested scroll regions keep their keys | `report.spec.ts` on slide 9 |
| A-3 the diagram scroller was unreachable | a named, focusable region | `report.spec.ts` and axe |

## Retro

- **What worked:** composing the report as a pure document first, and rendering it second, meant one golden test, one guard and one set of agreement tests covered the PDF, the screen and the CLI at once. The guard composes live rather than reading the golden, so a composer regression cannot hide behind a refreshed fixture.
- **What cost time:** text-anchored patch scripts against files `ruff format` had already reflowed failed silently (`count == 0`) and had to be redone with reads. `SchemaRegistry` re-checking every schema on every call made the first guard take 46 s.
- **What to keep:** asking the owner again when an answer conflicts with a hard invariant (K3) and when a dependency fails review (`python-pptx`). Both questions changed the sprint for the better, cheaply, before any code depended on them.
