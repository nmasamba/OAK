<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dependency record

OAK uses small, replaceable open components at interface, validation, and persistence
boundaries. Versions are locked in `uv.lock` and `pnpm-lock.yaml`; ranges below are not a
substitute for those locks.

| Component | Purpose | Boundary | Licence family |
|---|---|---|---|
| Pydantic | Typed runtime boundary models | contracts/interfaces | MIT |
| FastAPI | OpenAPI HTTP adapter | interfaces only | MIT |
| Typer | CLI adapter | interfaces only | BSD-3-Clause |
| Uvicorn | Local ASGI process | interface entrypoint | BSD-3-Clause |
| jsonschema | Canonical JSON Schema validation | contracts | MIT (no extras; see the 2026-08-21 review) |
| PyYAML | Public YAML example parsing | contracts | MIT |
| SQLAlchemy 2.0 | PostgreSQL transaction and mapping toolkit | PostgreSQL persistence adapter only | MIT |
| Alembic | Forward-only PostgreSQL migrations | migration tooling and API/worker startup | MIT |
| cryptography (PyCA) | Ed25519 signing and verification | signing adapter and runner verification | Apache-2.0 OR BSD-3-Clause |
| Psycopg 3 with binary implementation | PostgreSQL DB-API driver and bundled local `libpq` | below SQLAlchemy in PostgreSQL processes only | LGPL-3.0-only; bundled libraries retain their terms |
| React | Architecture workspace UI | web only | MIT |
| Vite | Web build tooling | web development | MIT |
| TypeScript | Strict web type checking | web development | Apache-2.0 |
| Playwright | Browser end-to-end harness | web development only | Apache-2.0 |
| axe-core (via @axe-core/playwright) | Automated accessibility checks | web development only | MPL-2.0 |

The core domain and compiler packages do not import interface or persistence frameworks.
Development-only format, lint, type, test, audit, and SBOM tools are locked but do not ship as
runtime requirements.

## Sprint 3 persistence review

The capability gap is ACID PostgreSQL transactions, migrations, and a maintained Python
driver. Reimplementing SQL parsing, connection pooling, PostgreSQL type adaptation, migration
ordering, and concurrency behavior with the standard library would be unsafe. ADR-0013
already selects PostgreSQL, SQLAlchemy, and Alembic for Community `0.x`; this review selects
Psycopg 3 as the driver.

- **SQLAlchemy 2.0:** established MIT-licensed toolkit with explicit PostgreSQL/DB-API
  boundaries and Python 3 support. OAK uses SQLAlchemy only in
  `oak.adapters.persistence`, so the repository port is the replacement seam.
- **Alembic:** maintained by the SQLAlchemy project under MIT and designed for SQLAlchemy
  metadata. It is invoked only for database schema lifecycle. Migrations remain plain,
  reviewable Python/DDL and do not define canonical object meaning.
- **Psycopg 3:** the current maintained Psycopg generation, supports Python 3.13 and
  PostgreSQL 17, and exposes sync/async DB-API behavior. It is LGPL-3.0-only rather than
  permissive. ADR-0011 permits contextually reviewed OSI-approved copyleft dependencies and
  requires their independent terms to be recorded. OAK does not copy or modify Psycopg; it
  remains a replaceable SQLAlchemy driver. The `binary` extra is chosen for reproducible local
  Community/container setup without host `libpq` headers and brings its own client libraries;
  the SBOM and vulnerability audit therefore cover both Python distributions and bundled
  native libraries. A production distribution may replace it with the source/C build behind
  the same SQLAlchemy URL after an image-level review.

The selected ranges intentionally stay on SQLAlchemy 2.0 and Psycopg 3 major versions.
Alembic revisions are forward-only. A dependency rollback reverts `pyproject.toml` and
`uv.lock`; file-backed local mode has no dependency on this stack.

No dependency creates a hosted runtime requirement. PostgreSQL receives only the canonical
control-plane metadata permitted by the data boundary; production/customer content remains
excluded by default.

## Sprint 5 signing review

The capability gap is asymmetric signatures for plan, approval, and runner-message
authenticity. Implementing Ed25519 by hand would be unsafe. `cryptography` is the PyCA
reference implementation, dual-licensed Apache-2.0 OR BSD-3-Clause, and is used only through
two narrow seams: `oak.adapters.signing` holds private keys and signs, while
`oak.contracts.signatures` verifies. The runner imports the verification path alone and
never loads a private key. Keys are raw 32-byte Ed25519 seeds in a 0600 file under a private
trust directory, labelled `development`; Community makes no production assurance claim. The
`SigningPort` is the replacement seam if a KMS or hardware backend is introduced later.

## Sprint 6 policy engine review

The capability gap is an optional open policy evaluator behind the policy port. No Python
dependency was added: the OPA adapter executes a locally installed `opa` binary (Open
Policy Agent, Apache-2.0, CNCF-graduated) through a fixed allowlisted argument vector with
`shell=False`, a sanitized environment, timeouts, and bounded output. The binary is never
downloaded, bundled, or required: `oak policy evaluate` defaults to the deterministic
built-in engine, engine selection is explicit, and a missing binary is a stable
`OAK-POLICY-ENGINE-UNAVAILABLE` error. Generated Rego carries pack content only as
JSON-encoded literals, and the engine-equivalence suite proves byte-identical canonical
evaluations against the built-in engine whenever `opa` is present. The `PolicyEnginePort`
is the replacement seam; removing the adapter removes the integration completely.

## Sprint 4 web test tooling review

The capability gap is real-browser verification of the workspace journey, failure
recovery, and accessibility. Playwright (Apache-2.0, Microsoft-maintained) and axe-core
(MPL-2.0, Deque-maintained, consumed unmodified through `@axe-core/playwright`) are
development-only dependencies in the web workspace; neither ships in runtime artifacts or
images. Neither package registers an install-time build hook, so the pnpm build allowlist
is unchanged. Browser binaries are not vendored: `playwright install chromium` fetches the
pinned build explicitly, and the suite itself needs only the local Compose stack. ADR-0011
permits the reviewed MPL-2.0 component; axe-core remains replaceable behind the single
`expectAccessible` helper in the end-to-end support module.

The pnpm workspace permits an install-time build hook only for the lockfile-pinned `esbuild` package required by Vite. All other dependency build scripts remain blocked by default.

Container base images use readable version tags plus immutable manifest digests. Updating a base requires an explicit manifest edit, rebuild, and audit rather than an implicit tag move.

## Sprint 7 interface review

The capability gap is a Model Context Protocol server and a remote CLI transport. No Python
dependency was added for either.

The MCP server implements the stdio transport in-tree over the standard library. Community
exposes only `initialize`, `ping`, `tools/list` and `tools/call` on newline-delimited stdio;
the reference `mcp` SDK would have added five runtime dependencies (`httpx`, `httpx-sse`,
`sse-starlette`, `pydantic-settings`, `python-multipart`) to support HTTP and SSE transports
that Community does not offer, enlarging the supply chain and the audit surface of the one
interface whose whole purpose is boundedness. Supported protocol revisions are pinned in
`SUPPORTED_PROTOCOL_VERSIONS` and governed by [compatibility.md](compatibility.md); the
replacement seam is `oak.interfaces.mcp`, and adopting the SDK later would not change the
tool contract. Revisit if Community needs HTTP transports or the resources/prompts/sampling
capabilities.

The remote CLI client uses `urllib.request` from the standard library with explicit timeouts
and bounded reads rather than adding a runtime HTTP dependency. One bounded request per
command against a local control plane does not justify enlarging the released dependency set;
`httpx` remains a development-only dependency used by the API test suites. The replacement
seam is `oak.interfaces.cli.remote.RemoteClient`.

Webhook envelope verification reuses the existing `cryptography` Ed25519 primitives and the
in-tree `oak.contracts.signatures` verifier; no new signing or HTTP-server dependency was
introduced, and Community ships no webhook dispatcher.

## Maintenance reviews

Reviews outside a sprint boundary are recorded here, newest first, under the same standard
as a sprint dependency review.

### 2026-08-21 jsonschema `format` extra removed

The `jsonschema[format]` extra was dropped from `pyproject.toml` in favour of plain
`jsonschema`. The extra was never load bearing: nothing in `src/` constructs a
`FormatChecker` or passes `format_checker=` to a validator, so `format` keywords in the
canonical schemas have always been annotation rather than validation — the behaviour
`docs/interfaces.md` and the Sprint 7 limitations already record.

What the extra did do was place eight packages in the runtime dependency closure of the
distribution, one of which is `rfc3987` 1.3.8, licensed **GPL-3.0-or-later**. OAK Community
is Apache-2.0. ADR-0011 permits a contextually reviewed OSI-approved copyleft dependency and
requires its independent terms to be recorded — as was done for Psycopg's LGPL — but this one
was neither reviewed nor recorded: the inventory above listed jsonschema as simply "MIT". A
release licence inventory would have had to either disclose an undiscussed GPL transitive or
misstate the closure.

`jsonschema[format-nongpl]` was considered and rejected. It swaps `rfc3987` for
`rfc3987-syntax` and resolves the licence question, but it keeps eight unused runtime
packages in order to preserve a capability that nothing enables. Enabling format checking was
also rejected: tightening validation so previously accepted documents are refused is a
breaking change for producers under `docs/compatibility.md`, and a release-hardening sprint is
the wrong place to make one.

Effect on the closure, measured with `uv export --no-default-groups`: 37 runtime packages,
down from 45. `fqdn`, `isoduration`, `jsonpointer`, `rfc3339-validator`, `rfc3987`,
`uri-template`, and `webcolors` all leave; `idna` stays because `anyio` requires it.
`rfc3987-syntax` and `rfc3986-validator` remain in `uv.lock` and in the development
environment because `cyclonedx-python-lib` — the SBOM generator, a development dependency —
itself depends on `jsonschema[format-nongpl]`. They are not runtime requirements of the
released wheel.

Rollback is restoring the extra in `pyproject.toml` and re-running `uv lock`. No canonical
document, digest, or schema changes: the reference case remains byte-stable, verified
directly. Should format validation ever be wanted, it must arrive as a deliberate,
changelog-announced tightening with `format-nongpl`, never with `format`.

### 2026-08-20 cryptography 46.0.7 to 50.0.0

`pip-audit` reported four advisories against the locked `cryptography` 46.0.7:
`GHSA-537c-gmf6-5ccf` (statically linked OpenSSL in the published wheels, fixed in 48.0.1),
`PYSEC-2026-3552` (PKCS#7 EnvelopedData Bleichenbacher oracle, fixed in 50.0.0),
`PYSEC-2026-3553` / CVE-2026-69249 (X.509 chain-building denial of service, fixed in
49.0.0), and `PYSEC-2026-3554` / CVE-2026-69248 (X.509 DNS name-constraint wildcard escape,
fixed in 49.0.0). No other locked Python or web package carried an advisory.

None of the four is reachable from OAK. `oak.adapters.signing`, `oak.runner.identity`, and
`oak.contracts.signatures` use raw-bytes Ed25519 only — generate, seed load, raw public and
private bytes, sign, and verify. OAK loads no X.509 certificate or chain, decrypts no PKCS#7
structure, and calls no serialization or key-loading API. The upgrade was taken anyway:
reachability is a property of today's call graph rather than a durable control, and this
component is the trust root for plan signatures, approvals, runner envelopes, and
extension-steward signatures. Only 50.0.0 clears all four; 48.0.1 clears one and 49.0.0
clears three. No advisory was suppressed and no `pip-audit` ignore list was introduced.

Verified from primary sources for 50.0.0: the licence expression remains
`Apache-2.0 OR BSD-3-Clause`, so the inventory row above is unchanged; supported Python is
3.9 to 3.14, covering the pinned 3.13.12; `cffi` is the only runtime requirement and the
lock already carries `cffi` 2.1.1 with `pycparser` 3.0, both advisory-free and unmoved by
this change; nothing else in `uv.lock` depends on `cryptography`, so the only edge is
downward.

Platform support narrowed. From 49.0.0 the project no longer publishes macOS x86_64 or
32-bit Windows wheels. `manylinux2014`, `manylinux_2_28`, and `manylinux_2_34` wheels are
published for x86_64 and aarch64, so `python:3.13.12-slim` resolves a wheel and the API
image still needs no Rust toolchain. macOS contributors now require an arm64 interpreter;
an Intel or Rosetta interpreter falls through to the source distribution and cannot build
without Rust.

Backwards-incompatible changes across 47.0.0 to 50.0.0 were reviewed against OAK's call
graph and none is reached: binary elliptic curves, OpenSSL 1.1.x, LibreSSL below 4.1, and
Python 3.8 support were removed; unsupported key loading now raises `UnsupportedAlgorithm`
and `public_bytes`/`private_bytes` raise `TypeError` where they previously raised
`ValueError`; ChaCha20 enforces RFC 7539 counter overflow; stricter X.509 and CRL parsing
rejects mismatched signature algorithms; and finite-field Diffie-Hellman is deprecated. The
two exception-type changes were checked explicitly, because `oak.contracts.signatures`
returns `False` rather than raising and its `except` clause is a fail-closed control: the
raw-bytes loaders it uses still raise `ValueError` on a wrong-length key, and
`tests/unit/test_signing.py` now pins that behaviour.

Ed25519 signatures are deterministic under RFC 8032 and are unchanged by this upgrade — a
fixed-seed signature is byte-identical before and after — so existing signed artifacts,
trust anchors, and canonical digests remain valid and no key rotation or re-signing is
required.

The replacement seam is unchanged: `SigningPort` for signing and `oak.contracts.signatures`
for verification. Rollback is reverting `pyproject.toml` and `uv.lock` together and
re-running `uv sync --frozen`, which restores 46.0.7 and returns `make audit` to a failing
state, so it is a temporary measure only.
