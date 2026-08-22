<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0013: Use a Python modular core and TypeScript web workspace for Community 0.x

- Status: Accepted
- Date: 2026-08-14
- Owners: @architecture, @maintainers
- Requirement IDs: OAK-NFR-REL-001–003, OAK-NFR-PERF-001–002, OAK-NFR-PORT-001–002

## Context

The first application needs typed contracts, an offline CLI, a REST service, deterministic compiler stages, strong testing and access to AI/solver/IaC ecosystems. It also needs an accessible interactive workspace. One team must be able to ship and operate the reference implementation without premature distributed-system overhead.

## Decision

For Community `0.x`:

- implement the domain, compiler, application services, CLI, API, worker, MCP adapter and reference runner in Python 3.12+;
- manage/lock the Python workspace with `uv` and expose stable Make targets;
- use Pydantic v2 for runtime boundary models with conformance tests against the canonical JSON Schemas;
- use FastAPI and OpenAPI 3.1 for the first REST network contract and Typer for the CLI;
- use PostgreSQL, SQLAlchemy and Alembic for server persistence/migrations while preserving a file-backed local repository;
- use React, TypeScript, Vite and a `pnpm` lockfile for the static web workspace;
- use PostgreSQL-backed job leases and a transactional outbox before adding a mandatory broker;
- use a local content-addressed artifact store first, with OCI/object-store ports.

Official project documentation confirms the relevant baseline capabilities: [FastAPI uses OpenAPI/JSON Schema](https://fastapi.tiangolo.com/features/), [Pydantic supports JSON Schema 2020-12 and OpenAPI 3.1](https://docs.pydantic.dev/latest/concepts/json_schema/), [uv supports locked projects/workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/), [Typer is type-hint based](https://typer.tiangolo.com/), [SQLAlchemy documents asyncio support](https://docs.sqlalchemy.org/en/latest/orm/extensions/asyncio.html), and [Vite supports TypeScript while requiring a separate type-check step](https://vite.dev/guide/features).

Exact supported versions belong in toolchain files and lockfiles, not this ADR. The runner remains a separate image/process even while sharing language/contracts.

## Alternatives

- **Go/Rust compiler and runner from the start:** strong binaries/isolation but duplicates contract/application work before the product flow is proven; a future hardened runner may replace the reference implementation behind the protocol.
- **TypeScript end to end:** one language, but weaker fit for the initial compiler/AI/solver ecosystem and existing Python validation assets.
- **Microservices and broker first:** rejected until scale/team/failure evidence justifies distributed semantics.
- **SQLite as server system of record:** useful for isolated tooling but insufficient as the declared concurrency/transaction baseline; file local mode already covers no-database use.

## Consequences

Strict module/import rules and port contract tests are required to prevent framework coupling. Two language toolchains add maintenance. Lockfiles, SBOM and licence review are release inputs. The choice constrains OAK implementation only; generated systems remain language-agnostic.

## Revisit triggers

Measured performance or isolation failures; unsupported target platforms; an independently maintainable runner team; or persistent friction maintaining schema/runtime parity. A rewrite must preserve the public contracts and conformance suite.
