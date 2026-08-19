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
| jsonschema | Canonical JSON Schema validation | contracts | MIT |
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
