<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S6-001–008: Policy and adapter SDK

## Status

- Owner/agent: Claude
- Started: 2026-08-19
- Last updated: 2026-08-19
- State: in progress
- Claimed tasks: `OAK-S6-001`–`OAK-S6-008`

## Outcome

A contributor can add a governed policy pack or a deterministic deployment backend without
modifying the compiler core or weakening any runner rule. Versioned SDK contracts exist for
the five extension classes (component manifests, architecture patterns, policy packs,
compiler renderers, runner adapters) with capability discovery. A policy port with a
deterministic built-in rule engine evaluates effective-dated, scoped, signed policy packs
into canonical decision documents; an optional OPA adapter behind the same port produces
byte-identical decisions and is never required. A second deployment renderer
(Helm/Kubernetes-shaped manifests) proves the same canonical plan contract behind a
renderer port without making Kubernetes mandatory. Extensions install into a quarantine
store and become usable only after digest, compatibility, licence, signature-against-pinned
anchor, and embedded-test verification plus an explicit local activation; a
poisoned/unsigned/incompatible extension stays quarantined with machine-readable reasons.
Swapping policy engines or deployment renderers changes target artifacts only — the
selected architecture's canonical intent, decision lineage, and byte-stable semantic
manifest are unchanged.

## Context and invariants

Sprint 5 is merged at `c5b2010` (PR #7); the repo is `0.5.0.dev5` and `make check` is
green. `src/oak/adapters/policies/` and `src/oak/adapters/deployment/` are Sprint 0
placeholders. There is no policy port; catalogue eligibility, hard constraints, and target
preflight are deterministic in-compiler code and stay that way. Runner adapter identity is
code in `oak.domain.runner_adapters` ("the allowlist is code, never plan data") and the
runner independently re-verifies identity, digest, parameter-schema digest, and kind
allowlists before target access.

Governing requirements: `OAK-FR-REG-001`–`007`, `OAK-FR-CAT-001`–`006`,
`OAK-FR-DEP-001`–`008` (esp. `OAK-FR-DEP-007`: two validated target adapters without
making Kubernetes mandatory), `OAK-FR-ARC-007`, `OAK-NFR-GOV-001`–`002`,
`OAK-NFR-PORT-002`. ADR-0003 (relational canonical records), ADR-0005 (compile through
target adapters; Kubernetes adapter second; do not require Kubernetes), ADR-0007
(nexus-first effective-dated policy packs), ADR-0011 (explicit openness classes), ADR-0015
(typed runner operations). Threat model TM-01, TM-02, TM-03 (malicious policy pack:
signed/effective-dated packs, fixtures, two-role activation, immutable lineage), TM-08,
TM-15, TM-17 (stale legal source becomes `review_required`, never silently compliant),
TM-18. skills.md recipes: Governed pack, Deployment adapter, Contract change, plus
Security review as the reviewing lens.

Hard invariants:

- No `command`, `shell`, `executable`, or `argv` field in any canonical document; the OPA
  adapter builds fixed allowlisted argv (`opa` only) with `shell=False`, a sanitized
  environment, and output/time bounds; renderers emit declarative files and execute
  nothing.
- `oak.runner` imports only `oak.contracts`, `oak.domain`, and itself; `oak.contracts` and
  `oak.domain` stay leaves; no new top-level package is added, so
  `tools/check_boundaries.py` continues to enforce the existing graph unchanged.
- Compiled canonical artifacts are immutable and byte-stable. Policy evaluation and
  rendering wrap existing artifacts in new ones; no existing compiled document, digest, or
  the `candidate-03` reference journey changes by one byte.
- Fail closed everywhere: unknown extension classes, engines, renderers, rule operators,
  schema versions, stale or not-yet-effective packs, and unverifiable signatures are
  refused with stable `OAKError` codes, never skipped.
- Signatures verify only against pinned local trust anchors (`initialize_trust_directory`
  roles); a key embedded in the document being checked is a claim, not an anchor. A pack
  or extension is never trusted because of where it came from.
- Extension payloads are data, never code. Deployment-adapter extensions bind
  configuration to in-tree renderer identities; there is no dynamic import, no downloaded
  code execution, and no plan-selected executable.
- The deterministic built-in fixture policy path works offline with no new mandatory
  dependency; OPA and Kubernetes remain optional.
- `.github/` stays unedited. No production/customer claim.

## Scope

### In

- **SDK contracts (`OAK-S6-001`)**: `oak.domain.extension_sdk` declaring `SDK_VERSION`,
  a versioned `ExtensionInterface` per extension class (component-manifest,
  architecture-pattern, policy-pack, compiler-renderer, runner-adapter) with schema
  bindings and capability vocabularies; renderer identities
  (`RENDERER_IDENTITY_BY_ID`) pinned as code like runner adapters; a deterministic
  capability-discovery document surfaced through `oak extensions capabilities`.
- **Policy port and lifecycle (`OAK-S6-004`)**: `oak.ports.policy` (`PolicyEnginePort`),
  new canonical schemas `policy-pack` (identity, semver, scope
  jurisdictions/domains, effective_from/expires_at, evidence source + version, owner,
  review status, embedded test fixtures, optional signature block) and `policy-decision`
  (pack/subject digest bound, outcome `allow|deny|review_required|unknown`, per-rule
  results with reasons and obligations, no engine identity in the canonical body — the
  engine is audit metadata, so identical inputs give byte-identical decisions across
  engines); a bounded declarative rule language evaluated in `oak.domain.policy_rules`
  (pure, fail-closed on unknown pointers/operators); a bundled deterministic fixture pack;
  `oak policy evaluate` committing `policy_pack` + `policy_decision` artifacts with a new
  `policy_evaluated` audit event; stale/not-yet-effective/expired packs refuse evaluation.
- **OPA adapter (`OAK-S6-005`)**: `oak.adapters.policies.opa` translating the pack's rule
  language deterministically to Rego, executing the local `opa` binary via fixed argv
  with `shell=False`, sanitized env, timeouts, bounded output; unavailable binary is an
  explicit stable error; engine selection is explicit (`--engine` / config), default
  builtin; decisions must be byte-identical to the built-in engine.
- **Second deployment adapter (`OAK-S6-006`)**: `oak.ports.rendering`
  (`DeploymentRendererPort`), `oak.adapters.deployment` with two renderers behind the
  same port — `renderer.local-manifests` (canonical JSON manifest set, the existing
  local/OCI-review shape) and `renderer.helm-kubernetes` (deterministic chart-shaped
  Kubernetes YAML: Namespace/Deployment/Service/NetworkPolicy from the semantic manifest
  and component lock, digest-pinned images, deny-all egress; nothing executes helm or
  kubectl). Recorded decision: Kubernetes render/plan chosen over OpenTofu per ADR-0005's
  "Kubernetes adapter second" and `OAK-FR-DEP-007`. New CLI `oak render` writes files
  read-only like `oak gitops`; the workspace is not mutated.
- **Extension supply chain (`OAK-S6-008`)**: `extension-manifest` schema (class, payload
  digest, compatibility ranges incl. SDK interface version, licence, owner,
  SBOM/provenance/signature status hooks mirroring the component-manifest vocabulary),
  `extension-activation` record schema; a local store (`~/.oak/extensions`, override
  `OAK_EXTENSIONS_DIRECTORY`) with `quarantine/` and explicit activation;
  `oak extensions install|verify|activate|deactivate|list|sign|capabilities`;
  a third signing role `extension-steward` added additively to the local trust
  directory; activation requires schema validity, payload digest match, compatibility,
  licence presence, steward signature against the pinned anchor, and the pack's embedded
  tests passing under the built-in engine; every failure leaves the extension quarantined
  with reasons; no dynamic code execution anywhere.
- **Scaffolding/docs (`OAK-S6-002`)**: `templates/extensions/` with a minimal schema-valid
  template per extension class plus README walkthroughs; `docs/extension-sdk.md`
  developer guide (interfaces, lifecycle, contract kit usage, replacement rules).
- **Contract test kit (`OAK-S6-003`)**: importable `tests/extension_kit/` with reusable
  checks — engine determinism and canonical-decision conformance, renderer determinism
  and path/content safety, error mapping to stable codes, licence/evidence field
  presence, parameter validation, argv-injection resistance corpus (shared with runner
  adapter tests), rollback behavior via the typed container adapter, and offline
  operation; used by our own suites and documented for contributors.
- **Replacement and exit demonstration (`OAK-S6-007`)**: integration/e2e proof that
  swapping the policy engine (builtin ↔ OPA, OPA leg gated on binary presence) and the
  deployment renderer changes target artifacts only, with the semantic manifest, decision
  lineage, and case digests unchanged; the full contributor journey from template →
  quarantine → contract suite → activation → evaluate/render; a poisoned, an unsigned,
  and an incompatible extension each stay quarantined.
- Version bump to `0.6.0.dev6`; STATUS/CHANGELOG/dependency-doc updates.

### Out

- Wiring policy decisions into existing compile stages or state-machine gates (candidate
  constraints, target preflight, and verification policy stay as deterministic compiled
  code; a policy decision is an additive governed artifact — gating transitions on it is
  a later, deliberate contract change).
- REST/web/MCP exposure of policy, render, or extension commands (Sprint 7 interface
  parity), regulatory-nexus/profile authoring flows, a real legal EU pack (the bundled
  pack is a synthetic fixture), OPA as a Python dependency or bundled binary, Helm/kubectl
  execution or any Kubernetes cluster contact, dynamic loading of extension code, remote
  extension registries or downloads, PostgreSQL persistence for the extension store
  (machine-local like keys/mailbox), `.github` changes, and the deferred known
  limitations carried from Sprint 5.

## Contract and data changes

Four new additive canonical schemas with examples and registry entries:
`extension-manifest.schema.json`, `policy-pack.schema.json`, `policy-decision.schema.json`,
`extension-activation.schema.json`. Two new workspace artifact kinds registered in
`KIND_SCHEMA`, `JSON_MEDIA_KIND`, and the workspace-manifest `kind` enum: `policy_pack`
(`application/vnd.oak.policy-pack+json`) and `policy_decision`
(`application/vnd.oak.policy-decision+json`), plus case extension
`oak.community/policy_decision_refs` (list) and `oak.community/policy_pack_refs` (list)
validated in workspace lineage. One additive audit event type: `policy_evaluated`.
Existing schemas, compiled artifacts, digests, the OpenAPI surface, and the database
schema are unchanged. `docs/dependencies.md` gains a Sprint 6 review section (no new
Python dependency; `opa` is an optional external binary documented with its trust
boundary).

## Milestones

1. **SDK contracts and schemas (`OAK-S6-001`, part `OAK-S6-004`)** —
   `oak.domain.extension_sdk` (SDK version, per-class versioned interfaces, renderer
   identities), `oak.domain.policy_rules` (pure bounded rule evaluation),
   the four new schemas + examples + `EXAMPLE_BY_SCHEMA`, workspace kind registration,
   `policy_evaluated` event type.
   Proof: `make validate` passes; schema conformance round-trips; rule engine unit suite
   covers every operator, aggregation order deny > review_required > allow > unknown-fail,
   and unknown pointer/operator fail-closed.
2. **Policy port, built-in engine, lifecycle (`OAK-S6-004`, part `OAK-S6-005`)** —
   `oak.ports.policy`, `oak.adapters.policies.builtin`, bundled fixture pack,
   `PolicyService` + `oak policy evaluate|packs`, effective/expiry/stale refusals,
   decision committed with pack artifact and audit lineage.
   Proof: identical decisions across fresh workspaces; expired/future packs refused with
   stable codes; the byte-stable reference journey and all prior suites unchanged.
3. **Extension supply chain (`OAK-S6-008`)** — store adapter, steward role,
   `ExtensionService`, `oak extensions ...` commands, activation records, adversarial
   fixtures (tampered digest, unsigned, wrong-key, incompatible SDK/oak version, poisoned
   pack tests, path traversal names).
   Proof: every adversarial fixture stays quarantined with machine-readable reasons;
   activation only after all checks; quarantined packs are unusable by `oak policy`.
4. **OPA adapter (`OAK-S6-005`)** — deterministic Rego translation, fixed-argv execution,
   availability probe, engine selection, equality contract.
   Proof: with `opa` present, builtin and OPA decisions are byte-identical across the
   fixture corpus; without it, selection fails with a stable code and builtin is
   unaffected; boundary check passes (subprocess only in adapters).
5. **Deployment renderer port and second adapter (`OAK-S6-006`)** — renderer port, both
   renderers, `oak render`, recorded backend decision.
   Proof: two clean workspaces render byte-identical file sets per renderer; renderers
   are swappable at the port with domain/application code untouched; no execution field,
   no secret, no unpinned image in any rendered file.
6. **Contract test kit, templates, developer guide (`OAK-S6-002`, `OAK-S6-003`)** —
   `tests/extension_kit/`, `templates/extensions/`, `docs/extension-sdk.md`.
   Proof: the kit passes against both engines, both renderers, the bundled pack, and
   every template; templates validate against their schemas in CI.
7. **Replacement test and exit demonstration (`OAK-S6-007`)** — swap suites, e2e
   contributor journey, docs/STATUS/CHANGELOG closure, version bump.
   Proof: swapping engine/renderer leaves case digests, semantic manifest, and decision
   lineage byte-identical while target artifacts differ; the exit demonstration passes
   through installed entrypoints; full `make check` green (verified by counting
   `make: ***` lines, not exit code).

Rollback for every milestone: revert the branch. All changes are additive; no existing
artifact kind, schema, digest, or state transition changes, and file mode remains the
source of truth.

## Verification

Unit suites for rule semantics, pack lifecycle dating, extension verification, renderer
determinism, Rego translation, and argv construction; contract suites extending the
schema/example conformance, execution-field ban, and adapter-identity checks to the new
schemas and renderer registry; integration suites for policy evaluation lineage, extension
quarantine/activation, engine and renderer replacement; e2e exit demonstration through
installed entrypoints; `make check`, `make audit`, `make sbom`; documentation policy scan
and `.github`-unchanged check.

## Security, privacy and authority review

Policy packs and extensions are untrusted input: bounded reads (size caps, no symlinks,
no YAML aliases), schema validation before any use, quarantine by default, and activation
only after digest + compatibility + licence + pinned-anchor signature + embedded-test
verification by an explicit local actor. Rule evaluation cannot execute code, reach the
network, or read files; unknown constructs fail closed to `review_required`/errors, so a
stale or ambiguous pack can never yield an automated approval (TM-17). The OPA adapter
runs only the allowlisted `opa` executable with adapter-constructed argv, `shell=False`,
sanitized environment, and bounded output; Rego is generated from validated pack rules,
never transported from documents. Renderers emit inert declarative files with digest-pinned
images and deny-all egress defaults and cannot weaken the runner: runner-side verification,
adapter allowlists, approval binding, and mutation gates are untouched. The steward signing
role is separate from plan-signer and approver, preserving separation of duties
(`OAK-NFR-GOV-001`); no LLM output authorizes anything. No secret values appear in packs,
decisions, rendered files, argv, or logs.

## Operational and rollback plan

The extension store lives under `~/.oak/extensions` (override `OAK_EXTENSIONS_DIRECTORY`)
beside the existing trust and mailbox directories; deleting a quarantined entry is safe;
deactivation reverses activation without deleting content, and activation records are
plain auditable JSON. Losing the steward key invalidates extension signatures, which are
re-signable from the payloads. Bundled fixture pack and templates ship in the wheel via
the existing force-include mechanism. Rollback is branch revert; no migration, no
database change, no change to compiled artifacts.

## Progress

- [x] 2026-08-19 Read STATUS, sprints.md, ADRs 0003/0005/0007/0011/0015, skills.md
  recipes, security invariants, threat model, and mapped every subsystem (ports,
  compiler, catalogue, runner/signing, persistence/application, CLI, tests/tooling,
  docs). Created `claude/sprint-6-policy-adapter-sdk`, authored this plan, claimed
  `OAK-S6-001`–`008`.
- [x] 2026-08-19 Milestone 1 complete. `oak.domain.extension_sdk` pins per-class
  interface versions, renderer identities, and deterministic capability discovery;
  `oak.domain.policy_rules` implements the bounded tri-state rule semantics where
  unknown never satisfies a gate; the four new schemas, examples, workspace kinds,
  `policy_evaluated` event, and `extension-steward` signature role registered.
- [x] 2026-08-19 Milestone 2 complete. `PolicyEnginePort`/`PolicyPackStorePort`, the
  built-in engine, the bounded pack store, the bundled `pack.community-baseline`
  fixture, and `PolicyService` committing engine-neutral `policy_pack` +
  `policy_decision` artifacts with audit lineage; `oak policy evaluate|packs`;
  expired/future/unpublished packs refuse evaluation with stable codes; identical
  inputs produce byte-identical decisions across fresh workspaces.
- [x] 2026-08-19 Milestone 3 complete. The quarantined-by-default extension store
  with authoritative directory identity, `ExtensionService` verification
  (schema, payload digests, compatibility, licence, pinned-anchor steward
  signature, class-specific payload checks incl. embedded pack tests), schema-valid
  activation records, materialized active packs, and the full
  `oak extensions` command set; tampered/unsigned/wrong-key/incompatible/poisoned/
  expired fixtures all stay quarantined.
- [x] 2026-08-19 Milestone 4 complete. The OPA adapter renders a deterministic
  tri-state Rego module (pack content only as JSON literals), runs the allowlisted
  `opa` binary with fixed argv/`shell=False`/sanitized env/bounds, and reuses the
  shared domain aggregation; equality proven byte-for-byte against the built-in
  engine over a 35-leaf operator corpus, composites, escaped pointers, and both
  shipped packs with a locally installed opa 1.19.1; absence is a stable error.
- [x] 2026-08-19 Milestone 5 complete. `DeploymentRendererPort` with the
  local-manifests and Helm/Kubernetes renderers behind pinned identities,
  `oak render`, byte-identical renders across fresh workspaces, digest-pinned
  images, deny-all egress, and no workspace mutation.
- [x] 2026-08-19 Milestone 6 complete. `tests/extension_kit` reusable checks,
  schema-valid templates for all five extension classes, `docs/extension-sdk.md`,
  and contract tests applying the kit to every shipped engine, pack, template, and
  the container fixture adapter.
- [x] 2026-08-19 Milestone 7 complete. Replacement proofs: builtin↔OPA canonical
  decisions byte-identical through the service; renderer swap changes target
  artifacts while the case digest, semantic manifest ref, and workspace revision
  stay untouched. The installed-entrypoint exit demonstration covers the template
  journey, explicit activation, quarantined unsigned/poisoned copies, both
  renderers, and capability discovery. Version bumped to `0.6.0.dev6` with
  regenerated OpenAPI passing the compatibility gate.
- [x] 2026-08-19 Byte-stability verified directly rather than inferred: the reference
  case was compiled on `main` and on this branch and the deployment-bundle,
  runner-plan, semantic-manifest, and selected-candidate digests are identical
  (`sha256:042313be…`, `sha256:5e0a65ba…`, `sha256:2ef34758…`, `sha256:576b0ca6…`),
  and `candidate-03` remains the stable pick at case `0.1.7`.
- [x] 2026-08-19 Full `make check` passed on the completed tree (verified by counting
  `make: ***` lines, not exit code): 301 unit/contract, the integration suites, and
  12 end-to-end tests including the new extension exit demonstration.

## Decisions

- 2026-08-19 The second deployment backend is **Helm/Kubernetes-shaped render** (not
  OpenTofu): ADR-0005 already records "a Kubernetes adapter second" and `OAK-FR-DEP-007`
  names local + Kubernetes as the two adapters; a chart-shaped deterministic render is
  independently useful (applyable by any k8s tooling out-of-band) while executing
  nothing, keeping Kubernetes optional.
- 2026-08-19 The canonical policy decision contains **no engine identity**; the engine is
  recorded as audit metadata. This makes "preserving a canonical decision result" testable
  as byte equality between builtin and OPA outputs and keeps engine swap invisible to
  decision lineage.
- 2026-08-19 Extension payloads are data only. A "deployment adapter" extension binds
  configuration to an in-tree renderer identity; runner adapters remain code registered in
  `oak.domain.runner_adapters`. This satisfies "no dynamic downloaded code execution"
  without pretending plugins are sandboxed.
- 2026-08-19 The policy decision artifact is additive and gates nothing yet: wiring
  decisions into state transitions is a deliberate future contract change, keeping this
  sprint's artifacts byte-stable and the reference journey untouched.
- 2026-08-19 The rule language lives in `oak.domain.policy_rules` (pure, leaf-safe) so the
  built-in adapter, pack self-tests during activation, and contract kits all share one
  semantics without new import edges.

## Discoveries and follow-ups

- `build_compiled_case` leaves the reference case at version `0.1.7` (the ExecPlan
  drafts and older notes said `0.1.6`); the new suites read the current version
  dynamically instead of hardcoding it.
- The interpreted reference intent records `regulatory_nexus.eu_nexus: possible`
  with `data.classifications: ["public"]`, so the bundled pack deterministically
  produces `review_required` on the reference case — an honest fixture outcome
  (legal facts unconfirmed → no automated approval).
- Python's native `==` treats `[True] == [1]` as equal while Rego's typed equality
  does not; `oak.domain.policy_rules._json_equal` now defines JSON-typed equality
  recursively so both engines agree at any nesting depth.
- Documentation files (`*.md`) inside an extension source directory are not
  governed payload: they are excluded from digesting and never copied into the
  store, so templates can ship READMEs without polluting supply-chain checks.
