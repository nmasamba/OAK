<!-- SPDX-License-Identifier: Apache-2.0 -->

# Changelog

All notable changes to OAK Community are recorded here.

## Unreleased

### Added

- Sprint 2 offline compiler flow for `OAK-S2-001` through `OAK-S2-011`.
- Governed synthetic catalogue snapshots and provider-neutral baseline, minimum, balanced, and high-assurance pattern contracts.
- Deterministic hardware, deployment, security, licence, locality, and compatibility constraints with fail-closed unknown handling.
- Transparent cost, latency, quality, operability, and energy ranges with estimator/calibration metadata and Pareto sensitivity.
- Digest-linked fixture evaluation results, immutable selection decisions, assurance plans, and a stable `candidate-03` exit path.
- Canonical review bundle and draft typed runner plan with byte-stable normalized semantic manifests.
- Sprint 1 offline `DesignCase` workflow for `OAK-S1-001` through `OAK-S1-010`.
- Atomic file-backed workspace with immutable content-addressed artifacts, expected-version checks, idempotent mutations, append-only audit lineage, and digest-verified export/import.
- Bounded YAML, JSON, Markdown, and text intake with source quarantine and adversarial path, type, size, structure, and Unicode checks.
- Deterministic typed intent interpretation with complete scalar provenance, stable findings, and at most five ranked clarification questions.
- Provider-neutral optional interpretation proposals, resource limits, and a deterministic failure-injection adapter; no model provider is required.
- Confirmation successors for confirm, correct, reject, and accept-risk decisions, exposed through human, JSON, and YAML CLI commands.
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

- Catalogue and target inputs are bounded, schema-validated, alias/symlink safe, and cannot select executable behavior.
- Target profiles are bound to command tenancy and checked for declared platform, capacity, and read-only planning capabilities before bundle publication.
- Immutable evaluation results cannot be overwritten by a second non-idempotent evaluation.
- Runner-plan parameter schemas recursively reject command, shell, executable, and argument-vector fields; Sprint 2 operations are non-mutating and never dispatched.
- Raw brief content remains an untrusted, separate artifact; text instructions cannot invoke tools or approve claims.
- Workspace publication uses a lock and atomic manifest replacement, while import rejects symlinks, corruption, digest mismatch, and artifact identity tampering.
- Idempotent lookup now follows actor/correlation and tenant-context validation.
- The initial harness is non-mutating and binds its API to loopback by default.
- Dependency build hooks are denied by default except for the explicitly reviewed, lockfile-pinned `esbuild` hook.
- Vite was upgraded to 7.3.6 after the initial dependency audit identified high-severity advisories in 7.1.4.
