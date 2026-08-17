<!-- SPDX-License-Identifier: Apache-2.0 -->

# Community harness architecture

OAK Community begins as a modular monolith with a separate runner trust domain. Sprint 0 implements only the control-plane serving skeleton and contract harness.

```text
CLI / HTTP / web -> application queries -> domain values
                                  -> ports
adapters ----------------------------^
canonical schemas -> contract registry
runner -> runner-owned protocols and adapters
```

## Enforced package boundaries

- `oak.domain` owns pure values and errors. It does not import transports, persistence, provider SDKs, or subprocess APIs.
- `oak.compiler` owns deterministic transformations and depends only on domain and contracts.
- `oak.application` orchestrates domain/compiler behavior through ports. It does not import concrete adapters or transport models.
- `oak.ports` declares protocols using domain-oriented types.
- `oak.adapters` implements ports and contains third-party translation.
- `oak.interfaces` maps transport requests to application requests and results. It does not write state directly.
- `oak.runner` remains a separate package boundary and has no control-plane database or model dependency.

Automated AST checks enforce these dependency directions and reject shell execution patterns outside the future runner/deployment-adapter boundary.

## Current serving path

The CLI and HTTP API both construct the same `SystemInformationService`. That service reads immutable package/build metadata and returns one application result. Transport adapters only render that result. `/healthz`, `/readyz`, and `/version` expose no dependency details or sensitive values.

The API binds to `127.0.0.1` by default. A caller must pass an explicit unsafe-bind acknowledgement to listen on a non-loopback address. This acknowledgement does not claim that authentication is present.

## Canonical contracts

JSON Schema Draft 2020-12 files in `schemas/` are the external contract authority. Runtime wrappers preserve the parsed JSON data model and validate through a registry containing every canonical schema. Tests prove that public YAML examples validate and round-trip without semantic drift.

## Deferred behavior

Case mutations, persistence, compiler stages, signing, approvals, runner dispatch, and target access are outside Sprint 0. Later work must preserve immutable canonical versions, deterministic output, shared application services, and explicit authority gates.
