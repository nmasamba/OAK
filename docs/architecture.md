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

The web workspace is a routed React application that consumes `/v1` through the generated
typed client and the same-origin nginx/Vite proxies; it adds no transport of its own and no
CORS relaxation. Following ADR-0014, the browser renders server-returned case state,
questions, candidates, decisions, and denials — it never computes lifecycle transitions,
and a stale `If-Match` surfaces as a visible conflict-recovery path. The additive
`GET /v1/design-cases` directory reads the authoritative case head/version tables, and
`GET /v1/design-cases/{id}/audit` reads the immutable `audit_event` artifacts through the
same repository port in both persistence adapters; neither read surface grants transition
authority.

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

## Signing, approval, and the runner trust domain

Signing never edits a compiled artifact. The control plane signs an immutable
`plan-signature` document that binds the plan digest, bundle digest, target identity, and
locally recomputed target fingerprint; approvals are separate signed documents bound to one
action, digest pair, target, actor, nonce, and expiry, and revocation publishes a notice the
runner reads. A dispatch envelope carries the lease, the requested operation kinds, and
content-addressed references to plan, bundle, policy, signature, and approvals. Signer and
approver hold distinct key roles, and the runner enforces that their identities differ.

`oak-runner` is a separate trust domain: it imports only `oak.contracts` and `oak.domain`,
holds no database credential, opens no listening socket, and reads its mailbox, trust
anchors, and own copy of the target profile. Before any target access it independently
verifies protocol version, schema validity, every attachment digest, all signatures against
pinned anchors, tenant/environment/target identity and fingerprint, lease window and nonce
replay, separation of duties, adapter identity and parameter-schema digests against a
code-level allowlist, permission envelopes and secret-reference bounds, and a current
unrevoked approval for the action class. Every check fails closed, and unknown kinds,
adapters, or schemas are refused rather than skipped.

Execution brackets each side effect with hash-chained journal entries, so an interrupted
run resumes into `manual_recovery_required` rather than guessing. Adapters map validated
typed fields to a fixed allowlisted executable and argument vector with no shell, a
sanitized environment, and bounded output; the executable allowlist is code, never plan
data. Evidence is category-filtered, size-capped, and redacted before it leaves the runner.
Delivery of a dispatch is never success: only a signed, verified runner completion advances
the case.

Enterprise authentication, remote runner transport, production targets, real secret
resolution, and Git provider promotion remain deferred. Later work must preserve immutable
canonical versions, deterministic output, shared application services, and separate
authority gates.
