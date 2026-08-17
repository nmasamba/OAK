<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dependency record

Sprint 0 uses small, replaceable open components at interface and validation boundaries.

| Component | Purpose | Boundary | Licence family |
|---|---|---|---|
| Pydantic | Typed runtime boundary models | contracts/interfaces | MIT |
| FastAPI | OpenAPI HTTP adapter | interfaces only | MIT |
| Typer | CLI adapter | interfaces only | BSD-3-Clause |
| Uvicorn | Local ASGI process | interface entrypoint | BSD-3-Clause |
| jsonschema | Canonical JSON Schema validation | contracts | MIT |
| PyYAML | Public YAML example parsing | contracts | MIT |
| React | Static status view | web only | MIT |
| Vite | Web build tooling | web development | MIT |
| TypeScript | Strict web type checking | web development | Apache-2.0 |

The core domain and compiler packages do not import these interface frameworks. Development-only format, lint, type, test, audit, and SBOM tools are locked but do not ship as runtime requirements.

Rollback is a manifest-and-lockfile revert. No dependency creates a hosted runtime requirement or receives customer content in this sprint.

The pnpm workspace permits an install-time build hook only for the lockfile-pinned `esbuild` package required by Vite. All other dependency build scripts remain blocked by default.

Container base images use readable version tags plus immutable manifest digests. Updating a base requires an explicit manifest edit, rebuild, and audit rather than an implicit tag move.
