<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S7-001–008: MCP, portal and interface parity

## Status

- Owner/agent: Claude
- Started: 2026-08-21
- Last updated: 2026-08-21
- State: done
- Claimed tasks: `OAK-S7-001`–`OAK-S7-008`

## Outcome

An authorized engineering agent can drive the bounded design workflow through a typed MCP
server, a developer can run the same CLI commands against a remote control plane, and a
developer portal can display case and gate state through documented REST behavior — all
without any interface gaining deployment authority. A case created through MCP is visible
through the web workspace and CLI with candidate and bundle digests identical to REST, a
headless validator lets CI verify exported cases and compiled plans without a live server,
and a published compatibility policy governs every public surface before `0.1.0`.

## Context and invariants

Sprint 6 is merged; `main` is at `91485c1` (PR #10) and the repository is `0.6.0.dev6` with
CI green for the first time. Sprints 0–6 delivered the offline CLI journey, the persistent
PostgreSQL control plane with a 21-path `/v1` REST surface, the web workspace, the signed
typed runner, and the policy/adapter SDK with governed extensions. `oak-mcp` is still the
Sprint 0 placeholder that exits 69.

Governing requirements: `OAK-FR-CTL-001`, `OAK-FR-INT-001`–`006`, `OAK-NFR-UX-001`–`002`,
`OAK-NFR-SEC-001`–`005`, `OAK-NFR-PORT-001`–`002`. Governing ADRs: 0014 (design-case
interface parity) above all, plus 0002 (modular monolith), 0012 (control-plane
distributions), and 0015 (typed runner operations) for anything touching runner authority.
Threat-model lenses: TM-01 (prompt injection), TM-06–09 (confused deputy, authority
bypass), TM-16, TM-18. Recipes applied: Interface adapter (primary), Contract change and
Security review (secondary).

Hard invariants:

- MCP must not become an authority bypass. No tool may approve, sign, revoke, dispatch,
  resolve a secret, override policy, impersonate an actor, read arbitrary files, or execute
  a command. Runner apply stays absent. A tool that cannot be expressed as a bounded typed
  call onto an existing application service does not ship.
- `interface_origin` is audit metadata and never grants authority; its schema enum already
  reserves `mcp` and `portal`.
- Every interface constructs `CommunityControlPlane`, `DesignCaseService`, or
  `CandidatePlanningService` — never a repository directly.
- No `command`, `shell`, `executable`, or `argv` field may appear in any canonical document.
- `oak.interfaces` may import `application`, `bootstrap`, `contracts`, `domain` — not
  `adapters`; `tools/check_boundaries.py` enforces this.
- Compiled canonical artifacts are immutable and byte-stable; the reference case digests on
  this branch must equal those on `main`, verified directly by compiling both.
- Fail closed everywhere: unknown tools, methods, kinds, or schemas are refused, never
  skipped. Signature verification uses pinned keys, never a key embedded in the document.
- No REST breaking change: the OpenAPI compatibility baseline is not reset; this sprint
  adds no REST path and changes none.
- `.github/` is not edited.

## Scope

### In

- **MCP server (`OAK-S7-001`)**: a bounded stdio MCP server (`oak-mcp` and `oak mcp serve`)
  exposing exactly the ten interface-contract tools plus one explicitly documented
  operation-progress read query, with typed JSON Schemas, actor/tenant/version/idempotency
  context, fail-closed dispatch, and no generic shell/file/secret capability. The Sprint 0
  placeholder module is deleted, together with its dead `worker_main`/`runner_main`
  siblings.
- **Remote CLI mode (`OAK-S7-002`)**: a root `--server` option (env `OAK_SERVER`) that maps
  the design-journey commands onto the `/v1` REST surface through a bounded stdlib HTTP
  client, preserving output formats, stderr diagnostics, and exit-code semantics; commands
  without a REST surface fail closed with a stable error code.
- **Public compatibility policy (`OAK-S7-003`)**: `docs/compatibility.md` covering
  versioning and deprecation for canonical schemas, REST/OpenAPI, CLI, MCP, and the runner
  protocol before `0.1.0`.
- **Interface conformance (`OAK-S7-004`)**: one fixture driven across local CLI (file
  mode), remote CLI, REST, and MCP with semantic digests, stable error codes, and audit
  outcomes compared; PostgreSQL-gated like the existing persistent REST journey.
- **Backstage starter (`OAK-S7-005`)**: catalogue entity, software template, and portal
  card examples under `examples/backstage/` that use only documented REST behavior and
  links; a contract test pins every referenced path to the committed OpenAPI document; no
  Backstage type enters the core IR.
- **Generic portal/CI integration (`OAK-S7-006`)**: a signed webhook event example with a
  canonical `webhook-envelope` schema and pinned example public key, and a headless
  `oak validate` command that verifies exported cases, compiled plan bundles, and signed
  webhook examples without a live server.
- **MCP abuse tests (`OAK-S7-007`)**: prompt-injection content, oversized frames and
  arguments, confused-deputy actor, stale version, tenant crossover, attempted
  mutation/tool escalation, malformed frames — all denied before any side effect.
- **Documentation (`OAK-S7-008`)**: `docs/interfaces.md` with setup, the permission model,
  a capability matrix, and explicitly unavailable operations for Community; updates to
  `docs/development.md`, `docs/architecture.md`, `schemas/README.md`, `README.md`,
  `CHANGELOG.md`, and `STATUS.md`.

### Out

- Any REST path addition, removal, or change; the OpenAPI baseline stays untouched.
- Runner apply, approval, signing, revocation, dispatch, policy override, or secret
  resolution through MCP or remote CLI. The release/runner command group stays local-only.
- A live webhook dispatcher or subscription mechanism; Sprint 7 ships signed examples and
  a validator, not a delivery service.
- Backstage plugin code or any Backstage dependency; examples are YAML/documentation only.
- Real authentication or multi-tenant controls; the local actor/tenant model is unchanged.
- MCP resources/prompts/sampling capabilities; the first surface is tools-only.
- Fixing carried-forward known limitations that this sprint does not touch.

## Contract and data changes

- New canonical schema `webhook-envelope.schema.json` (version `0.1.0`) with example
  `examples/example-webhook-envelope.json`-equivalent YAML, registered in
  `EXAMPLE_BY_SCHEMA` and `schemas/README.md`. It wraps an audit event with a detached
  Ed25519 signature under the existing `verify_signed_document` convention. No workspace
  artifact kind is added; the envelope is a portal export shape, not workspace state.
- The MCP tool surface is a new public contract documented in `docs/interfaces.md` and
  governed by `docs/compatibility.md`; tool input schemas mirror the REST request model
  bounds exactly.
- CLI gains `--server` (root), `--case` (evaluate/select/assure/plan), and the `validate`
  and `mcp serve` commands. All additions are additive; no existing command changes
  meaning, output shape, or exit codes.
- No change to canonical workspace schemas, artifact kinds, digest computation, REST
  models, or the runner protocol.

## Milestones

1. **MCP server core (`OAK-S7-001`)** — `oak.interfaces.mcp` package with bounded stdio
   JSON-RPC framing, initialize/tools-list/tools-call lifecycle, the eleven-tool registry
   mapped onto `CommunityControlPlane`, local actor/tenant binding, and entrypoint
   replacement (placeholders deleted).
   Proof: unit tests for framing/limits and tool schemas; db-free integration test drives
   a real file-backed control plane through create→interpret→confirm over real MCP frames.
2. **Remote CLI mode (`OAK-S7-002`)** — stdlib REST client, `--server` routing for the
   design-journey commands, problem-details mapping onto existing exit codes, bounded
   operation polling, export/import directory parity.
   Proof: unit tests for the client mapping; integration test drives remote commands
   against an in-process HTTP server and compares emitted documents with local mode.
3. **Compatibility policy (`OAK-S7-003`)** — `docs/compatibility.md` published and linked.
   Proof: document review against every public surface; referenced gates exist in the
   Makefile.
4. **Portal/CI integration (`OAK-S7-006`)** — `webhook-envelope` schema + signed example +
   pinned example key, `oak validate export|bundle|webhook`, Backstage starter examples
   (`OAK-S7-005`) with the OpenAPI-reference contract test.
   Proof: `make validate` passes with the new schema registered; contract tests verify the
   signed example against the pinned key and refuse a tampered copy; validator exits 0 on
   the reference export/bundle and 2 on tampered copies.
5. **Interface conformance (`OAK-S7-004`)** — PostgreSQL-gated conformance suite comparing
   semantic digests, denial codes, idempotent retries, and audit `interface_origin` across
   local CLI, remote CLI, REST, and MCP.
   Proof: suite passes against the pinned local PostgreSQL with `OAK_TEST_DATABASE_URL`
   set; digests equal the file-mode journey.
6. **MCP abuse suite (`OAK-S7-007`)** — adversarial coverage listed in Scope.
   Proof: every abuse case is denied with a stable code before any state change; the
   db-free suite runs inside `make test-integration` without PostgreSQL.
7. **Documentation and closure (`OAK-S7-008`)** — `docs/interfaces.md`, doc updates,
   CHANGELOG, STATUS, ExecPlan moved to completed.
   Proof: full `make check` green (verified by counting `make: ***` lines, not exit code);
   byte-stability of the reference case verified directly against `main`; exit
   demonstration recorded.

Rollback for every milestone: revert the branch. All changes are additive; no existing
artifact kind, canonical schema, digest, REST path, or state transition changes, and file
mode remains the source of truth.

## Verification

Unit and contract suites cover MCP framing limits, tool-schema validation, tool-registry
pinning against the documented capability matrix, remote-client problem mapping, webhook
signature verification with tampering, and validator refusal paths. Integration suites
cover the db-free MCP journey and abuse cases, remote CLI against a live in-process server,
and the PostgreSQL-gated four-interface conformance run. E2E covers the installed
`oak-mcp` entrypoint handshake and `oak validate` against a real exported workspace.
`make check` aggregates all gates; the PostgreSQL legs run locally with
`OAK_TEST_DATABASE_URL` set because CI provisions no database. Byte-stability is verified
directly by compiling the reference case on `main` and on this branch and comparing
deployment-bundle, runner-plan, semantic-manifest, and selected-candidate digests.

## Security, privacy and authority review

The MCP server and remote CLI are transports onto the same application commands and add no
authority. MCP tool arguments are untrusted input: frames are size-bounded before parsing,
tool names outside the fixed registry are refused, argument schemas are closed
(`additionalProperties: false`) with the same bounds as REST models, and the four
execution-field names remain impossible in any canonical document. The claimed actor and
tenant in a tool call are verified against the server's bound local identity exactly as
the REST layer verifies headers: a foreign tenant receives an opaque denial that leaks no
existence information, and a foreign actor receives `OAK-ACTOR-DENIED`. Approval, signing,
revocation, dispatch, secret resolution, policy override, and runner apply are absent from
both new transports by construction, and a contract test pins the tool registry so a new
tool cannot appear without failing the capability-matrix test. Prompt-injection text
inside briefs remains inert quarantined data under the Sprint 1 intake policy. The remote
CLI sends no secret values, derives idempotency keys from content digests, and treats
problem responses as data. Webhook examples are verified against a pinned committed public
key, never a key carried in the document; the signing private key was discarded and no
private key is committed. Error output never includes stack traces, provider output, or
payload bodies. No secret values appear in tool results, frames, argv, or logs.

## Operational and rollback plan

The MCP server runs on stdio under the same environment variables as `oak-api`
(`OAK_DATABASE_URL`, `OAK_ARTIFACT_ROOT`, `OAK_LOCAL_ACTOR`, `OAK_LOCAL_TENANT`) and holds
no state of its own; stopping the process is a complete rollback. Remote CLI mode is
opt-in per invocation and falls back to local file mode by default. The validator is
read-only. Reverting the branch restores the placeholder entrypoint and removes every new
surface; no migration, key rotation, or data change is involved.

## Progress

- [x] 2026-08-21 ExecPlan authored; tasks claimed in `STATUS.md`; branch
  `claude/sprint-7-mcp-portal-interface-parity` created from `origin/main` at `91485c1`.
- [x] 2026-08-21 M1 MCP server core: `oak.interfaces.mcp` with bounded stdio JSON-RPC
  framing (1 MiB frame limit enforced during read), the eleven-tool registry with closed
  schemas mirroring REST bounds, local actor/tenant authority, `oak-mcp` and
  `oak mcp serve` entrypoints, placeholders module deleted. 15 protocol unit tests, 6
  capability-matrix contract tests, and a db-free integration journey over real frames
  (create → interpret → confirm → generate → evaluate → out-of-band select → assure →
  compile, ending `bundle_compiled` at case `0.1.7`) all pass; full unit/contract suite is
  329 passed and strict mypy covers 112 files.
- [x] 2026-08-21 M2 remote CLI mode: root `--server`/`OAK_SERVER` routing, stdlib urllib
  client with problem-details mapping onto existing exit codes, deterministic derived
  idempotency keys, bounded operation polling (`OAK_REMOTE_TIMEOUT`), digest verification
  of every remotely fetched document written locally, export/import directory parity, and
  fail-closed `OAK-REMOTE-UNSUPPORTED` refusal for the eleven local-only command groups.
  Integration suite drives the real CLI against a live loopback uvicorn server backed by a
  file-mode control plane: full journey to `0.1.7`, remote export imported locally with
  identical bundle digest, idempotent confirm replay, state denials, and unreachable/
  non-http server refusals. Full db-free `make`-equivalent suites pass (329 unit/contract,
  85 integration + 20 gated skips, mypy 113 files).
- [x] 2026-08-21 M3 compatibility policy: `docs/compatibility.md` covering the versioning
  model and per-surface rules for canonical schemas, REST/OpenAPI (baseline-gate
  semantics), CLI (exit codes, output shapes, remote parity), MCP (tool registry,
  permanent prohibition list, pinned protocol revisions), the runner protocol, and the
  pre-`0.1.0` deprecation process.
- [x] 2026-08-21 M4 portal/CI integration: canonical `webhook-envelope.schema.json` with a
  really-signed committed example (`examples/example-webhook-envelope.yaml`; publisher key
  pinned in `examples/portal/webhook-publisher.identity.json`, private half generated in a
  throwaway process and discarded); `oak validate export|bundle|webhook` headless
  validator that replays workspace import, verifies bundle schema/digest-links/inert
  status/execution-field ban, and verifies webhooks against the pinned key only; Backstage
  catalogue/template/proxy-card examples under `examples/backstage/`. Six validator
  integration tests (tamper, poison, missing-file, wrong-key denials) and five portal
  contract tests (every referenced REST path exists in the committed OpenAPI document, no
  privileged operation in wiring, no Backstage type in `src/`, identity file is public
  material only) pass; `make validate` passes with the schema registered in
  `EXAMPLE_BY_SCHEMA` and `schemas/README.md`.
- [x] 2026-08-21 M5 interface conformance: PostgreSQL-gated suite runs the reference
  scenario across four legs — file-mode application services, REST over a live loopback
  uvicorn server, real MCP frames, and the installed CLI in `--server` mode — each in an
  isolated environment with one fixed clock. Candidate/selected/assurance/bundle/
  semantic-manifest digests, question sets, forbidden-transition and stale-version denial
  codes, idempotent retry convergence, final version/status, and the audit event sequence
  are compared and identical; `interface_origin` is asserted per transport including the
  deliberate out-of-band selection in the MCP leg. The runner-plan digest is asserted
  lineage-specific (it binds the exact case document, whose audit head and origin are
  transport metadata) rather than cross-interface equal. Passed against pinned
  PostgreSQL 17.6.
- [x] 2026-08-21 M6 MCP abuse suite: 13 adversarial integration tests — prompt injection
  stays inert quarantined data, oversized content and an unbounded newline-free frame are
  bounded (the reader aborts before buffering the whole line), a 2000-deep frame is a
  clean parse error (fixing an unhandled `RecursionError` in the frame parser and hardening
  the tool executor), actor impersonation and tenant crossover are denied before dispatch
  (tenant opaquely), stale versions are retriable denials, every privileged tool name and
  non-tool method is refused, a forbidden execution field in a target profile is refused
  with no operation enqueued, malformed frames keep the session alive, and a denied
  mutation leaves no workspace or operation state. Runs db-free in `make test-integration`.
- [x] 2026-08-21 M7 documentation and closure: `docs/interfaces.md` (setup, permission model,
  capability matrix, unavailable operations), `docs/compatibility.md`, and
  development/architecture/README updates; CHANGELOG and STATUS updated; e2e entrypoint tests
  for `oak-mcp` and `oak validate`. Full `make check` green (verified by counting `make: ***`
  lines: 0) — 335 unit/contract, 126 integration (+4 gated skips) against pinned PostgreSQL
  17.6, 16 e2e, plus every static gate; the OpenAPI contract and baseline are unchanged.
  Byte-stability verified directly against `main` (identical deployment-bundle, runner-plan,
  semantic-manifest, selected-candidate digests, case `0.1.7`).
- [x] 2026-08-21 Adversarial audit and remediation: six-lens multi-agent audit with
  independent per-finding refutation plus owner verification of every candidate; six real
  defects fixed and four scoped limitations recorded (see Post-implementation audit). Full
  `make check` re-run green after the fixes; byte-stability re-verified unchanged.
- [x] 2026-08-21 Remote CI green on PR #11. One e2e assertion scraped Rich-rendered
  `oak --help` for `--server` and failed on the CI runner while the option worked; it was
  replaced with behavioural assertions (invocable subcommands, `OAK-VALIDATE-KIND`,
  `OAK-REMOTE-UNSUPPORTED`, `OAK-REMOTE-UNAVAILABLE`), which prove more than the presentation
  check did. Rule recorded for later sprints: never assert on Rich-formatted help output.

## Decisions

- 2026-08-21 The MCP server implements the stdio transport in-tree over stdlib JSON-RPC
  2.0 rather than adopting the `mcp` SDK package. The server needs only
  initialize/ping/tools-list/tools-call on newline-delimited stdio; the SDK would add five
  new runtime dependencies (httpx, httpx-sse, sse-starlette, pydantic-settings,
  python-multipart) for transports Community does not expose, enlarging the supply chain
  and the audit surface of the one interface whose whole point is boundedness. The
  protocol versions accepted are pinned (`2025-06-18`, `2025-03-26`) and recorded in the
  compatibility policy; revisit if Community later needs HTTP transports or
  resources/prompts capabilities.
- 2026-08-21 The MCP surface adds one read-only tool, `oak_operation_get`, beyond the
  ten-tool interface-contract table. Three contract tools are asynchronous proposals that
  return operation references; without an operation-progress query the references are
  unusable. The interface contract's query paragraph explicitly names operation progress
  as a permitted query class, and the tool maps onto the same `get_operation` query as
  `GET /v1/operations/{operation_id}`. Cancellation is deliberately not exposed.
- 2026-08-21 Remote CLI mode requires an explicit design-case identifier (positional where
  one exists, `--case` on `evaluate`/`select`/`assure`/`plan`) and refuses to guess with
  `OAK-REMOTE-CASE-REQUIRED`. A server may hold many cases; inferring "the" case would be
  interface-owned defaulting, which the interface-adapter recipe forbids.
- 2026-08-21 The remote client uses stdlib `urllib.request` with explicit timeouts rather
  than adding a runtime HTTP dependency. One bounded request per command against a local
  control plane does not justify enlarging the supply chain; `httpx` stays dev-only.
- 2026-08-21 Commands without a REST surface (`init`, `serve`, `keys`, `sign`, `approve`,
  `revoke-approval`, `dispatch`, `ingest`, `gitops`, `policy`, `render`, `extensions`,
  `validate`, `mcp`) fail closed in remote mode with `OAK-REMOTE-UNSUPPORTED` instead of
  silently falling back to local state, so a scripted remote journey can never half-apply
  locally. The capability matrix documents each.
- 2026-08-21 The webhook envelope became a canonical schema (`webhook-envelope.schema.json`)
  rather than a free-form example, because `oak validate webhook` must fail closed against
  a defined contract. The example's signature verifies against a pinned committed public
  key; the private half is generated in a throwaway directory and discarded, so the
  example is verification-reproducible but not signing-reproducible, which is the correct
  asymmetry for committed fixtures.
- 2026-08-21 `questions` parity needs no new REST endpoint: the full question documents
  live in the case document's `unresolved_questions`, so remote CLI and MCP derive the
  same `QuestionResult` shape from the case query that local CLI derives from
  `DesignCaseService.questions()`.

## Post-implementation audit

A six-lens multi-agent adversarial audit ran against the Sprint 7 source diff (MCP
authority, remote-CLI parity/safety, validator/webhook signing, parsing/injection/limits,
contracts/conformance/boundaries, and a repo-wide latent sweep). It produced 11 candidate
findings; each was routed to an independent skeptic prompted to refute it by default. Two
verifiers completed and CONFIRMED both of their findings; the remaining eight skeptics were
interrupted by a session limit, so every candidate they would have judged was verified
directly against the code by the owner instead. No candidate was accepted without local
reproduction. The authority invariant held: no MCP tool, remote-CLI path, portal example,
or webhook could reach a forbidden capability — every survivor was a robustness,
input-safety, or conformance-honesty defect, not an authority bypass.

Fixed:

- **Untrusted-YAML anchor expansion in `oak validate webhook` (high).** `validate_webhook`
  parsed the envelope with `load_yaml_document`, which permits YAML anchors/aliases; the
  repo ships `load_alias_free_yaml_document` precisely because anchor expansion lets a tiny
  source allocate an enormous structure at parse time, before any schema or signature check.
  A CI/portal running the validator on a hostile ~255-byte envelope could be memory-pinned.
  The validator now uses the alias-free reader.
  (`tests/integration/test_validate_cli.py::test_a_yaml_alias_bearing_webhook_envelope_is_refused`)
- **Wrong-shape server responses crashed the remote CLI (medium).** A hostile or
  version-skewed control plane returning 200 with well-formed JSON of the wrong shape made
  the remote command handlers raise `KeyError`/`TypeError`, which no command's except tuple
  catches — a Python stack trace and exit 1 instead of the documented stable code and exit 2.
  A `require_field` guard now navigates every server-supplied document and raises
  `OAK-REMOTE-PROTOCOL` on any missing or mistyped field; `write_export_directory` type-checks
  each manifest entry.
  (`tests/integration/test_remote_cli.py::test_malformed_server_responses_are_stable_protocol_errors_not_crashes`)
- **Execution-field ban was enforced inconsistently across validator kinds (medium).**
  `validate_bundle` scanned for `command`/`shell`/`executable`/`argv`, but `validate_export`
  and `validate_webhook` did not, and the canonical `extensions` object is
  `additionalProperties: true`, so a byte-identical document rejected in a bundle passed as an
  export or webhook. Both now scan every canonical object/envelope for execution fields.
  (`test_an_execution_field_in_an_export_object_is_refused`,
  `test_an_execution_field_in_a_webhook_envelope_is_refused`)
- **A handler-internal error in the MCP server was mislabeled or fatal (medium).** A
  `KeyError` raised inside a tool handler was caught by `_call_tool`'s unknown-tool
  `except KeyError` and reported to the client as `OAK-TOOL-UNKNOWN`; a `TypeError` could
  escape `serve()` and kill the stdio session. The handler except now catches every
  non-domain exception as `OAK-INTERNAL`, and `serve()` guards each frame so no single frame
  can terminate the session.
  (`tests/integration/test_mcp_abuse.py::test_a_handler_internal_error_is_oak_internal_not_unknown_tool_or_a_crash`)
- **The MCP/REST bounds-parity contract test was vacuous (medium).** It checked only the two
  `create` fields and asserted the idempotency-key bounds against hardcoded literals, so a
  future widening of any other MCP bound would pass unnoticed. It now cross-checks every
  header-derived bound against the REST `app` header source and every identifier bound against
  the REST request models; a mutation test confirms it fails when a bound diverges. (No live
  divergence existed; every MCP bound was already equal-or-stricter.)
- **Remote `design` forwarded a short idempotency key to its second sub-call (low).** The
  create step derived its key but the interpret step forwarded a user `--idempotency-key`
  verbatim, so a sub-16-character key made create succeed then interpret fail the length
  check, leaving a half-applied journey. Both sub-calls now derive their key from the same
  identity.

Known limitations, deliberately not fixed in this sprint:

- **Remote-mode integrity depends on trusting the control plane.** The document check compares
  a returned document against a case reference from the *same* response, so it detects a
  corrupted, buggy, or version-skewed server, not a fully malicious one that returns matching
  (document, reference) pairs. Remote mode is for a control plane the operator trusts;
  independent integrity would need a pinned out-of-band digest, which the REST surface does not
  yet carry. Documented in the module docstring and CHANGELOG.
- **`oak validate bundle` binds only the digest edges that exist in a detached bundle.** The
  deployment-bundle → architecture-decision and runner-plan → deployment-bundle edges are
  checked, but `assurance-plan.json` and `semantic-manifest.json` carry no digest edge into the
  bundle spine, so a detached bundle directory could pair a genuine spine with a substituted
  assurance plan or manifest and still validate. The real integrity binding is the signed
  runner envelope and approval, a separate signed path; a review bundle is not a security
  artifact. The validator's guarantees are scoped accordingly in `docs/interfaces.md`.
- **The webhook envelope is an export/verification contract only.** Nothing dispatches
  webhooks; delivery-side replay protection (dedup by `delivery_id`, gap detection by
  `sequence`) is documented as a consumer obligation but unenforced by Community.
- **The MCP server serves one stdio client per process** with no concurrent-session model;
  concurrency-abuse coverage is process-level only.

## Discoveries and follow-ups

- The `interface_origin` schema enum already reserved `mcp` and `portal` since Sprint 1,
  so no schema change is needed for either new origin value.
- `case["unresolved_questions"]` carries complete question documents, which is what makes
  question parity across four interfaces possible with zero REST additions.
- The operation `result` document is the exact `to_document()` of the planning result, so
  remote CLI output parity for async commands falls out of the existing worker contract
  rather than needing any response reshaping.
