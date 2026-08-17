<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR-0001: Pin supported toolchains and handwrite runtime contract wrappers

- Status: Accepted
- Date: 2026-08-14
- Task IDs: `OAK-S0-001`, `OAK-S0-004`, `OAK-S0-007`

## Context

The walking skeleton needs reproducible Python and web workspaces and bidirectional conformance with canonical JSON Schemas. Generating a separate class graph for every schema would add a second generated authority before domain behavior exists.

## Decision

Pin Python 3.13.12 and Node.js 24.18.0 for the supported repository build. Lock Python dependencies with `uv` and web dependencies with `pnpm`. Local source development accepts the tested `uv` 0.10.x series; CI and the API container pin exact builder version 0.10.8. Python support is an explicit repository decision and is not derived from the Python versions discoverable by a contributor's local `uv` installation.

Treat the container build as the self-contained runtime build path: a container user needs no host Python, `uv`, Node.js, or `pnpm`. These toolchains build OAK itself and do not describe an eventual compilation target. Target hardware and environment capabilities belong to an explicit target profile or a target-side inventory adapter at invocation time.

Keep JSON Schema files authoritative. Use a handwritten, generic Pydantic root wrapper for parsed canonical documents and validate it against a complete Draft 2020-12 schema registry. API-specific response models remain handwritten and small. Tests assert validation, rejection, and lossless YAML/JSON/runtime round trips.

## Consequences

There is no generated model drift in Sprint 0, but application work must add typed domain models deliberately rather than treating arbitrary dictionaries as canonical domain state. Revisit generation when repeated domain models create measurable maintenance cost; schema conformance remains mandatory either way.

Exact CI/container builder pins and the local compatibility declaration are checked together so they cannot drift silently. Updating a runtime or builder remains an explicit, tested repository change, without coupling target selection to the control-plane host.
