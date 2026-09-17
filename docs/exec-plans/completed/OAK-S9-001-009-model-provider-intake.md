<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S9-001–009: Optional model provider and natural-language intake

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-09-17
- Last updated: 2026-09-17 (complete; awaiting review)
- State: complete
- Claimed tasks: `OAK-S9-001`–`OAK-S9-009`

## Outcome

A user configures one model family — a free Hugging Face open model by default (looked up
against the live catalogue, not hard-coded), a hosted provider (OpenAI, Anthropic, Google
Gemini, Meta, xAI) with their own API key, or a local OpenAI-compatible server — and keeps the
credential on their own machine. With a model configured, a plain-language brief is the
default intake: the model produces a bounded, schema-valid *proposal*; the deterministic
interpreter merges it into a typed intent with `model_proposed` provenance and confidence;
every touched section opens a confirmation question; the existing five-question round asks the
reviewer to confirm, correct, reject or accept the risk; and candidates cannot be generated
until no model-proposed value is unconfirmed. The same journey with no model configured, or with
`--interpreter deterministic`, produces today's output byte for byte.

Demonstration:

```bash
oak models discover huggingface
oak models set-key huggingface --stdin < token.txt
oak models select huggingface openai/gpt-oss-120b
oak design brief.md
oak questions
oak confirm --answers answers.yaml
```

and, in the browser, Settings → Models → detect → token → key → select → create a prose case →
interpret → confirm with provenance badges → candidates.

## Context and invariants

`main` is at `62bc7a1`; `0.7.1` is published as a GitHub Release (2026-09-03). The LLM seat
already exists and is inert: `ModelInterpreterPort` (`src/oak/ports/interpreter.py`), the
closed `interpretation-proposal` schema, `validate_interpretation_proposal`
(`src/oak/compiler/interpretation.py`) and `DesignCaseService.optional_proposal`
(`src/oak/application/design_case.py`), which validates a proposal and discards it. No
interface reaches it; `tests/integration/test_offline_boundary.py` and `TM-13` (verdict
*structural*) pin the absence of any provider adapter.

Local terms: the **reference case** is `tests/runner_support.py::build_compiled_case` (fixed
clock `2026-08-18T12:00:00Z`) ending at `design-case.public-manual-qa@0.1.7`; its four tracked
digests are the **byte-stability baseline** (`deployment_bundle sha256:570abb66…`,
`runner_plan sha256:fad30959…`, `selected_candidate sha256:576b0ca6…`,
`semantic_manifest sha256:2ef34758…`), now pinned by
`tests/integration/test_reference_digests.py` together with the canonical bytes of the
deterministic intent for the YAML and prose briefs. A **proposal** is an
`interpretation-proposal` document; a **model-proposed value** is a scalar in `spec` whose
provenance `source` is `model_proposed`. **Model path** means `interpret` ran with a
proposal; **deterministic path** means it did not.

Governing requirements: `OAK-FR-CTL-003`, `-008`, `OAK-FR-INT-001`–`006`, `OAK-NFR-SEC-003`,
`OAK-NFR-UX-001`, `OAK-NFR-PORT-002`, `OAK-NFR-REL-002` (governance `docs/requirements.md`);
new `OAK-FR-INT-009` and `OAK-NFR-SEC-007` are added in Milestone 7. Governing ADRs: 0001,
0004, 0009, 0011, 0012, 0014 (governance series); implementation ADR 0003 and governance ADR
0016 are written in Milestone 7. Threat lenses: TM-01, TM-04, TM-10, TM-13, TM-14, TM-19
and the new TM-20. Recipes applied (`skills.md`): Compiler stage, Contract change, Interface
adapter, Workspace UI, Security review, Dependency and release, Documentation and ADR.

Owner decisions (2026-09-17): ship CLI, REST and web; OS keychain through an optional
`keyring` extra with a 0700/0600 file fallback; seven families including a local
OpenAI-compatible server; loopback middleware **and** a per-process capability token.

Hard invariants:

- **LLM output is untrusted proposal data.** A proposal never sets status, never confirms a
  claim, never bypasses the reviewer. Every model-proposed value carries
  `confirmation_required: true` and a question; candidates are refused while any remains.
- **Community works with no provider.** The deterministic path is unchanged and byte-identical;
  `make check` needs no network after bootstrap; no test needs a key.
- **The credential never enters canonical state.** Not in artifacts, exports, audit events,
  idempotency rows, OpenAPI examples, logs, error messages, MCP results or browser responses;
  key entry only through a hidden prompt, stdin, or a write-only REST body.
- **No authority bypass.** MCP gains no configuration tool and defaults to deterministic;
  remote CLI keeps refusing local-only commands (`models` joins the list).
- **Egress is pinned, not absent.** One transport module, a fixed host allowlist per family,
  HTTPS outside loopback, no redirects, no environment proxies, bounded reads, total deadline.
- No `command`, `shell`, `executable`, or `argv` field in any canonical document; the
  `tools/check_boundaries.py` rules hold (adapters own every third-party import).
- **Byte stability**: the four reference digests and the two golden intents are unchanged at
  every milestone; anything model-specific exists only when the model path ran.
- No AI-vendor attribution in commits or PR bodies; provider display names in product
  surfaces are the user's choices, not agent attribution.

## Scope

### In

- **`OAK-S9-001`** — reference-digest and golden-intent test, test isolation of model state,
  secret-scan shapes, boundary rule, egress module list, Sprint 9 registered in governance.
- **`OAK-S9-002`** — `_LoopbackGuardMiddleware` (Host allowlist, `Origin`, `Sec-Fetch-Site`),
  per-process capability token (`X-OAK-Model-Token`), `OAK_ALLOWED_HOSTS`, nginx frame
  headers, `SECURITY.md` and `RR-027` wording.
- **`OAK-S9-003`** — `SecretValue`, credential and configuration ports, file/keychain/env
  stores, `model-configuration` schema and example, `ModelConfigurationService`,
  `oak models`, `keyring` optional extra, `RR-040`.
- **`OAK-S9-004`** — `model_proposed` provenance and assumption source, `interpretation_proposal`
  artifact kind, admissible intent paths, proposal merge with per-section confirmation
  questions and the confirmation invariant, all ranked questions persisted, `interpreter`
  selector on CLI/REST/MCP, regenerated OpenAPI and web client, cross-interface conformance
  with the fake adapter.
- **`OAK-S9-005`** — `transport.py`, `providers.py` (seven profiles, three request shapes),
  `hosted_interpreter.py`, `huggingface_catalogue.py`, discovery, egress gates rewritten,
  `TM-13` → direct, `RR-039`/`RR-041`, provider fixtures, live smoke behind
  `OAK_LIVE_MODEL_TESTS`.
- **`OAK-S9-006`** — `/v1/models` resources, api-only Compose volume, operator docs.
- **`OAK-S9-007`** — Settings page, natural-language default intake, provenance on the
  confirmation screen, recovery actions, Playwright coverage, manual screenshot.
- **`OAK-S9-008`** — manual, ADRs (implementation 0003; governance 0016 mirrored with 0009),
  both repositories' docs, `AGENTS.md`, `skills.md`, governance root `CLAUDE.md` pointer.
- **`OAK-S9-009`** — closing adversarial audit, status/changelog, PR.

### Out

- MCP sampling (the client's own model interprets with no stored key) — follow-up.
- Proxy support for provider calls (`OAK_MODEL_PROXY`) — follow-up; environment proxies are
  deliberately ignored.
- Interpretation as a durable Operation; the call stays synchronous within a 55-second budget.
- Per-tenant token or cost budgets beyond one bounded request per interpret (`RR-041`).
- LLM assistance in candidate explanations or assurance drafting.
- Any release, version bump (`0.8.0` is suggested), PyPI or registry decision — the owner's.
- Provider SDKs or a runtime HTTP dependency.

## Contract and data changes

- `common.schema.json` and `design-case.schema.json` (both repositories): provenance and
  assumption `source` enums gain `model_proposed`. Conditionally compatible (loosened
  validation); changelog callout; no `schema_version` bump.
- `interpretation-proposal.schema.json`: optional `version` (semver). Additive.
- `workspace-manifest.schema.json`: artifact `kind` enum gains `interpretation_proposal`;
  registered in `KIND_SCHEMA`/`JSON_MEDIA_KIND`. Additive; a `0.7.1` install cannot import an
  export that carries one (stated in `docs/compatibility.md`).
- New canonical schema `model-configuration.schema.json` (`0.1.0`) with example.
- REST: additive `/v1/models*` resources; optional `interpreter` query on `:interpret`;
  optional `X-OAK-Model-Token` header on `:interpret`, required on the new mutating routes;
  new status codes 429 (`OAK-MODEL-RATE-LIMITED`) and 403 (`OAK-ORIGIN-DENIED`,
  `OAK-MODEL-TOKEN-REQUIRED`), 400 (`OAK-HOST-DENIED`). Compatibility baseline is not reset.
- CLI: new local-only `oak models`; `oak design --interpreter`; `oak questions` output gains
  provenance lines and a "N more" count (human output only).
- MCP: `oak_design_case_interpret` gains an optional `interpreter` argument; tool set
  unchanged.
- Audit: `brief_interpreted` gains `extensions["oak.community/interpreter"]` on the model path
  only. Intent gains `extensions["oak.community/interpretation_proposal_ref"]` on the model
  path only.
- New `OAK_*` variables (all documented in `docs/configuration.md`): `OAK_ALLOWED_HOSTS`,
  `OAK_CREDENTIALS_DIRECTORY`, `OAK_MODELS_DIRECTORY`, `OAK_MODEL_KEY_{HUGGINGFACE,OPENAI,
  ANTHROPIC,GEMINI,META,XAI}`, `OAK_MODEL_ENDPOINT_LOCAL`, `OAK_MODEL_TOKEN`,
  `OAK_MODEL_TIMEOUT_SECONDS`, `OAK_MODEL_DISCOVERY_CACHE_SECONDS`, `OAK_LIVE_MODEL_TESTS`.
- New `OAK-*` codes regenerated into `docs/error-codes.md` with two new families.
- Residual-risk register: `RR-039`, `RR-040`, `RR-041` (count 38 → 41 in the five live
  quotes, following the `b954830` precedent).
- Dependencies: `keyring` as the optional extra `keychain`; no runtime HTTP dependency.

## Milestones

### Milestone 0 — Branch, plan, baseline, pre-emptive gates (`OAK-S9-001`)

- Work: branch `model-provider-intake` from `origin/main` (`62bc7a1`); this plan;
  `tests/integration/test_reference_digests.py`; `examples/briefs/public-manual-qa-prose.md`;
  `tests/conftest.py`; secret-scan shapes and `tests/contract/test_secret_shapes.py`;
  `THIRD_PARTY_FORBIDDEN` provider roots with a firing fixture; `NETWORK_MODULES` widened;
  governance Sprint 9 (`sprints.md`, `STATUS.md`, `spec-manifest.yaml`, `VERSION`,
  `CHANGELOG.md`, `README.md`).
- Proof: `make check` with zero `make: ***` lines; the digest test passes; governance
  `make validate` passes.
- Rollback: delete the branch; restore the governance files from the scratchpad copies.

### Milestone 1 — Loopback hardening and capability token (`OAK-S9-002`)

- Work: `_LoopbackGuardMiddleware` in `src/oak/interfaces/api/app.py`; `create_app(…,
  allowed_hosts=None, model_token=None)`; token minting in `server.py` and `oak serve`;
  `OAK_ALLOWED_HOSTS`; codes `OAK-HOST-DENIED`, `OAK-ORIGIN-DENIED`, `OAK-MODEL-TOKEN-REQUIRED`;
  ten test call sites move from `http://test` to `http://127.0.0.1`; nginx frame headers;
  `SECURITY.md`, `RR-027`, `docs/operations.md`, `docs/compatibility.md`.
- Proof: `tests/integration/test_loopback_hardening.py`; `make openapi-compatibility` clean;
  `curl -H 'Host: evil.example' http://127.0.0.1:8080/v1/design-cases` → 400.
- Rollback: revert the commit.

### Milestone 2 — Credential store, model configuration, `oak models` (`OAK-S9-003`)

- Work: `src/oak/domain/secrets.py`; `src/oak/ports/model_configuration.py`;
  `src/oak/adapters/credentials/`; `schemas/model-configuration.schema.json` + example;
  `src/oak/application/model_configuration.py`; bootstrap factories; `oak models`
  (`families`, `status`, `set-key`, `remove-key`, `select`, `token`); `keyring` extra and mypy
  override; `docs/dependencies.md` review; configuration rows; `RR-040`; local-only list.
- Proof: unit tests for every store and for `SecretValue`; CLI round trip with a fixture key
  showing `-rw-------` and no key in any output; remote refusal; count gate at 39.
- Rollback: revert; `rm -rf ~/.oak/credentials ~/.oak/models`.

### Milestone 3 — Proposal merge seam with the fake adapter (`OAK-S9-004`)

- Work: enum additions; optional proposal `version`; `interpretation_proposal` kind;
  `src/oak/contracts/intent_paths.py`; compiler merge, `SECTION_CONFIRMATION_TABLE`,
  invariant, all-questions persistence; `interpret(interpreter=)` through service, control
  plane, CLI, REST (optional query), MCP (optional argument, deterministic default);
  regenerated OpenAPI and web client; `web/src/claims.tsx`; `tests/model_support.py`;
  cross-interface conformance with the fake; docs.
- Proof: golden intents unchanged; the new merge, service and conformance tests; existing
  conformance suite untouched; `compatibility_errors == ()`.
- Rollback: revert; enum widening is backwards-compatible.

### Milestone 4 — Transport, providers, hosted interpreter, catalogue, egress gates (`OAK-S9-005`)

- Work: register and threat-coverage first (`RR-039`, `RR-041`, `TM-13` direct, tally), then
  the gate rewrite and the four adapter modules in one commit; discovery; `oak models
  discover`; `create_model_interpreter()`; configuration rows; codes; provider fixtures; live
  smoke.
- Proof: transport, profile, interpreter and catalogue unit tests offline; offline-boundary
  suite green with the new gates; `make check` with sockets broken after bootstrap; count gate
  at 41; a hand-verified live run recorded here.
- Rollback: revert the adapters commit, then the register commit.

### Milestone 5 — REST model endpoints, OpenAPI, Compose (`OAK-S9-006`)

- Work: request/response models; five closures with the token dependency; `CLIENT_SOURCE`;
  regenerated artifacts; Dockerfile mount point; `compose.yaml` api-only volume; operations
  and interface docs.
- Proof: `tests/integration/test_models_api.py`; OpenAPI gate clean; Docker-gated hardening
  assertions; nginx round trip.
- Rollback: revert; endpoints are additive.

### Milestone 6 — Web settings and natural-language intake (`OAK-S9-007`)

- Work: `SettingsPage.tsx`, routes, masthead chip, `CaseListPage`, `CasePage`,
  `ConfirmPage`, `ReviewPage`, `problems.tsx`, styles, footer; `web/e2e/models.spec.ts`;
  manual screenshot `11-models`.
- Proof: web build, typecheck, format; `make web-e2e` including the new spec; journey spec
  unchanged.
- Rollback: revert.

### Milestone 7 — Documentation, ADRs, governance (`OAK-S9-008`)

- Work: manual chapters 3 and 4 and PDF; implementation ADR 0003; governance ADR 0016
  mirrored with ADR 0009; every implementation and governance document named in the approved
  plan; governance root `CLAUDE.md` pointer.
- Proof: `make check`; governance `make validate`; ADR-reference and assurance-claim tests.
- Rollback: revert; restore governance files from scratchpad copies.

### Milestone 8 — Closing audit, verification, PR (`OAK-S9-009`)

- Work: multi-agent adversarial audit with independent refute-by-default skeptics; fixes with
  pinning tests; this plan's audit section; move to `completed/`; status and changelog in both
  repositories; PR.
- Proof: zero `make: ***` lines with and without `OAK_TEST_DATABASE_URL`; digests re-verified;
  `git grep -n oak-test-key` only under tests.

## Verification

- Unit: credential stores, `SecretValue`, configuration service, proposal merge, section
  questions, ranking determinism, transport rules, provider profiles, hosted interpreter,
  catalogue.
- Contract: secret shapes, boundaries (with the new firing fixture), configuration reference,
  error-code index, schema conformance for the new schema, generated OpenAPI equality and
  compatibility, MCP capability matrix, ADR references, assurance claims.
- Integration: reference digests and golden intents, offline boundary (new gates), loopback
  hardening, design-case service model path (commit shape, refusals, raw-bytes absence,
  confirmation invariant), model interface conformance, models API, remote CLI refusal.
- End to end: CLI journey with a fixture key; Playwright settings and journey; Docker-gated
  volume ownership.
- Security: key-leak grep over CLI output, REST bodies, MCP results, artifacts, exports,
  database rows and OpenAPI; egress under socket breakage; brief→proposal→spec injection.
- Failure and retry: provider unavailable, malformed, rate limited, quota exhausted, key
  rejected, key under-scoped, model retired, endpoint invalid, token missing — each with a
  stable code, nothing committed, and a stated remedy.

## Security, privacy and authority review

Input trust: the brief is untrusted; the proposal is untrusted model output bound to the
source record by digest, validated against a closed schema, restricted to admissible paths and
bounded values, re-validated after every claim, and merged only with `confirmation_required`
provenance and a confirmation question. Sensitive data: the credential exists in the OS
keychain or a 0600 file, is revealed per call inside the transport, and is never written to
canonical state, logs, errors or responses; brief content leaves the machine only after the
user selects a hosted model (`RR-039`). Identity and tenant: unchanged; the credential endpoints
are loopback-only and token-gated (`RR-040` records the residual). Privileged operations: none
new — the model proposes, the reviewer decides, the runner is untouched. Failure state: every
provider failure is a stable, non-fabricating refusal that commits nothing. Audit: the model
path records family, model, provider route and proposal digest in the `brief_interpreted`
event; the proposal is an immutable artifact.

## Operational and rollback plan

Feature flag is configuration: no model configured means today's behaviour. Compose gains an
api-only named volume whose loss means keys are re-entered (never backed up with artifacts).
The token rotates per process start. Rollback of any milestone is a revert; schema changes are
additive; a `0.7.1` install cannot import an export carrying an `interpretation_proposal`
artifact, which `docs/compatibility.md` states.

## Progress

- [x] 2026-09-17 Milestone 0 in progress: branch created; digest and golden-intent test,
  prose fixture, conftest isolation, secret shapes, boundary rule and fixture, egress module
  list landed; governance Sprint 9 registered and `make validate` passes.

- [x] 2026-09-17 Milestone 1: `_LoopbackGuardMiddleware`, `verify_model_token` and the
  per-process token file landed with `tests/integration/test_loopback_hardening.py`,
  `tests/unit/test_api_token.py` and the bind-warning test; ten API tests moved to a loopback
  base URL; `OAK_ALLOWED_HOSTS`/`OAK_CREDENTIALS_DIRECTORY`/`OAK_MODELS_DIRECTORY`
  documented; nginx frame headers; `SECURITY.md`, `RR-027`, operations and compatibility
  updated; error reference regenerated with two new families.

- [x] 2026-09-17 Milestone 2: `SecretValue`, the family table, credential and configuration
  ports, file/keychain/environment stores, `model-configuration` schema and example,
  `ModelConfigurationService`, bootstrap factory, `oak models`, the `keychain` extra with its
  dependency review, `RR-040` (count 39), configuration rows and the local-only lists landed;
  unit and CLI tests pass; the error reference is regenerated.

- [x] 2026-09-17 Milestone 3: `model_proposed` in both provenance enums (both repositories),
  optional proposal `version`, the `interpretation_proposal` artifact kind,
  `oak.contracts.intent_paths` (101 admissible paths, schema-derived and pinned by
  `tests/contract/test_intent_paths.py`), the merge in `DeterministicBriefInterpreter`
  (`SECTION_CONFIRMATION_TABLE` for all sixteen sections, bounds, per-claim schema
  re-validation, `OAK-INT-PROPOSAL-REJECTED`/`-UNANSWERED` findings, in-memory `rank_hint`,
  every ranked question persisted), `DesignCaseService.interpret(interpreter=)` with the
  model-path-only proposal artifact, intent reference and audit extension, the confirmation
  status guard, section-level `reject`, the `candidates` refusal, `--interpreter` on
  `oak design` (local and remote, `OAK_MODEL_TOKEN`), the optional REST query and header
  (token demanded exactly when the model would be spent), the optional MCP argument with a
  deterministic default, regenerated OpenAPI and web client (compatibility check clean), the
  `proposal` claim badge, `tests/model_support.py`, `tests/unit/test_proposal_merge.py`,
  `tests/integration/test_model_interpretation_service.py` and
  `tests/integration/test_model_interface_conformance.py` (file, REST and MCP legs equal);
  the golden-bytes and reference-digest tests are unchanged and green.

- [x] 2026-09-17 Milestone 4: `transport.py` (host allowlist before any socket call, https
  except loopback for `local`, no redirects, no environment or system proxies, verified TLS,
  per-packet deadline, fixed messages), `providers.py` (seven profiles, catalogue parsers,
  chat-candidate rules, status map), `hosted_interpreter.py` (one request plus one bounded
  retry, key per call, strict JSON schema, bounded claims, digest-only extension) and
  `huggingface_catalogue.py` (anonymous two-catalogue lookup, licence and namespace filter,
  structured-output requirement, pinned fallback) landed with 60 unit tests; the egress gates
  were rewritten (adapter set pinned by name, non-transport modules proved network-free,
  deterministic journey checked in a fresh interpreter); `TM-13` moved to **direct** with a
  rewritten absence section; `RR-039` and `RR-041` added (count 41); the four configuration
  rows and the `live` marker are documented; `tests/live/test_provider_smoke.py` is skipped
  unless `OAK_LIVE_MODEL_TESTS=1`.

- [x] 2026-09-17 Milestone 5: `/v1/models` status, credential, selection and discovery
  resources with the capability token as a dependency (refused before the body is parsed),
  `api_key` write-only with no example, `no-store` on every response, the generated
  TypeScript client, the `oak-model-state` volume on the api service with its mount point
  created `0700` in the image, operations and interfaces documentation, and
  `tests/integration/test_models_api.py` plus the Compose ownership assertions in
  `web/e2e/hardening.spec.ts`.

- [x] 2026-09-17 Adversarial review of the Milestone 4 provider layer: six reviewers across
  credential leakage, egress bypass, hostile provider responses, bounds and determinism,
  catalogue trust and documentation honesty, with two independent skeptics per finding. 27
  findings, 21 confirmed. All confirmed findings are fixed with regression tests; the review
  and its outcome are summarised in `## Post-implementation audit`.

- [x] 2026-09-17 Milestone 6: the Models settings page (token from the `#token=` fragment or
  pasted, stripped from the address bar, held in `sessionStorage` only), plain-language-first
  intake with a structured toggle, the interpreter chip in the masthead, model provenance on
  the confirmation screen with five questions per round, model-failure recovery in
  `problems.tsx`, `web/e2e/models.spec.ts` (including a `page.on("response")` check that no
  response body ever carries the key, and an axe pass), and the `11-models` manual capture.

- [x] 2026-09-17 Milestone 7: the manual's "no model adapter ships" passages corrected and an
  optional model-provider section added to the workspace chapter; ADR-0016 in governance and
  mirrored here; ADR-0003 recording this build's transport, loopback, bounds and token
  decisions; `AGENTS.md` boundary, architecture rule and two Code Review Rules; the
  `skills.md` routing row and recipe; `TM-20` and a real `TM-13` mitigation column; the
  secrets invariant distinguishing target secrets from provider credentials; the interface
  contract's permanent MCP and remote-CLI prohibition; `OAK-FR-INT-009` and
  `OAK-NFR-SEC-007` with their traceability rows; terminology; evidence sources; and the
  governance `CLAUDE.md` pointer.

## Decisions

- 2026-09-17 Standard-library transport in one module; no `httpx`, no provider SDKs. Reason:
  `docs/dependencies.md` precedent and ADR-0009; one bounded request per interpret does not
  justify a runtime HTTP dependency; six SDKs would dominate the release closure.
- 2026-09-17 Merge seam is inside the single `interpret` commit (no new event type, no case
  version shift). Reason: the source record and bytes are already on the draft case; a
  persisted pre-interpret step would shift `If-Match` and the audit sequence; a
  post-interpret step is blocked by the state machine.
- 2026-09-17 One confirmation question per touched section, plus a status guard, so a model
  value can never reach candidates unconfirmed. Reason: `confirmation_required` was decorative
  and confidence is model-reported.
- 2026-09-17 All ranked questions are persisted; five are presented per round. Reason: the
  model path can produce more than five, and questions dropped at interpret time could never be
  asked (no transition back to draft).
- 2026-09-17 MCP defaults to deterministic; an agent must opt in per call. Reason: the key
  belongs to the operator, not to the calling agent.
- 2026-09-17 Provider display names are permitted in product surfaces; `OAK-FS-001`'s scope
  was agent attribution, which stays neutralized.
- 2026-09-17 A `reject` on a section-level question removes the model-proposed values in
  that section and keeps the brief's explicit values; a section with no model value (the
  deterministic hardware question) is emptied rather than deleted, which also fixes a latent
  contract failure (`reject` on `/spec/hardware` used to delete a required section). Reason:
  the claims under review at a section path are the model's, and a required section must
  survive every decision.
- 2026-09-17 The REST route resolves the interpreter before it demands the token, so the
  token is required exactly when the operator's credential would be spent (`model`, or
  `auto` on a prose brief with a model configured) and never for deterministic work.
- 2026-09-17 `create_model_interpreter()` returns `None` until `OAK-S9-005`; `--interpreter
  model` therefore refuses with `OAK-MODEL-NOT-CONFIGURED` on this branch state. Reason: no
  hosted adapter exists yet and the refusal is the honest answer. Superseded by Milestone 4:
  it now builds a `HostedModelInterpreter` from the stored selection, and returns `None` only
  when no selection exists or its default interpreter is deterministic.
- 2026-09-17 Gemini is listed through the native Generative Language API but called through
  its documented OpenAI-compatible endpoint on the same host. Reason: one request shape
  serves five of the seven families, the compatibility layer is the only Gemini surface that
  accepts the OpenAI `response_format.json_schema` spelling the rest of the code already
  builds, and the host allowlist is unchanged either way.
- 2026-09-17 A model identifier is a bare name or one `namespace/name`. Reason: a hostile
  catalogue entry of `https://evil.example/model` satisfied the identifier pattern and was
  accepted by the permissive families; ids never address a host, so the rule costs nothing.
- 2026-09-17 The transport reads with `read1`, not `read`. Reason: `read` blocks until it has
  a whole chunk, so a provider trickling one byte at a time held the connection for the full
  body while every individual socket read stayed inside its own timeout. The first version of
  the deadline test took 62 seconds to fail; it now cuts off in under two.
- 2026-09-17 The deadline is enforced by wrapping the response's file object, installed
  through the connection's `response_class`. Reason: a socket timeout bounds one receive, not
  a request, and `http.client` reads the status line and each header separately, so a
  provider dribbling its header held the request open for as long as it liked. `socket.
  makefile` is read-only on a real socket, and `HTTPResponse.begin()` runs after
  `__init__`, so the response class is the only seam that covers the whole exchange.
- 2026-09-17 The egress gate is structural as well as enumerative: every top-level import
  under `src/oak` must resolve to the standard library, `oak`, or a declared distribution.
  Reason: the review demonstrated the enumerative gate by adding a module importing
  `litellm`, then `together`, then `replicate` — each invisible to a list of the SDKs we had
  thought of, each caught by the declared-dependency rule.
- 2026-09-17 The capability token is a FastAPI dependency, not a check inside each handler.
  Reason: dependencies resolve before the body is parsed, so an unauthorised caller is
  refused without its request being examined, and without being told what was wrong with it.

## Post-implementation audit

Run after Milestone 4, before the REST surface was exposed, against the provider layer:
transport, provider profiles, hosted interpreter, catalogue lookup, the rewritten egress
gates and the security documentation. Six reviewers took one lens each — credential leakage,
egress bypass, hostile provider responses, bounds and determinism, catalogue trust,
documentation honesty — and every finding went to two independent skeptics, one instructed to
refute it and one to judge whether it was consequential in practice. Both were told to settle
it by running code rather than by reading it.

27 findings, 21 confirmed, all fixed with regression tests. The ones that mattered:

| Finding | Why it mattered |
|---|---|
| `is_loopback_host` used a string prefix, so `127.evil.example.com` was "this machine" | The `local` family speaks plain http *because* the bytes stay on the machine. The brief, and a bearer token if one was stored, would have gone in cleartext to a host whose owner chooses where it resolves. Two gates leaned on this one function, so they agreed on the same wrong answer. Now the address is parsed |
| The deadline covered only the body | `http.client` reads the status line and each header separately, so a provider dribbling its header held a request open indefinitely while every receive stayed inside its socket timeout. Now every read of the response runs under one clock |
| The pinned fallback chain could re-admit a filtered model | A constant recorded in September would have overridden today's catalogue saying a model had become gated or been relicensed |
| An enumerative egress gate cannot see an SDK it does not know | Demonstrated by adding a module importing `litellm`, then `together`, then `replicate`. Replaced by a structural rule: every import must resolve to the standard library, `oak`, or a declared dependency |
| Model output could crash interpretation | An out-of-range confidence, a deeply nested value, or an unbounded claim path each escaped the bounds as `OverflowError` or `RecursionError`, neither of which is a `ValueError` |
| A provider's error `type` could end with a newline and reach the message | `$` matches before a trailing newline; `fullmatch` does not |

Six findings were refuted, each after the skeptics reproduced the mechanism and then showed
the consequence did not follow — for example, the provider key can reach an exception
`__cause__`, but nothing OAK emits renders a chain, and the input that would put it there is
already refused. Those are recorded here rather than acted on.

### Closing audit (`OAK-S9-009`)

Run against the complete branch, six lenses — credential leakage, egress, the confirmation
invariant, determinism, interface parity, documentation honesty — with two independent
verifiers per finding, one instructed to refute and one to judge consequence, both told to
settle it by running code. 20 findings, 11 confirmed, 9 refuted. Every confirmed finding is
fixed with a regression test.

The three that mattered were all in the same place: the merge seam's idea of "the brief
states this".

| Finding | Why it mattered |
|---|---|
| A model overwrote an explicit brief value whenever that value was an empty array or object | Provenance is recorded per scalar leaf, so `affected_non_users: []` — a declaration that nobody outside the user base is affected, in the repository's own reference brief — produced no record, and a check that consulted provenance alone read it as unstated. The reviewer was never told the model had contradicted them |
| Rejecting a section-level question erased the brief's own values in that section | And on the deterministic path too, where no model had run: rejecting the hardware question deleted the measured capacity the brief stated. `reject` means "the claims you showed me are wrong", so only what OAK proposed is removed now |
| A model proposing a value deleted the named critical question about it | `question.production-use` vanished when a model guessed at the production-data boundary, leaving only the broader section question. A model guessing is a reason to ask, not a reason to stop asking; the named questions are unconditional again and the section question is additional |
| The declared-dependency egress gate was far weaker than intended | Its hand-rolled parser ran past the end of the dependency list, swallowing the console scripts and the whole dev group — so `httpx` and `pytest` would have passed — while missing `keyring`. It parses the manifest properly now, and reads only what the shipped package declares |
| The live suite could never run | The autouse isolation fixture pointed the credential directory at a temporary path, so every live test skipped even with `OAK_LIVE_MODEL_TESTS=1` and real keys. The same fixture also did not isolate the OS keychain at all, so on a developer's machine a test could have written into their real login keychain |
| `auto` stopped being backwards-compatible | Once a model was selected, a REST client that had never heard of the capability token began getting 403 on a call that had always worked. With no token, `auto` means what it always meant |

The nine refuted findings were each reproduced and then shown not to follow — for example a
provider key can reach an exception `__cause__`, but nothing OAK emits renders a chain and
the input that would put it there is refused upstream.

### Documentation sweep (`OAK-S9-009`)

Six readers over both repositories — implementation top-level and operator docs, security
and release records, the manual, contracts and generated artefacts, the governance root, the
governance `docs/` tree — each asked for statements the branch had made false, misleading or
incomplete, with an independent check of every finding against the code. 45 raised, 23
verified stale and fixed; the rest were deliberately historical (a signed release record, a
completed plan) or already qualified by their surrounding text.

The sweep was worth running for one class of finding in particular: sentences that were
true before this branch and quietly stopped being true, in documents the branch never
touched. The implementation `README.md` is the clearest case — it is the project's front
door, it was absent from the whole branch diff, and it both omitted the feature and carried a
sentence a reader would fairly take as "OAK holds no provider credential". The same pattern
produced the `models`-is-local-only line in the interface contract, the "never in a request
body" clause of a requirement this sprint itself wrote, and the manual's `≤ 5 questions` box.

## Discoveries and follow-ups

- The `interpretation-proposal` schema had no `version`; both persistence adapters require one
  for the artifact identity check, so the field is added as optional.
- MCP sampling, `OAK_MODEL_PROXY`, a per-tenant token budget and a durable interpret Operation
  are recorded as follow-ups in the approved plan.
