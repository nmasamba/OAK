<!-- SPDX-License-Identifier: Apache-2.0 -->

# Public compatibility policy

This policy governs every public surface of OAK Community from `0.7.0`, the first
Community release: canonical JSON Schemas, the REST/OpenAPI contract, the CLI, the MCP
tool surface, and the runner protocol. It exists so that a consumer can tell, before
upgrading, what may change under them and what may not. It is a pre-`1.0` policy: the
repository version (`VERSION`, a `0.x` series) signals that breaking change is still
possible — but never silent.

These promises bind external consumers operationally from the **first published
artifact**. That artifact exists: `0.7.1` was published as a GitHub Release on
2026-09-03 (tag `v0.7.1`; wheel and sdist with `SHA256SUMS`), so every rule here now
binds as written. Before that, no `0.7.x` artifact had been published anywhere, and the
`0.7.1` re-cut deliberately used that window for one digest-shifting change (the
`RR-032` verification-policy migration), recorded in the changelog exactly as rule 4
below requires rather than made silently. No such window remains. Publication is to
GitHub Releases only: nothing is on a package index or in an image registry.

## Versioning model

- **Repository version** (`VERSION`, `pyproject.toml`, `oak --version`, `/version`):
  one version for the whole distribution. Through `0.6.0.dev6` it moved as
  `0.<sprint>.0.dev<n>`; that development scheme is retired at `0.7.0`, and from `0.7.0`
  the version follows semantic versioning intent: patch releases are compatible, minor
  releases are additive, and any break lands only in a minor release with a changelog
  migration note. `0.7.0` rather than `0.1.0` is the first release because `0.1.0` would
  have sorted below the development builds that already existed; see
  [ADR-0002](adr/0002-release-versioning.md).
- **Object schema version** (`schema_version` inside canonical documents): versions each
  canonical data contract independently of the repository *and of the other schemas*.
  There is no single current number — schemas sit at `0.1.0`, `0.3.0` or `0.4.0`
  depending on when each was introduced and last changed; see
  [schemas/README.md](../schemas/README.md). `SUPPORTED_SCHEMA_VERSIONS` in
  `src/oak/bootstrap.py` lists the versions the **workspace manifest** may carry, which is
  a narrower thing than every readable document version.
- **Interface protocol versions**: the MCP server pins its supported protocol revisions
  in `SUPPORTED_PROTOCOL_VERSIONS`; the runner protocol carries `protocol_version` in
  every message; the canonical export carries `export_version`.

A change is **compatible** when every existing consumer and every stored document keeps
working unmodified; **conditionally compatible** when it works given a documented,
mechanical migration; **breaking** otherwise.

## Canonical JSON Schemas

- Schemas are closed (`additionalProperties: false`). Adding an *optional* field is
  compatible; adding a required field, removing a field, changing a type, or reusing an
  identifier with a new meaning is breaking and requires a `schema_version` bump plus an
  upgrade path for stored documents (tested, as `import`/migration behavior).
- Extension data lives under namespaced `extensions` keys (`oak.community/...`); core
  meaning may never move into an extension key or depend on one.
- `unknown` never satisfies a gate; loosening a validation rule so that previously
  rejected input is accepted is conditionally compatible and must be called out in the
  changelog; tightening one is breaking for producers and needs the same treatment as a
  field change.
- Semantic digests (`content_digest(canonical_json_bytes(...))`) are part of the
  contract: any change that shifts the canonical bytes of an unchanged document is
  breaking, even if the JSON "looks the same". Byte-stability of compiled artifacts is
  verified directly against the previous mainline before merge.
- Enum additions are conditionally compatible and are called out here. Sprint 9 added
  `model_proposed` to the provenance `source` enums in `common.schema.json` and
  `design-case.schema.json`, the optional `version` field to
  `interpretation-proposal.schema.json`, and the `interpretation_proposal` artifact kind
  to `workspace-manifest.schema.json`. Documents from the deterministic path carry none
  of them, so a 0.7.1 reader still validates every export from a workspace that never
  used the model path; an export from a workspace that did cannot be imported by 0.7.1.
- `model-configuration.schema.json` (Sprint 9) has never been published, so Sprint 10
  changed it in place at `0.1.0`: the `family` enum shrank to `huggingface` and `local`,
  `selection` became one entry per family, `verification` was added, and provider routes
  gained `is_free` and `throughput`. A file written by the unreleased Sprint 9 build is
  upgraded on load; a file written by Sprint 10 does not load on that build. The document
  is machine-local and never exported, so no stored canonical object is affected.

## REST and OpenAPI

- The committed `openapi/oak.openapi.json` is the contract; `make openapi-compatibility`
  diffs every change against `openapi/oak.compatibility-baseline.json` and fails on:
  removed paths or operations, removed response codes, changed required parameters,
  request bodies becoming required, removed schemas or properties, and property type
  changes. Additive paths, operations, optional properties, and schemas pass.
- A breaking REST change therefore requires a deliberate baseline reset
  (`--write-baseline`) in the same change, a changelog entry, and — from `0.7.0` — a
  deprecation period of at least one minor release in which the old behavior still
  works and is marked deprecated in the OpenAPI description.
- Error contracts are part of the surface: problem-details field names, stable
  `OAK-*` error codes, and status-code mappings may gain new codes freely, but an
  existing code may not change meaning or disappear while any documented flow uses it.
- Headers (`Idempotency-Key`, `If-Match`, `X-Correlation-ID`, `X-OAK-Actor`,
  `X-OAK-Tenant`) and their bounds are stable; tightening a bound is breaking.
  `X-OAK-Model-Token` (Sprint 9) is required only on the model-configuration routes it was
  introduced with and on `:interpret` when the configured model is used; it is never a
  required parameter of a pre-existing operation.
- The loopback guard (Sprint 9) — `Host` allowlist, `Origin` and `Sec-Fetch-Site` checks —
  runs as middleware before routing. It adds no parameter to the OpenAPI contract and is
  therefore outside this baseline; its behaviour is documented in
  [configuration.md](configuration.md) (`OAK_ALLOWED_HOSTS`) and pinned by
  `tests/integration/test_loopback_hardening.py`.

## CLI

- Stable surface: command names, positional argument meaning, documented option names,
  exit codes (`0` success, `2` refusal/invalid input, `4` version/idempotency conflict),
  the stdout/stderr split (data on stdout, `CODE: message` diagnostics on stderr), and
  the `--output json|yaml` document shapes, which mirror the application results.
- Adding a command or an option with a default that preserves old behavior is
  compatible. Renaming or removing a command/option, changing an exit code, or changing
  a JSON output shape is breaking and needs a changelog migration note; from `0.7.0`
  the old spelling must keep working (with a deprecation warning on stderr) for at
  least one minor release.
- Local mode and remote mode (`--server`) promise the same stable output and exit
  semantics; a command that cannot honor that in remote mode refuses with
  `OAK-REMOTE-UNSUPPORTED` rather than approximating.
- `oak design --interpreter deterministic|online|local` (Sprint 10, replacing Sprint 9's
  unreleased `auto|model|deterministic`) defaults to `deterministic`, which yields the
  `0.7.1` output for every brief. `oak questions` prints five open questions per round and
  counts the rest; the `--output json` document is unchanged and lists every persisted
  question. `oak models` (Sprint 9, reshaped in Sprint 10) is unreleased and carries no
  compatibility debt until `0.8.0`.

## MCP

- The tool registry in `oak.interfaces.mcp.tools.TOOL_DEFINITIONS` is the contract:
  tool names, required arguments, argument bounds, and result document shapes.
  `tests/contract/test_mcp_contract.py` pins that registry against a list of the eleven
  contract tools held in the test itself — it does **not** parse
  [docs/interfaces.md](interfaces.md), so adding a tool fails the test but keeping the
  capability matrix in step is a human step.
- Adding a tool or an *optional* argument is compatible. Removing a tool, renaming one,
  adding a required argument, or changing a result shape is breaking and follows the
  same changelog/deprecation rules as the CLI.
- The prohibition list is not versioned — it is permanent: no generic command executor,
  arbitrary file read, secret resolver, policy override, approval or impersonation
  tool, or runner-apply tool may be added under any version of this policy.
- Supported MCP protocol revisions are pinned in `SUPPORTED_PROTOCOL_VERSIONS`
  (currently `2025-06-18` and `2025-03-26`). Dropping a revision is breaking; adding
  one is compatible. Unsupported client revisions negotiate down to the newest
  supported revision rather than failing the handshake.
- `oak_design_case_interpret` gained the optional `interpreter` argument in Sprint 9;
  Sprint 10 closed it to `deterministic` | `online` | `local`. Its default is
  deterministic, so a client written against the previous registry gets exactly the
  previous behaviour; a model is called only when a client opts in.

## Runner protocol

- Every runner message and envelope carries `protocol_version`. The runner refuses a
  version it does not support; it never "best-effort" parses. Signature formats,
  digest algorithms (`sha256:`), and the verification order documented in
  [docs/signed-runner.md](signed-runner.md) are part of the contract.
- Any change to signed-payload canonicalization is breaking for every existing
  signature and requires an explicit migration (re-signing) note; trust-anchor file
  formats follow the schema rules above.
- The four forbidden execution fields (`command`, `shell`, `executable`, `argv`) are
  permanently invalid in every protocol version.

## Deprecation process

1. Announce the change and its migration in `CHANGELOG.md` under the release that
   ships it, and in the affected document under `docs/`.
2. Prefer additive coexistence (new field/command/tool beside the old) over in-place
   change whenever the surface allows it.
3. A break that affects stored data ships with a tested upgrade path in the same
   release (import/migration), never as a manual instruction alone.
4. A digest-shifting change is never silent: any change to the canonical bytes of an
   unchanged document is called out as such in the changelog, whatever else it is.

Before `0.7.0`, development (`.dev`) versions were permitted to break between themselves
without a deprecation window. From `0.7.0`, the deprecation window is at least one minor
release for every public surface above.
