<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S10-001–008: Hugging Face only — Deterministic, Online AI, Local AI — with a corroborated token

**Approved by the owner on 2026-09-21** (revision 2, including OPEN A — the three modes — and
OPEN B — the masthead label kept and repurposed). Execution on branch `hf-only-modes`.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-09-21
- Last updated: 2026-09-21 (Milestone 0)
- State: in-progress
- Claimed tasks: `OAK-S10-001`–`OAK-S10-008`

## Owner's answers, and what they settle

| # | Answer (2026-09-21) | Effect on this plan |
|---|---|---|
| 1 | Keep `local` | `local` stays as the third mode, **Local AI**. Nothing about it is deleted. |
| 2 | "Free should have meant free. If not possible via Hugging Face, is there a way online?" | Answered in the next section with evidence. Short form: no reputable anonymous free inference exists; every free tier needs an account, and Hugging Face's is $0.10 a month with no free promotional route live today. |
| 3 | If no genuinely free open-model inference exists: remove Default, make Deterministic the default, the other mode is **Online AI** preferring the current top inference-provided model on Hugging Face, the last is **Local AI** | **Adopted** (OPEN A below asks you to confirm the reading). Modes are `deterministic` (default), `online`, `local`. |
| 4 | Yes | Verification runs after `set-key`, on demand, and again when older than a day. |
| 5 | Yes | Both: a stale catalogue is refreshed just before an online interpretation, **and** there is an explicit Refresh (`oak models discover`, the Settings button). |
| 6 | No — add a manual pick; the mode chooses a preferred model but the user chooses among model × provider pairs | The Sprint 9 selection stays, per family: Online AI uses the user's pinned `model × provider` pair if one exists, else the preferred (trending-top) pair; Local AI uses the user's pinned local model. Settings lists the pairs with licence, price, throughput and structured-output support. |
| 7 | "What is a masthead chip?" | Explained under OPEN B. |
| 8 | Yes | Schema version stays `0.1.0`; `RR-042` added (count 42); `0.8.0` is the release version. |

## Is there genuinely free open-model inference online? (evidence, 2026-09-21)

"Free" here means: an open-weight model, permissively licensed, on a route that supports
structured output, at no cost to the user. Two flavours matter: free **without any account**,
and free **with a free account but no payment**.

| Option | Needs an account? | Needs a card? | What is free | Structured output | Verdict for OAK |
|---|---|---|---|---|---|
| **Hugging Face Inference Providers** (what OAK already uses) | yes — "You'll need a Hugging Face token to authenticate your requests" | no — "Free Users: $0.10, subject to change … Extra usage: yes (credits purchase required)" | $0.10 of routed usage a month, applied automatically; routes flagged `is_free` cost nothing while a provider runs a promotion. **Live read today: 137 models, 88 with a live structured-output route, 0 routes flagged `is_free`.** | per route, from the catalogue | Free in practice for light use (roughly 30–100 interpretations a month at today's prices), not free by design, and the amount is "subject to change". |
| **Groq** free tier | yes | not stated on the rate-limit page | `openai/gpt-oss-120b` and `-20b`: 30 requests/min, 1,000/day, 8K tokens/min, 200K tokens/day | strict `json_schema` on gpt-oss and `qwen/qwen3.8-27b` | A real free tier, but a second provider family (the owner ruled those out) and its data-use terms are in a DPA the privacy page does not reproduce. Reachable through Hugging Face only on Hugging Face's billing, unless the user adds a Groq key in their Hugging Face settings ("Custom Provider Key … billed directly by the provider"). |
| **Cerebras** free trial | yes | **yes** — "API access remain[s] inactive until you do [add a payment method]" | $5 credit; 1M tokens/day | strict `json_schema` | Not free without a card. |
| **OpenRouter** `:free` models | yes (API key) | no | 20 requests/min, **50/day** without purchased credits | some models | An aggregator like Hugging Face, with a data-training routing setting the user must manage; 50/day. Not adopted. |
| **Mistral** | — | — | the current API pricing page lists Standard, Batch and Priority only; the old free-tier page returns 404 | — | No documented free tier today. |
| **GitHub Models** | — | — | "fully retired" as of 2026-07-30 | — | Gone. |
| **Anonymous services** (the only one found with a documented no-key tier: Pollinations) | no | no | one request every 15 seconds | no JSON mode documented; model licences and data terms undocumented | Not a foundation for a governance tool. |

**Conclusion.** There is no reputable way to call an open model online with no account and no
key. With a free account and no card, Hugging Face gives a small monthly credit and Groq a
usable free tier; neither is "free by design", and Hugging Face's promotional free routes are
zero today. That satisfies the owner's condition in answer 3: **Default is removed and
Deterministic is the default.** Online AI still costs nothing for light use on a free
Hugging Face account because the monthly credit "automatically appl[ies] when you route
requests through Hugging Face" — the surfaces say exactly that, and never promise more.

A documentation-only follow-up, not part of this sprint: a user who wants more free usage can
add a Groq key under Hugging Face → Inference Providers settings; OAK's requests then route
through Hugging Face unchanged and are billed by Groq's free tier. OAK's code does not change.

## Outcome

A user has three ways to have a brief read, chosen per request from one dropdown in the
workspace, `--interpreter` on the CLI, the `interpreter` query on REST and the optional MCP
argument:

| Mode | What it does | What it needs | What it costs |
|---|---|---|---|
| **Deterministic** (default) | Today's offline interpreter. Nothing leaves the machine. Byte-identical to `0.7.1`. | nothing | nothing |
| **Online AI** | Sends the brief to one open model on Hugging Face Inference Providers: the user's pinned model × provider pair, or else the **preferred** pair — the current top model in the Hub's trending order that is ungated and has a live structured-output route, on the route the user's provider policy chooses. | a Hugging Face token, stored once and **corroborated with Hugging Face first**: accepted or not, its role, whether the account can pay, and the models it can call | the provider's published price, shown next to the pair; the account's free monthly credit applies first; OAK never buys credit |
| **Local AI** | Sends the brief to an OpenAI-compatible server on this machine (Ollama, vLLM, llama.cpp) at a loopback address, using the model the user picked. | `OAK_MODEL_ENDPOINT_LOCAL` (default `http://127.0.0.1:11434/v1`) and a picked model | nothing; nothing leaves the machine |

Today's live catalogue makes the preferred pair concrete: the Hub's trending list starts with
`Qwen/Qwen3.8-27B` (Apache-2.0, ungated) with three live structured-output routes — Cerebras
($1.49/M output, ~846 tokens/s), OVHcloud ($3.19/M, ~71 tokens/s), DeepInfra ($2.50/M,
~40 tokens/s) — so `cheapest` picks Cerebras today and `fastest` also Cerebras. Second is
`zai-org/GLM-5.3-Flash` (MIT, $0.50/M on Baseten or DeepInfra). Every figure above will differ
tomorrow, which is why the catalogue is read live and the pick shows when it was resolved.

Demonstration (CLI):

```bash
oak models set-key --stdin < hf-token.txt
#   Stored the huggingface key in the keychain backend (fingerprint …, 37 characters).
#   Verifying with Hugging Face (one request to huggingface.co; nothing is generated)…
#   accepted at 2026-09-21T10:02:11Z — read token; account can pay: no.
oak models discover
#   preferred: Qwen/Qwen3.8-27B via cerebras (apache-2.0, $1.49/M output, structured output)
#   88 models this token can call on a structured-output route; 4 gated models excluded
#   catalogue read 2026-09-21T10:02:15Z
oak models select Qwen/Qwen3.5-9B --provider deepinfra        # optional manual pair
oak models select local qwen3:8b                              # the Local AI model
oak models status                                             # verdict with age; picks; pairs
oak design brief.md --interpreter online
oak design brief.md --interpreter local
oak design brief.yaml                                         # deterministic; digests unchanged
```

and, in the browser: Settings → Models (token → key → verdict badge with time → Refresh →
preferred pair → table of pairs with "Use this pair" → Local AI endpoint and model), then Cases
→ "Describe what you want to build" → dropdown *Deterministic / Online AI / Local AI* →
Interpret → confirm with provenance badges.

## What Hugging Face actually offers (primary sources, read 2026-09-21)

| Fact | Source |
|---|---|
| "You'll need a Hugging Face token to authenticate your requests." A fine-grained token with "Make calls to Inference Providers", or a `read` token ("e.g. … doing inference"). | https://huggingface.co/docs/inference-providers/index; https://huggingface.co/docs/hub/security-tokens |
| Monthly credits: free $0.10 "subject to change"; PRO $2.00; Team/Enterprise $2.00 per seat; "credits automatically apply when you route requests through Hugging Face"; extra usage needs a credit purchase; no markup. | https://huggingface.co/docs/inference-providers/pricing |
| `GET https://router.huggingface.co/v1/models` is anonymous and returns, per provider route: `status`, `pricing.input/output`, `is_free`, `supports_structured_output`, `supports_tools`, `context_length`, `first_token_latency_ms`, `throughput`, `is_model_author`. Confirmed by a live read today (137 models). | https://huggingface.co/docs/inference-providers/hub-api |
| `GET /api/models?inference_provider=all&filter=conversational&sort=trendingScore…` lists served models in trending order; OAK already reads it. Confirmed live today (100 entries with `cardData.license` and `gated`). | same page; https://huggingface.co/docs/hub/api |
| `model:provider` pins a provider; `:fastest`/`:cheapest`/`:preferred` are server-side policies. OAK keeps pinning an explicit route because only some routes support structured output. | https://huggingface.co/docs/inference-providers/index |
| `GET https://huggingface.co/api/whoami-v2` with a bearer token: "Get information about the user and auth method used"; Hugging Face's own client typings show `type`, `name`, `isPro`, `canPay`, `billingMode`, `periodEnd`, `orgs[]`, `auth.accessToken.{displayName, role, createdAt}`; non-2xx is an error. Costs nothing, generates nothing. | https://huggingface.co/.well-known/openapi.md; https://raw.githubusercontent.com/huggingface/huggingface.js/main/packages/hub/src/lib/who-am-i.ts |
| The fine-grained inference permission identifier is `inference.serverless.write` (in-tree in the token link). Whether `whoami-v2` echoes fine-grained scopes is undocumented → settled by the live run; reported `unknown` until then. | `src/oak/domain/model_families.py:60` |
| Hub API rate limits: 1,000 requests / 5 min for a free user; 429 carries `RateLimit` headers. | https://huggingface.co/docs/hub/rate-limits |
| Hugging Face's MCP server (https://huggingface.co/mcp) serves coding assistants over HTTP with Hub search, Jobs, Sandboxes and Spaces tools. | https://huggingface.co/docs/hub/en/hf-mcp-server |

**On the MCP or "skill" suggestion.** OAK should not add an MCP client. The MCP server exposes
the same Hub data OAK already reads anonymously through its one audited transport; an MCP
client would be a second network client (the egress gate forbids it) and a new runtime
dependency (the declared-dependency gate forbids it); a "skill" is a coding-agent artefact.
The live source the owner wants is the router catalogue plus the Hub trending listing, read
on Refresh and, when stale, just before an online interpretation. It tells OAK the current top
model *and* exactly how to call it: `model:provider`, structured-output support, price.

## Context and invariants

`main` is `3430c71`; `0.7.1` (published 2026-09-03) predates every model-provider surface, so
`oak models`, `/v1/models*`, `--interpreter`, the MCP `interpreter` argument and
`model-configuration.schema.json` are **unpublished** and may change shape without a
deprecation window (`docs/compatibility.md`, publication-boundary reading). The OpenAPI
compatibility baseline contains no `/v1/models` path (verified), so removals there pass the
gate. What must not change: the deterministic path (`tests/integration/test_reference_digests.py`),
the `0.7.1` REST contract, and every Sprint 9 invariant in
`docs/exec-plans/completed/OAK-S9-001-009-model-provider-intake.md`.

Local terms: a **mode** is `deterministic`, `online` or `local`. A **pair** is a model and a
provider route on Hugging Face. The **preferred pair** is the one discovery resolves from the
trending order; a **pinned pair** is one the user selected. A **verdict** is what the Hub said
about the stored token, with the time it said it.

Governing requirements and ADRs are unchanged: `OAK-FR-INT-009`, `OAK-NFR-SEC-007`, ADR-0009,
ADR-0016, implementation ADR-0003, `TM-13`, `TM-20`, `RR-039`–`RR-041`. Recipes: Model provider
integration, Contract change, Interface adapter, Workspace UI, Security review, Documentation
and ADR.

## Scope

### In

- **`OAK-S10-001` — Branch, plan, governance.** Branch `hf-only-modes` from `origin/main`;
  this plan under `docs/exec-plans/active/`; Sprint 10 rewritten in the governance
  `sprints.md`; `STATUS.md` claims (both repositories); the digest test and `make check`
  green before anything moves.
- **`OAK-S10-002` — Remove the five hosted families.** `openai`, `anthropic`, `gemini`, `meta`,
  `xai` rows in `model_families.py` and `providers.py`; the dead request shape
  (`anthropic_messages`), header kinds (`x-api-key`, `x-goog-api-key`), pagination and
  chat-candidate branches only they used; their fixtures; the five `OAK_MODEL_KEY_*` literals
  and `docs/configuration.md` rows; the schema enum members; the `conftest.py` loop entries;
  every test naming them (retargeted to `huggingface` where the behaviour is generic, deleted
  where it was that family's). `tools/check_repository.py` keeps every key-shape pattern.
  `data_use_acknowledged` and the `OAK-MODEL-DATA-USE` check go too: no remaining family
  reports `trains_on_inputs` (Hugging Face reports `unknown` and shows the routed provider).
- **`OAK-S10-003` — Three modes.** `INTERPRETER_MODES = ("deterministic", "online", "local")`;
  `auto` and `model` are gone; an absent `interpreter` means `deterministic` everywhere.
  `create_model_interpreter(mode)` builds the adapter from the mode's family and its pinned or
  preferred pair. Discovery stores the preferred pair (with the time and the reason) and
  every callable pair's licence, price, throughput and structured-output flag. `oak models
  select [huggingface] <model_id> [--provider <route>]`, `oak models select local <model_id>`,
  `oak models clear [family]`; REST `PUT/DELETE /v1/models/selection` keep their shape with
  `provider_route` now meaningful for Hugging Face; the MCP argument's closed enum becomes the
  three words with `deterministic` as default. The audit extension records the mode.
- **`OAK-S10-004` — Corroborate the token.** `key_verification_request()` (unused since
  Sprint 9) becomes the `whoami-v2` request for Hugging Face and the models list for `local`;
  `parse_whoami()` yields a verdict and discards the body (it carries an email address OAK
  must never store). `ModelConfigurationService.verify()` persists `{verdict, checked_at,
  method, token_role, inference_permission, can_pay, is_pro}` — no key material, no name, no
  email. `set-key` verifies by default and says so (`--no-verify` skips); `oak models verify`;
  REST `POST /v1/models/{family}:verify` (token-gated, `no-store`); the status document carries
  the verdict, its age and `stale: true` past `OAK_MODEL_VERIFICATION_STALE_SECONDS` (86400).
  Before an `online` interpretation OAK re-verifies a missing or stale verdict and refreshes a
  missing or stale snapshot, each under its own budget, and refuses before spending if the
  token is rejected; a 401 during an interpretation also records `rejected`.
- **`OAK-S10-005` — Workspace.** One dropdown on the "Describe what you want to build" form
  (carried to the case page's Interpret action, shown there again so a re-interpret can change
  mode), each option stating what it needs and costs, with the live verdict and pair beside
  Online AI and the endpoint and model beside Local AI. Settings → Models: token; key with
  verdict badge, time and Verify; Refresh; the preferred pair; a table of callable pairs
  (model, provider, licence, output price, throughput, structured output) with "Use this
  pair"; "Use the preferred pair"; the Local AI endpoint (read-only, from the environment)
  and model pick. Masthead chip per OPEN B. Browser tests updated; `11-models` and the PDF
  regenerated.
- **`OAK-S10-006` — Documentation, ADRs, governance.** Every document naming seven families,
  `auto`, `model`, "Detection asks the provider", or the free default is corrected (list in
  Milestone 5). `RR-039` narrowed to Hugging Face and the provider it routes to; new `RR-042`
  (a verdict is a claim about the past); `TM-13`/`TM-20` wording; ADR-0003 addendum;
  ADR-0009/0016 consequence sentences (governance, then re-mirrored); `evidence/sources.yaml`
  gains the Hugging Face sources and the free-tier survey above and retires the five-vendor
  entry; error reference, OpenAPI and web client regenerated; `SPRINT-10-PROMPT.md` marked
  superseded.
- **`OAK-S10-007` — Live run, adversarial audit, sweep, PR.** A recorded live run with the
  owner's token(s); refute-by-default reviewers over the verdict path, pre-flight budgets, mode
  parity across CLI/REST/MCP/web, pinned-pair honesty and documentation honesty; fixes with
  pinning tests; a grep sweep of both repositories; PR with remote CI green; merge.
- **`OAK-S10-008` — Release `0.8.0`** (post-merge, owner-gated).

### Out

- Any hosted provider other than Hugging Face. No "bring your own base URL" family.
- An MCP client or any second network client; any runtime dependency.
- A spend budget (`RR-041` stands; the Hugging Face credit is the budget).
- Changing the merge seam, the confirmation invariant, the transport, the credential stores,
  the loopback guard, the capability token or the egress gates.
- Publication — the owner's separate decisions.

## Contract and data changes

- `schemas/model-configuration.schema.json` (unpublished; `schema_version` stays `0.1.0`):
  `$defs.family` enum → `["huggingface", "local"]`; `selection` becomes a map keyed by family,
  each `{model_id, provider_route, selected_at}` (`default_interpreter` and
  `data_use_acknowledged` removed); `discovery.<family>` gains optional `preferred`
  `{model_id, provider_route, licence, output_price_per_million, resolved_at, reason}`;
  `providers[]` items gain optional `is_free` and `throughput`; new optional top-level
  `verification` map keyed by family. A `main`-era document still loads (a single `selection`
  object is up-converted into the map on load); a branch-era document does not load on `main`
  — stated in `docs/compatibility.md`; harmless because nothing published carries the schema.
  `examples/example-model-configuration.yaml` rewritten.
- REST (unpublished): `interpreter` enum `deterministic|online|local`, omitted =
  `deterministic` (what `0.7.1` clients get; the compatibility test is kept and simplified);
  `X-OAK-Model-Token` required for `online` and `local` (unchanged rule: today `local` also
  needed it). New `POST /v1/models/{family}:verify`. `GET /v1/models` gains `verification`,
  `preferred` and `pairs`. `make openapi-compatibility` stays clean.
- CLI (unpublished): `oak design --interpreter deterministic|online|local`, default
  `deterministic`; `oak models status|set-key [family] [--no-verify]|remove-key [family]|
  verify [family]|discover [family]|select [family] <model_id> [--provider]|clear [family]|
  token`; the family defaults to `huggingface`; `families` removed.
- MCP: `interpreter` enum `deterministic|online|local`, default `deterministic`, description
  states what each spends and sends. No configuration tool, as before.
- Audit: `brief_interpreted` extension gains `mode`; deterministic path unchanged.
- `OAK_MODEL_VERIFICATION_STALE_SECONDS` (default `86400`) added; five `OAK_MODEL_KEY_*` rows
  removed; `OAK_MODEL_ENDPOINT_LOCAL` unchanged. No new `OAK-*` code expected; the error
  reference is regenerated for changed messages.
- Residual-risk register: `RR-039` reworded, `RR-042` added; count 41 → 42 in the quoted
  places the count gate checks (the `b954830` precedent).

## Milestones

### Milestone 0 — Branch, plan, governance (`OAK-S10-001`)

- Work: branch `hf-only-modes` from `origin/main`; this plan
  (`docs/exec-plans/active/OAK-S10-001-008-huggingface-only-modes.md`); governance
  `sprints.md` Sprint 10, `STATUS.md` (both), `spec-manifest.yaml`, root `CHANGELOG.md`.
- Proof: `make check` with zero `make: ***` lines (`OAK_TEST_DATABASE_URL` set); governance
  `make validate`; the digest test passes.
- Rollback: delete the branch; restore the governance files from the scratchpad copies.

### Milestone 1 — Remove the five hosted families (`OAK-S10-002`)

- Work: `model_families.py` (two descriptors; one environment literal); `providers.py`
  (`RequestShape`/`KeyHeader` one member each; `_HOSTED_PROFILES` one entry; dead branches in
  `auth_headers`, `models_request`, `parse_models`, `descriptor_from`, `_is_chat_candidate`,
  `extract_text`, `chat_request` deleted — nothing refactored); `data_use_acknowledged`
  removed end to end; schema enum; `conftest.py`; `docs/configuration.md`; fixtures deleted,
  the OpenAI-shaped `completion.json`, `refusal.json`, `truncated.json` moved under
  `huggingface/`; tests retargeted (`test_provider_profiles.py`, `test_model_configuration.py`,
  `test_credential_store.py`, `test_hosted_interpreter.py`, `test_models_api.py`,
  `test_models_cli.py`, `web/e2e/models.spec.ts`); the live suite follows `FAMILY_IDS`.
- Proof: `make check` green; `oak models status --output json` shows only `huggingface` and
  `local`; egress suite green with `DOCUMENTED_MODEL_ADAPTERS` unchanged; digests unchanged.
- Rollback: revert the commit.

### Milestone 2 — Three modes, preferred and pinned pairs (`OAK-S10-003`)

- Work: `design_case.py` (`INTERPRETER_MODES`; `resolve_interpreter` without `auto`;
  `interpret(interpreter=mode)`; `request["interpreter"] = mode`; extension `mode`);
  `control_plane.py`; `bootstrap.create_model_interpreter(mode)` (family from mode; pinned
  pair else preferred; `local` requires a pinned model and refuses with the list otherwise);
  `huggingface_catalogue.py` gains `preferred_pair(snapshot, policy)` — ungated, trusted
  namespace (list refreshed against today's trending page, `as_of` recorded), at least one
  live structured-output route, ranked by the Hub's trending order, route by `provider_policy`
  (`cheapest` = lowest output price, `fastest` = highest `throughput`, both among
  structured-output routes only); `providers.py` `_huggingface_routes` reads `is_free` and
  `throughput`; `PINNED_MODELS` refreshed from today's router with `PINNED_AS_OF =
  "2026-09-21"`; `ModelConfigurationService` selection map with up-conversion,
  `select(family, model_id, provider_route)`, `clear(family)`, `preferred(family)`,
  `pairs(family)`; schema and example; CLI `InterpreterChoice`, `models` actions, status and
  discovery text; REST `InterpreterMode`, routes, models; remote CLI; MCP `_INTERPRETER`;
  OpenAPI and client regenerated; tests: `test_proposal_merge`/golden intents untouched;
  `test_model_interpretation_service` and `test_model_interface_conformance` driven with
  `online` and `local` through the fake adapter (file, REST and MCP legs agree; MCP refuses
  `auto` and `model`); catalogue tests for the preferred pair, `cheapest`/`fastest`, gated and
  non-structured exclusion, pinned fallback; a pinned pair whose route has no structured
  output is refused at `select` with the reason.
- Proof: `oak design brief.md --interpreter online` with no key refuses with
  `OAK-MODEL-KEY-MISSING`; with the fake adapter both modes produce `model_proposed` claims
  and per-section questions; `oak design brief.yaml` and `oak design brief.md` (no flag) are
  byte-identical to `0.7.1`; `make openapi-compatibility` clean.
- Rollback: revert the commit.

### Milestone 3 — Corroborate the token (`OAK-S10-004`)

- Work: `providers.py` `key_verification_request()` builds `GET
  https://huggingface.co/api/whoami-v2` for `huggingface` (host already allowlisted) and the
  models list for `local`; `parse_whoami(response)` → `Verdict(verdict, token_role,
  inference_permission, can_pay, is_pro)`: 200 → `accepted` (`inference_permission` true for
  `read`/`write`, from fine-grained scopes when present, else `null`; `can_pay`/`is_pro`
  booleans or `null`), 401 → `rejected`, 403 → `scope_limited`, 429/5xx/deadline →
  `unreachable`; everything else discarded, with a test that the stored verdict never
  contains the response's `name` or `email`. `verify()` via an injected `verifier`,
  `record_verdict()`, `verification_status()` with staleness; `status()` carries it. CLI
  `set-key` (verify by default, `--no-verify`), `verify`; REST `:verify`; the route-enumeration
  tests extended. Pre-flight in `create_model_interpreter("online")`: stale verdict → verify
  (5 s); stale snapshot → discover (15 s); the interpretation keeps its own budget; when
  `OAK_MODEL_TIMEOUT_SECONDS` leaves under 20 s of headroom below the 55 s ceiling the
  pre-flight is skipped, the stored state is used, and a note says so. A `rejected` verdict
  refuses with `OAK-MODEL-KEY-REJECTED` before any chat request; the adapter's own 401 records
  `rejected` through a thin wrapper in bootstrap. `OAK_MODEL_VERIFICATION_STALE_SECONDS`
  documented.
- Proof: recorded fixtures `tests/fixtures/providers/huggingface/whoami-v2*.json` (read token,
  fine-grained, 401, 403, hostile) drive unit tests; API tests for `:verify` (token required,
  `no-store`, verdict in status, no key in any body); CLI test that `set-key --stdin` prints
  the verification sentence and `--no-verify` sends nothing (fake transport counts requests);
  service test that a stale verdict triggers exactly one whoami request before the chat
  request and a `rejected` one triggers none; `git grep` of every model-state file for the
  fixture's email finds nothing.
- Rollback: revert the commit; the verification block is optional in the schema.

### Milestone 4 — Workspace (`OAK-S10-005`)

- Work: `CaseListPage.tsx` dropdown — *Deterministic — nothing leaves this machine* /
  *Online AI — Qwen/Qwen3.8-27B via cerebras, $1.49/M output; your free monthly credit applies
  first; token verified 2 h ago* / *Local AI — qwen3:8b on 127.0.0.1:11434* — preselecting
  `deterministic`; the choice is kept in `sessionStorage` for the new case and read by
  `CasePage.tsx`, whose Interpret action shows the same dropdown; choosing Online AI with a
  stale or missing snapshot calls `:discover` and with a stale verdict calls `:verify` so the
  text is current before Interpret; `SettingsPage.tsx` as in scope; `main.tsx` per OPEN B;
  `problems.tsx` recovery copy kept; generated client regenerated; `web/e2e/models.spec.ts`
  rewritten (store → verdict badge → refresh → pin a pair → dropdown shows it → no response
  body carries the key); `manual-screens.spec.ts` recaptures `11-models`; PDF rebuilt.
- Proof: `make web-build`, typecheck, format; `make web-e2e` under Compose; axe pass on
  Settings and the case list.
- Rollback: revert the commit.

### Milestone 5 — Documentation, ADRs, governance (`OAK-S10-006`)

- Work (implementation): `README.md:9`, `CHANGELOG.md` (Sprint 10 section under Unreleased;
  Sprint 9 entries kept as history with a lead sentence), `docs/configuration.md`,
  `docs/operations.md:351-375`, `docs/interfaces.md:125-148`, `docs/compatibility.md:109` and
  the schema bullet, `docs/local-design-case.md:17`, `docs/dependencies.md:136`,
  `docs/manual/manual.html` chapter 4, `docs/adr/0003-…md` addendum,
  `docs/adr/architecture/0009` and `0016` re-mirrored, `docs/security/residual-risk.md`
  (`RR-039`, `RR-042`), `docs/security/threat-coverage.md`, `docs/error-codes.md`, `STATUS.md`.
  Governance: `docs/threat-model.md` (`TM-13`, `TM-20`), `docs/adr/0009`, `docs/adr/0016`,
  `sprints.md`, `STATUS.md`, `CHANGELOG.md`, `spec-manifest.yaml`, `evidence/sources.yaml`,
  `SPRINT-10-PROMPT.md` marked superseded.
- Proof: ADR-reference, assurance-claim, configuration-reference, error-reference and
  register-count contract tests green; governance `make validate`.
- Rollback: revert.

### Milestone 6 — Live run, audit, sweep, PR (`OAK-S10-007`)

- Work: `OAK_LIVE_MODEL_TESTS=1 uv run pytest tests/live -v` with the owner's read token and,
  if available, a fine-grained token with and without the inference permission — settling the
  two undocumented points — plus one `online` interpretation on the owner's credit with their
  explicit go-ahead, and one `local` interpretation if a local server is running; recorded
  here. Independent refute-by-default reviewers: credential and email leakage on the verify
  path; verdict honesty (can any path show `accepted` without a 200 from the Hub?); pre-flight
  budgets against the nginx limit; mode parity across CLI, REST, MCP and web; a pinned pair
  that lost its structured-output route; documentation honesty. Fixes with pinning tests.
  Sweep: `git grep` both repositories for `seven`, `auto`, `"model"`, `families`, `free`,
  `OpenAI`, `Anthropic`, `Gemini`, `xAI`, `Meta Model`, `Detection asks the provider`,
  `nothing calls`, `proves only`. PR; CI green; merge.
- Proof: `git status --porcelain -uall` clean before every commit; zero `make: ***` lines
  with and without `OAK_TEST_DATABASE_URL`; digests unchanged.

### Milestone 7 — Release `0.8.0` (`OAK-S10-008`, post-merge, owner-gated)

- Work: version touch-list (`VERSION`, `pyproject.toml`, `STATUS.md`, `package.json`,
  `web/package.json`, regenerated `openapi/oak.openapi.json`, the manual's "must report"
  line, `CHANGELOG.md` heading); `docs/release/0.8.0/release-decision.md` in the `0.7.1`
  shape, not inheriting its signatures, honest about one person holding three roles; evidence
  refresh (`make check`, `make audit`, `make sbom`, `make scan-images` from a clean tree —
  never commit `source_tree_dirty: true`); tag; stop.
- Proof: `make release` builds twice with equal digests; `release.yml` on the tag is green and
  publishes nothing.

## Verification

- Unit: whoami parsing (every status, hostile body, missing fields, email never retained);
  verdict staleness (future/unparsable timestamps read as stale); preferred pair
  (trending order; gated and non-structured excluded; `cheapest`/`fastest`; pinned fallback
  says `pinned`); selection up-conversion; a pinned pair validated against the snapshot;
  profile table with two families; transport suite re-run unchanged.
- Contract: schema conformance for the new example; configuration reference; error
  reference; MCP contract; OpenAPI equality and compatibility; ADR references; assurance
  claims; register count; secret shapes unchanged.
- Integration: reference digests (unchanged — stop if not); offline boundary (unchanged
  gates); interpretation service and interface conformance under `online` and `local`;
  models API including `:verify`; models CLI; loopback hardening (`:verify` on the model-route
  predicate); remote CLI refusal of `models`.
- End to end: CLI journey with a fixture token and the fake transport; Playwright settings,
  dropdown and journey; manual capture.
- Security: the key and the whoami response's `name`/`email` absent from every response,
  document, store, log and problem; egress under broken sockets; the pre-flight never runs on
  the deterministic path (the fresh-interpreter test extended).
- Failure and retry: token rejected (before spend); Hub unreachable (verdict `unreachable`,
  interpretation refused with the existing retriable code); credit exhausted
  (`OAK-MODEL-QUOTA-EXHAUSTED` names the pricing page); gated pair impossible by construction;
  pinned pair whose route died (404/`error` → refused with "refresh and pick again"); local
  server down (`OAK-INTERPRETER-UNAVAILABLE`); snapshot and verdict stale.

## Security, privacy and authority review

Input trust: unchanged for the brief and the proposal. New untrusted input: the `whoami-v2`
body (parsed into five typed fields) and the router's `is_free`/`throughput` (boolean; finite
non-negative number). Sensitive data: the token travels only in the `Authorization` header to
`huggingface.co` and `router.huggingface.co`; the verdict stores no key material and no
account identity; the email is dropped at parse time and a test proves it. Identity and
tenant: unchanged; `:verify` sits behind the loopback guard and the capability token. Privileged
operations: none new. Failure state: a failed verification is a verdict, never an exception,
and never blocks `deterministic`; a rejected token blocks `online` before any request that
could spend. Audit: the `brief_interpreted` event records mode, model and route as before.

## Operational and rollback plan

No token means only `deterministic` and `local` work, exactly as today for `deterministic`.
A `main`-era configuration file loads (up-converted; new fields optional); a branch-era file
does not load on `main` (unpublished schema; stated). Compose: no change to volumes. Rollback
of any milestone is a revert. The pre-flight adds at most two bounded requests to
`huggingface.co` before an online interpretation and none to the other modes.

## Decisions

Settled by the owner on 2026-09-21: keep `local` (1); verification by default and daily (4);
pre-flight refresh **and** explicit refresh (5); a manual model × provider pick beside the
preferred one (6); schema `0.1.0`, `RR-042`, `0.8.0` (8); and A and B below.

**A — the three modes (approved 2026-09-21).** No genuinely free online inference exists, so
Default is removed; the modes are **Deterministic** (default), **Online AI** (Hugging Face;
preferred = current trending top with a structured-output route; pinned pair optional; token
corroborated first; the free monthly credit applies but is not promised) and **Local AI**.

**B — the masthead label (approved 2026-09-21).** The label Sprint 9 put in the workspace's
header bar (`web/src/main.tsx`, `useInterpreterLabel`) is kept and repurposed: it shows the
Online AI pair that would be used and the token's verification age ("Online AI:
Qwen/Qwen3.8-27B via cerebras · token verified 2 h ago"), or "Online AI: no token", so a stale
or missing key is visible before anyone opens the dropdown.

## Progress

- [x] 2026-09-21 Plan revision 1 written and answered by the owner; revision 2 approved
  (three modes; masthead label kept, repurposed).
- [x] 2026-09-21 Milestone 0 (`5ef6136`): branch `hf-only-modes` from `origin/main`
  (`3430c71`); this plan; Sprint 10 registered in the governance `sprints.md`, `STATUS.md`,
  `spec-manifest.yaml` (`0.4.0-draft.5`) and `CHANGELOG.md`; tasks claimed in `STATUS.md`;
  governance `make validate` and the digest test green.
- [x] 2026-09-21 Milestone 1 (`44d4b2f`): the five hosted families removed with their request
  shape, header kinds, paginated parsers, chat-candidate branches, fixtures, environment
  literals, configuration rows, schema enum members and tests; the OpenAI-shaped completion
  fixtures moved under `huggingface/`; the secret scanner untouched; `make check` zero
  `make: ***` lines with PostgreSQL (627 unit/contract, 262 integration, 42 e2e).
- [x] 2026-09-21 Milestone 2: `deterministic`/`online`/`local` replace `auto`/`model` in the
  service, control plane, CLI (`--interpreter`, default deterministic), remote CLI, REST
  (`interpreter` query; absent = deterministic; token demanded for the two model modes), MCP
  (closed enum, default deterministic) and the generated client; the audit extension records
  the mode; one selection per family (`selection` map, up-converted from the Sprint 9 shape
  on load) with `provider_route` validated against the snapshot's structured-output routes;
  the catalogue ranks by the Hub's trending order and records the licence rather than
  filtering on it; routes carry `is_free` and `throughput`, and the provider policy uses
  them; `PINNED_MODELS` and `TRUSTED_NAMESPACES` refreshed with `as_of` 2026-09-21; the web
  pages compile against the new `modes`/`selections` shape (the dropdown is Milestone 4);
  `make openapi-compatibility` clean; `make check` zero `make: ***` lines with PostgreSQL
  (632 unit/contract, 264 integration, 42 e2e) (`feac93d`).
- [x] 2026-09-21 Milestone 3: the token is corroborated with the Hub's `whoami-v2`
  (`key_verification_request` finally has a caller); the answer is reduced to a verdict with
  the token's role, whether the account can pay and, when the Hub says, the Inference
  Providers permission, and the account's name and email are dropped at parse time (a test
  proves the stored document never carries the fixture's sentinel name or email); the verdict
  is stored with the time it was given, shown with its age by `oak models status` and
  `GET /v1/models`, stale after `OAK_MODEL_VERIFICATION_STALE_SECONDS` (a day), and forgotten
  when a key is stored or removed; `oak models set-key` verifies by default and prints what it
  does (`--no-verify` skips), `oak models verify` and `POST /v1/models/{family}:verify`
  re-check; a rejected verdict takes Online AI offline; before an online interpretation a
  stale verdict is re-checked (5 s) and a stale catalogue refreshed (15 s) when the
  interpretation budget leaves 20 s of headroom under the 55 s ceiling, and a rejected token
  is refused before any request that could spend; a token refused mid-interpretation is
  recorded as rejected; the test suite's wiring gets a verifier that answers `unverifiable`
  so no test can reach huggingface.co; `make check` zero `make: ***` lines with PostgreSQL
  (648 unit/contract, 272 integration, 42 e2e).

## Discoveries and follow-ups

- The 2026-09-18 multi-provider research is superseded and not carried forward.
- Two Hugging Face facts are undocumented and are settled by the live run: whether
  `whoami-v2` reports fine-grained scopes, and how it answers an inference-only token.
- Documentation follow-up (no code): more free usage is possible by adding a Groq key under
  Hugging Face → Inference Providers settings; requests still route through Hugging Face.
- `SPRINT-10-PROMPT.md` describes the superseded scope; mark it superseded in Milestone 5.
- The Hub trending list today includes gated Meta Llama models (`gated: "manual"`) and models
  with no structured-output route; both are excluded from the preferred pair by construction
  and the exclusion count is shown.
