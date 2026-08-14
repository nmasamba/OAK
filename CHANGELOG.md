<!-- SPDX-License-Identifier: Apache-2.0 -->

# Changelog

All notable changes to OAK Community are recorded here.

## Unreleased

### Added

- Complete Sprint 0 walking skeleton for `OAK-S0-001` through `OAK-S0-009`.
- Locked Python package with domain, compiler, application, port, adapter, interface, contract, and runner boundaries.
- Canonical schema registry and lossless public YAML/JSON runtime conformance suite.
- Shared application-service version/readiness queries exposed through the `oak` CLI and loopback-safe `oak-api` HTTP process.
- Generated OpenAPI 3.1 artifact, strict TypeScript client, and accessible local status shell.
- Local PostgreSQL/API/web Compose harness with health checks and loopback-only published ports.
- Stable Make entrypoints, CI, dependency audits, secret-pattern checks, and development SBOM generation.
- Repository hygiene rules that exclude agent state, secrets, build output, local runtime data, and editor files.
- Separate local-source compatibility from exact CI/container builder pins, with an executable drift check across toolchain files, package metadata, images, CI, and documentation.

### Security

- The initial harness is non-mutating and binds its API to loopback by default.
- Dependency build hooks are denied by default except for the explicitly reviewed, lockfile-pinned `esbuild` hook.
- Vite was upgraded to 7.3.6 after the initial dependency audit identified high-severity advisories in 7.1.4.
