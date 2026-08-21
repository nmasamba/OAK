<!-- SPDX-License-Identifier: Apache-2.0 -->

# Extension SDK

OAK Community accepts governed extensions without compiler-core changes and
without weakening any runner rule. This guide covers the five extension
classes, the policy rule language, the supply-chain lifecycle, the renderer
port, and the reusable contract test kit.

## Versioned interfaces and capability discovery

`oak.domain.extension_sdk` pins one versioned interface per extension class;
`oak extensions capabilities` prints the deterministic discovery document:
SDK version, per-class interface versions and payload schemas, registered
policy engines, deployment renderer identities, and typed runner adapter
identities with their kind allowlists.

| Extension class | Payload | Interface |
|---|---|---|
| `policy-pack` | `pack.yaml` (`policy-pack.schema.json`) | 1.0.0 |
| `deployment-adapter` | `adapter.yaml` binding a registered renderer | 1.0.0 |
| `component-manifest` | component manifests | 1.0.0 |
| `architecture-pattern` | architecture patterns | 1.0.0 |
| `runner-adapter` | `adapter.yaml` binding a registered runner adapter | 1.0.0 |

Extension payloads are data. Nothing installs, downloads, or executes code:
deployment renderers and runner adapters are reviewed in-tree source with
pinned identities, and extensions bind or distribute governed documents only.

## The contributor journey

```bash
cp -r templates/extensions/policy-pack my-pack
# edit my-pack/pack.yaml and my-pack/extension.yaml
oak keys init                       # once; creates the extension-steward key
oak extensions sign my-pack         # recomputes digests, signs the manifest
oak extensions install my-pack      # lands in quarantine
oak extensions verify extension.my-pack
oak extensions activate extension.my-pack
oak policy evaluate --pack pack.my-pack
```

Every install is quarantined under `~/.oak/extensions` (override with
`OAK_EXTENSIONS_DIRECTORY`). Activation runs the full verification and is an
explicit local action; a failed check leaves the extension quarantined with
machine-readable reasons in `verification-report.json`. Activation writes a
schema-valid `activation.json` binding the manifest digest, actor, time, and
every passing check. `oak extensions deactivate` reverses activation without
deleting content.

Verification checks, all fail-closed:

- `manifest-schema` — `extension-manifest.schema.json` validity;
- `payload-digest` — every declared file digest and the aggregate
  `payload_digest` match the files on disk, with no undeclared files;
- `compatibility` — the class interface version is supported and the running
  OAK version is inside the declared range;
- `licence` — an SPDX expression is declared;
- `signature` — a signature by the `extension-steward` role, verified against
  the **pinned** local trust anchor (`oak keys init` creates it; a key
  embedded in the manifest is a claim, never an anchor);
- `payload-content` — class-specific: schema validity, registered binding
  identities, and for policy packs the effective window, a pack id that does
  not collide with an already-available pack, and every embedded test under
  the built-in engine.

Two further rules hold at activation. Exactly one version of an extension is
active at a time: activating a second returns `OAK-EXTENSION-VERSION-ACTIVE`
until the current one is deactivated, because the active namespace is keyed by
extension id and a second version would shadow the first. And an activated
pack is read in place from its verified directory rather than copied, so the
pack that is evaluated is always the pack that was digest-checked and
signature-verified.

Payload YAML is parsed with the same bounded, alias-free reader as every other
untrusted input, so a payload using anchors is refused at verification rather
than activating and breaking later policy reads.

## Policy packs

A pack is effective-dated (`effective_from`, `expires_at`), scoped
(jurisdictions, domains), evidenced (`source_version`, `evidence[]`), owned,
reviewed, and tested (`tests[]`). `oak policy evaluate --pack <id>` refuses
stale, future, or unpublished packs with stable codes
(`OAK-POLICY-PACK-EXPIRED`, `-NOT-YET-EFFECTIVE`, `-STATUS`).

Rules are declarative conditions over the canonical subject
`{case_id, intent_spec, candidate}`:

- leaves: `{pointer, operator, value?}` with operators `equals`,
  `not_equals`, `in`, `not_in`, `less_or_equal`, `greater_or_equal`,
  `exists`, `absent`, `contains`, `subset_of` (resolved value ⊆ rule value);
- composites: `{all: [...]}`, `{any: [...]}`, `{not: ...}`.

Evaluation is tri-state. An unresolved pointer, a type mismatch, or a
degenerate composite (an empty `all`/`any`, which the schema forbids but the
semantics refuse independently) is *undecidable*, the rule reports `unknown`,
and the pack outcome becomes `unknown` — an undecidable pack can never produce
an automated allow (threat model TM-17). Matched rules aggregate as
`deny > review_required > allow`; no matched rule is also `unknown`.

The canonical `policy-decision` document is engine-neutral: it binds the pack
digest, subject digest, per-rule results, sorted reasons, and obligations,
and never names the engine (the audit event records that). The built-in
engine is the required offline reference implementation and an external
engine is never an independent oracle. The OPA adapter (`--engine opa`,
requires a locally installed `opa` binary) recomputes the reference evaluation
and refuses with `OAK-POLICY-ENGINE-DIVERGED` rather than publish a decision
the built-in engine would not produce, so an engine version whose comparison
semantics differ, a translation defect, or a tampered module fails closed and
visibly. `tests/integration/test_engine_equivalence.py` proves the two agree
byte-for-byte across the operator corpus and the shipped packs whenever the
binary is present.

## Deployment renderers

`DeploymentRendererPort` (in `oak.ports.rendering`) turns the immutable
bundle, semantic manifest, and component manifests into deterministic inert
files. Two renderers ship in-tree behind pinned identities in
`RENDERER_IDENTITY_BY_ID`:

- `renderer.local-manifests` — the canonical JSON review file set;
- `renderer.helm-kubernetes` — a chart-shaped, digest-pinned, deny-all-egress
  Kubernetes render (ADR-0005's recorded second backend; Kubernetes stays
  optional and nothing executes helm or kubectl).

`oak render --adapter <id> --output <dir>` renders into a new directory and is read-only
with respect to the case: swapping
renderers changes target artifacts only — the case, its digests, and its
decision lineage are untouched. A new backend is contributed as reviewed
source implementing the port plus a registered identity, and must pass the
renderer kit checks.

## Runner adapters

Runner adapters remain governed by ADR-0015: identities, digests, parameter
schemas, and kind allowlists are code in `oak.domain.runner_adapters`, and
the runner independently re-verifies everything before target access. The
extension mechanism can document and configure a registered adapter but can
never introduce executable payloads, widen argv, or bypass approvals.

## Contract test kit

`tests/extension_kit` is importable from any test module:

- `check_engine_determinism`, `check_engine_matches_reference`,
  `check_engine_fails_closed_on_unknown` — policy engines;
- `check_pack_governance_fields`, `check_pack_lifecycle_dating`,
  `check_pack_embedded_tests` — policy packs;
- `check_renderer_determinism`, `check_renderer_output_safety`,
  `check_renderer_replaceability` — deployment renderers;
- `check_argv_injection_resistance` (with `INJECTION_PARAMETER_SETS`) and
  `check_typed_rollback` — typed runner adapters.

The kit itself runs fully offline: every check takes an injected port and
none shells out. The only network-adjacent behavior in this SDK is the
optional local `opa` binary. At runtime its absence is a stable
`OAK-POLICY-ENGINE-UNAVAILABLE` error rather than a silent fallback — an
explicitly requested engine never degrades to a different one. In the test
suite the built-in engine's checks always run, while the cross-engine
equivalence suite (`tests/integration/test_engine_equivalence.py`) is skipped
when the binary is absent, since it has nothing to compare against; the
built-in engine remains authoritative either way.
