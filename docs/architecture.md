<!-- SPDX-License-Identifier: Apache-2.0 -->

# Community harness architecture

OAK Community is a modular monolith with a separate runner trust domain. Sprint 1 adds the offline local `DesignCase` path to the serving skeleton and contract harness.

```text
CLI / HTTP / web -> application services -> domain values
                                  |       -> compiler
                                  v
                                ports
                                  ^
adapters -------------------------|
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

## Current interface paths

The CLI and HTTP API both construct the same `SystemInformationService`. That service reads immutable package/build metadata and returns one application result. Transport adapters only render that result. `/healthz`, `/readyz`, and `/version` expose no dependency details or sensitive values.

The API binds to `127.0.0.1` by default. A caller must pass an explicit unsafe-bind acknowledgement to listen on a non-loopback address. This acknowledgement does not claim that authentication is present.

The local CLI calls one `DesignCaseService` for initialization, brief interpretation, question review, confirmation, export, and import. The interface maps arguments and output only; the application service owns orchestration and uses intake and workspace ports. The deterministic compiler maps explicit facts, records inferences and unknowns with scalar provenance, ranks at most five questions, and treats any optional model result as an untrusted proposal.

## Local persistence and lineage

The file adapter stores one atomic `.oak/manifest.json` pointer and immutable content-addressed objects. A mutation takes the workspace lock, checks expected version and idempotency, validates all new artifacts, writes objects, then atomically replaces the manifest. A crash before replacement can leave only unreferenced objects; it cannot partially publish a case.

Every successful mutation creates a successor `DesignCase`, successor intent where applicable, and an audit event linked to the previous event digest. Raw source bytes remain a separate `brief_source` object and the source record marks them untrusted. Export and import validate manifest references, artifact identity, schemas, sizes, and digests before an imported workspace becomes visible.

## Canonical contracts

JSON Schema Draft 2020-12 files in `schemas/` are the external contract authority. Runtime wrappers preserve the parsed JSON data model and validate through a registry containing every canonical schema. Tests prove that public YAML examples validate and round-trip without semantic drift.

## Deferred behavior

Candidate generation and evaluation, plan compilation, signing, approvals, runner dispatch, and target access remain deferred. Later work must preserve immutable canonical versions, deterministic output, shared application services, and explicit authority gates.
