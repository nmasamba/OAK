<!-- SPDX-License-Identifier: Apache-2.0 -->

# Local DesignCase workspace

The local workspace is the Sprint 1 reference implementation for offline design intake and confirmation. It is intended for development, demonstrations, and portable public or synthetic cases. It does not approve a deployment or contact a target system.

## State and transaction model

`oak init` creates `.oak/manifest.json` and `.oak/objects/sha256/` with owner-only permissions. The manifest indexes immutable objects by identifier, version, media type, kind, size, and SHA-256 digest. It also points to the current case, lists its append-only audit lineage, and records normalized input digests for idempotent retries.

A mutation holds `.oak/workspace.lock`, validates its expected case version and retry key, writes new immutable objects, and atomically replaces the manifest. The manifest is the publication boundary. Unreferenced objects left by an interrupted operation have no authority and are omitted from export.

## Source and interpretation boundary

Brief files are untrusted input. Raw normalized bytes are stored as a `brief_source`; a separate `source_record` contains bounded metadata and its digest reference. The deterministic interpreter copies explicit values, labels deterministic inferences, retains unknowns, detects stable contradictions or infeasible claims, and attaches provenance to every scalar intent value.

An optional model adapter can return only a bounded, schema-validated interpretation proposal. When the operator asks for Online AI or Local AI — never by default — the proposal is merged inside the same `interpret` commit under fixed rules: only the typed `spec` paths listed in `oak.contracts.intent_paths` are admissible, values are bounded, explicit brief values win, every applied claim is re-validated against the intent schema, and every value the model contributed carries `model_proposed` provenance with the proposal identifier as evidence. Each section the model touched gains a `question.model.<section>` confirmation question whatever confidence the model reported, so a model-proposed value never reaches candidates unconfirmed. Refused claims become `OAK-INT-PROPOSAL-REJECTED` findings, never silence. The proposal is stored as an `interpretation_proposal` artifact, the intent references it under `oak.community/interpretation_proposal_ref`, and the audit event records which interpreter ran and the proposal digest — never a prompt, a response body or a credential. A workspace with no model configured produces exactly the documents it produced before; provider unavailability commits nothing.

## Confirmation and retries

`oak questions` returns the current case's ranked questions, five per round; any further open questions are counted, and a question whose value a model proposed is annotated with the model's confidence and rationale. `oak confirm` accepts one to five typed decisions: `confirm`, `correct`, `reject`, or `accept_risk`. Each accepted command names the local actor, records rationale and a value digest, creates successor intent and case versions, and appends one linked audit event. Missing answers never imply confirmation, and a case stays in `needs_confirmation` while any model-proposed value is unconfirmed. On a section question (`/spec/<section>`), `confirm` and `accept_risk` take the section object as it stands, `correct` replaces it, and `reject` removes the model-proposed values while keeping what the brief stated.

If no retry key is supplied, the CLI derives one from the operation and normalized input digest. Repeating identical input returns the first result. Reusing an explicit key with different input fails with `OAK-IDEMPOTENCY-CONFLICT`; a stale expected version fails with `OAK-EXPECTED-VERSION`.

## Export, import, and recovery

`oak export --output DIRECTORY` requires a new destination and copies only indexed objects after validating their schemas, sizes, identities, and digests. `oak import EXPORT --directory WORKSPACE` requires an uninitialized workspace and validates the full export before atomically publishing `.oak`.

Import never overwrites an initialized workspace. For local recovery, retain or copy the last valid export and import it into a new directory. Do not hand-edit a manifest to move its current pointer: that would bypass lineage and reference checks. Deleting `.oak` removes all local state and is irreversible unless an export exists.

## Current limits

The adapter supports one current `DesignCase` per workspace and one local tenant label. It is not a multi-user server, an authorization service, or a production metadata store. This offline design workflow performs no approval, signing, runner dispatch, secret resolution, subprocess execution, or target mutation; its only network calls are the optional, explicitly chosen model request during `interpret` (Online AI: Hugging Face; Local AI: a loopback server) and the token verification and catalogue refresh that may precede it, and the default `--interpreter deterministic` makes none.
