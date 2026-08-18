<!-- SPDX-License-Identifier: Apache-2.0 -->

# Community control-plane architecture

OAK Community is a modular monolith with a separate runner trust domain. The same application
services now support the offline file workspace and the persistent PostgreSQL/REST control
plane through deterministic candidate comparison, fixture evaluation, assurance, and
non-executing plan compilation.

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

The CLI and HTTP API construct the same application services. `/healthz`, `/readyz`, and
`/version` expose only coarse process/dependency status and immutable build metadata. The
`/v1` handlers authenticate the configured local actor/tenant, parse typed requests and
headers, then call `CommunityControlPlane`; transition policy remains in `DesignCaseService`
and `CandidatePlanningService`.

The API binds to `127.0.0.1` by default. A caller must pass an explicit unsafe-bind
acknowledgement to listen on a non-loopback address. This acknowledgement does not claim that
local actor headers are enterprise authentication.

The local CLI calls shared `DesignCaseService` and `CandidatePlanningService` application operations. The interface maps arguments and output only; application services own orchestration through intake, catalogue, target-profile, and workspace ports. The deterministic compiler maps explicit facts, records inferences and unknowns with scalar provenance, validates catalogue eligibility, expands provider-neutral patterns, rejects hard-constraint failures and unknowns, estimates visible objective ranges, computes the Pareto frontier, evaluates the public fixture, and compiles a draft typed plan.

## Local persistence and lineage

The file adapter stores one atomic `.oak/manifest.json` pointer and immutable content-addressed objects. A mutation takes the workspace lock, checks expected version and idempotency, validates all new artifacts, writes objects, then atomically replaces the manifest. A crash before replacement can leave only unreferenced objects; it cannot partially publish a case.

Every successful mutation creates a successor `DesignCase`, successor intent where applicable, and an audit event linked to the previous event digest. Raw source bytes remain a separate `brief_source` object and the source record marks them untrusted. Catalogue, candidate, evaluation, decision, assurance, bundle, runner-plan, and review artifacts are immutable and content-addressed. Export and import validate manifest references, artifact identity, schemas, sizes, and digests before an imported workspace becomes visible.

The PostgreSQL adapter implements the same repository port. One row-locked metadata
transaction inserts immutable object/case versions, advances the case head, appends the
transition and idempotency record, and enqueues one stable-sequence outbox event. Artifact
bytes use a bounded digest-verified local object store; unreferenced bytes after a failed
metadata transaction do not authorize or publish state. Tenant, environment, and workspace
scope participates in database keys and every query.

Outbox delivery is at least once. Leased delivery can repeat after expiry; consumer receipts
deduplicate by stable event ID, and projection positions expose indexed-through lag. These
projections are rebuildable and never authorize transitions. Durable Operations similarly
use bounded attempts, deterministic backoff, leases, checkpoints, cooperative cancellation,
and explicit terminal failure. `oak-worker` may run only the three compiler/evaluation
application operations and has no runner authority.

The Alembic `0001_sprint3_baseline` revision starts from an empty database. Storage migration
rollback is restore-forward from backup; no destructive down-migration is supplied. Canonical
file/PostgreSQL exports use the same manifest and content-addressed objects.

## Canonical contracts

JSON Schema Draft 2020-12 files in `schemas/` are the external contract authority. Runtime wrappers preserve the parsed JSON data model and validate through a registry containing every canonical schema. Tests prove that public YAML examples validate and round-trip without semantic drift.

## Compiler and runner boundary

The compiler bundles synthetic catalogue data and works offline. It emits a byte-stable semantic manifest plus a schema-valid deployment bundle and `draft` runner plan. Explicit target-profile invocation data is tenant-bound and checked against the selected candidate's platform, resource, and read-only operation requirements; the control-plane host is never inferred as the target. The plan contains only inventory, validation, rendering, planning, and verification operation kinds; recursive parameter validation rejects command/shell/executable fields. There is no runner dispatch or target connection.

Signing, approvals, lease/target verification, runner execution, and target access remain deferred. Later work must preserve immutable canonical versions, deterministic output, shared application services, and separate authority gates.
