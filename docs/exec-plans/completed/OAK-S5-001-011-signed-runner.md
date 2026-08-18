<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S5-001–011: Signed typed runner and GitOps boundary

## Status

- Owner/agent: Claude
- Started: 2026-08-18
- Last updated: 2026-08-18 21:40 BST
- State: done
- Claimed tasks: `OAK-S5-001`–`OAK-S5-011`

## Outcome

With the runner unable to receive inbound connections, the control plane signs the compiled
draft runner plan into an immutable dispatch envelope, records digest/target/action/expiry
bound approvals, and dispatches a lease through an outbound-only local mailbox. `oak-runner`
independently verifies protocol version, plan and bundle digests, signature and trust
policy, target fingerprint, lease/nonce/expiry, approvals, adapter identity and
parameter-schema digests, and the permission envelope before any target access. Tampering
one plan byte, changing the target fingerprint, or removing an approval blocks before any
adapter call. The allowed plan dry-runs, applies, and rolls back only the isolated
non-production fixture profile, leaving a hash-chained journal and bounded redacted
evidence, and `oak gitops` renders deterministic branch-ready files with a change proposal
and patch description that never promote automatically.

## Context and invariants

Sprint 4 is merged at `588ead3`. `oak.runner` is an empty trust-domain package and
`oak-runner` is a placeholder exiting 69. The compiler already emits a draft immutable
`RunnerPlan` whose schema anticipates Sprint 5 (status through `manual_recovery_required`,
apply/rollback/destroy kinds, lease policy `{300s, 30s heartbeat, require_nonce}`, evidence
policy with redaction, `supply_chain` binding plan digest + signature ref + verification
policy ref), plus `signature.pending` and `verification-policy` review artifacts and an
`approvals` PostgreSQL table that no code reads yet.

Governing requirements: `OAK-FR-CTL-005`–`009`, `OAK-FR-DEP-001`–`008`,
`OAK-NFR-SEC-001`–`006`, `OAK-NFR-REL-001`–`002`; ADR-0015 (typed runner operations),
ADR-0002, ADR-0008, ADR-0013; threat model TM-01, TM-06–09, TM-16, TM-18; the
security-invariants "Runner execution" checklist; and the skills.md "Runner safety" and
"Deployment adapter" recipes with Security review as the reviewing lens.

Hard invariants:

- The runner executes only typed operations from a schema-valid plan; no `command`,
  `shell`, `executable`, or `argv` field may appear in any canonical document; adapters map
  validated typed fields to a fixed allowlisted executable and argument vector with
  `shell=False`, a sanitized environment, and output/time bounds.
- Plans and apply authorizations are separately signed objects; a plan alone never
  authorizes apply, and no development shortcut can reach a target unsigned.
- The runner trusts nothing because it came from the control plane: every check runs
  runner-side before any target connection, and unknown kinds/adapters/schemas fail closed.
- Compiled canonical artifacts stay immutable: signing wraps the draft plan's digest in a
  separate envelope artifact rather than editing the plan.
- The runner has no control-plane database access, no inbound port, and a separate
  identity; proposal, approval, signing, and mutation never collapse into one actor, and no
  model output authorizes anything.
- Secrets appear only as references; the fixture profile allows none, and the verifier
  enforces the target's allowed-reference set before resolution would ever occur.

## Scope

### In

- Ed25519 signing through a new `SigningPort` with a local key-lifecycle adapter
  (`cryptography` as a reviewed locked dependency), explicit development-mode trust marker,
  and an `oak keys` CLI for init/inspect.
- A signed immutable dispatch envelope over the draft plan digest, a signed approval
  document bound to plan/bundle digest, target identity, environment, action, actor, nonce,
  and expiry, with revocation; `oak sign`, `oak approve`, `oak revoke-approval` CLI.
- Versioned runner protocol messages (register/inventory, poll/lease, progress, evidence,
  heartbeat, completion) with protocol version, identities, correlation/operation IDs,
  nonces, and expiry; an outbound-only filesystem mailbox transport for Community local
  mode (the runner reads and writes only its mailbox, journal, and target).
- Runner-side plan verifier implementing the security-invariants checklist before target
  access; hash-chained append-only journal with before/after checkpoints, crash resume,
  cooperative cancellation, and `manual_recovery_required`.
- Bounded local inventory adapter (platform/CPU/RAM/storage capabilities via standard
  APIs; no file scraping or secret access) producing a sanitized target fingerprint digest.
- Local container adapter: typed render/plan/verify plus isolated reversible apply
  (digest-pinned `docker create --network=none` of a labelled, never-started container) and
  rollback/destroy of exactly the journaled name, only for an explicit non-production
  target profile; allowlisted argv, injected executor for hermetic tests.
- Target-profile schema evolution to `0.2.0` (additive): a `non-production-local` status
  whose mutation permission requires development/validation environment and an explicit
  acknowledgement field; the `0.1.0` fixture stays valid and read-only.
- Dispatch and ingestion: `oak dispatch` (issues the signed lease envelope; requires
  signature and approvals per the verification policy), `oak-runner run-once` /
  `--poll`, `oak runner-status` ingesting evidence/completion with delivery
  never treated as success.
- Deterministic GitOps output: `oak gitops` renders branch-ready normalized files, a
  schema-valid change proposal, and a patch/PR description; promotion remains manual.
- Adversarial suite: tampered/forged/stale/replayed/revoked/wrong-target envelopes and
  approvals, command/path/environment injection attempts, executable substitution, output
  flooding, lease loss, crash resume, rollback failure to `manual_recovery_required`, and
  secret/environment redaction.
- New canonical schemas (`approval`, `runner-envelope`, `runner-message`,
  `runner-evidence`) registered with conformance examples; docs, STATUS, CHANGELOG,
  dependency review updates; `oak-runner` entrypoint repointed with the placeholder test
  replaced.

### Out

- Any production/customer target, enterprise authentication, remote/networked runner
  transport (the protocol is transport-neutral; HTTP polling arrives with Sprint 7
  interface parity), Kubernetes or second deployment adapter (Sprint 6), OPA/policy packs
  (Sprint 6), real secret resolution (the fixture forbids references), Git provider PR
  creation (optional adapter later), `.github` CI wiring (still explicitly deferred), and
  the PostgreSQL `approvals` table wiring (approvals are canonical signed artifacts in
  Community local mode; the table remains for the later deployment controller).

## Contract and data changes

New additive canonical schemas: `approval.schema.json`, `runner-envelope.schema.json`
(signed dispatch envelope + lease), `runner-message.schema.json` (protocol messages), and
`runner-evidence.schema.json` (journaled evidence/completion). Target profile evolves
additively to `0.2.0` as above. The runner-plan and deployment-bundle schemas are
unchanged; compiled artifacts remain byte-stable. No database schema change. No REST
surface change (CLI-first; Sprint 7 owns interface parity), so OpenAPI is untouched.

## Milestones

1. **Signing and trust (`OAK-S5-004`, part `OAK-S5-002`)** — `cryptography` dependency
   review and lock; `SigningPort` + local Ed25519 adapter with 0600 key files, explicit
   `development` trust marker, and deterministic canonical-bytes signing; `oak keys`;
   envelope/approval schemas; `oak sign` producing the signed envelope artifact.
   Proof: signing round-trips; a flipped byte fails verification; unsigned dispatch is
   impossible because dispatch requires the envelope.
2. **Runner core (`OAK-S5-001`, `OAK-S5-002`, `OAK-S5-003`)** — protocol messages, the
   full pre-target verifier, hash-chained journal with resume/cancel/manual-recovery.
   Proof: unit suites over every verifier denial and journal transition; the journal
   detects tampering of any prior entry.
3. **Approvals (`OAK-S5-008`)** — signed approval artifacts with revocation and the CLI;
   verifier consumes approvals for mutating kinds only.
   Proof: forged/stale/wrong-target/replayed/revoked all denied before adapter calls.
4. **Adapters (`OAK-S5-005`, `OAK-S5-006`)** — inventory + container adapters with
   parameter schemas and digests, allowlisted argv, injected executor.
   Proof: fingerprint is stable and secret-free; argv construction rejects every injection
   fixture; apply/rollback round-trip against real Docker in a gated integration test.
5. **Dispatch and lifecycle (`OAK-S5-007`, `OAK-S5-009`)** — mailbox dispatch, lease
   issuance, runner execution loop, evidence/completion ingestion, rollback/destroy,
   `manual_recovery_required`.
   Proof: the exit journey end-to-end; delivery-versus-success separation; crash resume.
6. **GitOps, adversarial closure (`OAK-S5-010`, `OAK-S5-011`)** — `oak gitops`,
   the full adversarial suite, exit demonstration test, docs/status updates, entrypoint
   repoint.
   Proof: byte-identical GitOps output across clean runs; complete adversarial matrix
   green; `make check` and the Compose journey unchanged.

Rollback for every milestone: revert the branch; compiled canonical artifacts and all
Sprint ≤4 behavior are untouched until the `oak-runner` entrypoint repoint in Milestone 6,
and file mode remains the source of truth.

## Verification

Unit/contract suites for signing, envelope, approval, protocol, verifier, journal, argv
construction, and GitOps determinism; integration suites for the mailbox dispatch journey,
Docker-gated apply/rollback, crash resume, and the adversarial matrix; the E2E exit
demonstration; schema conformance for the four new schemas; `make check`, `make audit`,
`make sbom`; documentation policy scan and `.github`-unchanged check.

## Security, privacy and authority review

The signer, approver, dispatcher, and runner are separate identities; Community local mode
labels every trust anchor `development` and never claims production assurance. All
verification is fail-closed and runner-side. Evidence is category-allowlisted, size-capped,
and redacted (secret/credential/environment patterns) before leaving the runner; journals
are append-only and hash-chained. Argv never includes plan-supplied executables; the
executable allowlist is code, not data. The mailbox contains only signed canonical
documents; a tampered mailbox file is an expected adversarial case and is denied. No
canonical or runner document may contain `command`/`shell`/`executable`/`argv` fields.

## Operational and rollback plan

Keys live under a local trust directory (0600, gitignored) created by `oak keys init`;
losing them invalidates outstanding envelopes/approvals, which are re-signable from
canonical artifacts. The mailbox and journal are plain directories; recovery is re-dispatch
after inspection, and `manual_recovery_required` states demand explicit operator action
(`oak-runner resume` re-verifies everything first). Docker mutations are labelled,
never-started containers removable by name; `docker compose` behavior is unchanged.

## Progress

- [x] 2026-08-18 18:20 BST Fast-forwarded `main` to `588ead3` (PR #6 merged), created
  `claude/sprint-5-signed-runner`, gathered governance/contract/code-seam context, and
  authored this plan; claimed `OAK-S5-001`–`011`.
- [x] 2026-08-18 Milestone 1 complete. Added `cryptography` as a reviewed locked dependency,
  the `SigningPort` with a local Ed25519 adapter (0600 per-role keys, `development` trust
  marker, key-id derived from the public key), verification primitives in `oak.contracts`
  so signer and verifier stay separate, and the `plan-signature`, `approval`,
  `runner-envelope`, and `runner-message` schemas with signed examples plus a shared
  `signatureBlock` and additive audit event types.
- [x] 2026-08-18 Milestone 2 complete. Added versioned protocol messages, the fail-closed
  pre-target verifier covering every security-invariant check, and the hash-chained journal
  with interrupted-operation resume and sticky `manual_recovery_required`.
- [x] 2026-08-18 Milestone 3 complete. Approvals are signed canonical artifacts bound to
  action, plan and bundle digest, target identity and fingerprint, actor, nonce, and expiry;
  revocation re-signs the approval and publishes a mailbox notice the runner honors.
- [x] 2026-08-18 Milestone 4 complete. Added the bounded inventory collector and the
  container fixture adapter constructing fixed allowlisted argv with `shell=False`, a
  sanitized environment, and bounded output; target-profile `0.2.0` gates mutation behind an
  explicit acknowledgement and the compiler emits typed apply/rollback/destroy operations.
- [x] 2026-08-18 Milestone 5 complete. Dispatch issues signed lease envelopes with
  content-addressed attachments through the outbound-only mailbox; the runner executes
  verified kinds with journaled side effects, category-filtered redacted evidence, and a
  signed completion; ingestion advances the case only on a verified completion.
- [x] 2026-08-18 Milestone 6 complete. `oak gitops` renders byte-identical branch-ready
  manifests with a patch description that promotes nothing; the adversarial matrix, contract
  invariants, and the exit demonstration all pass; docs, dependency review, and the runner
  guide are updated and the `oak-runner` entrypoint replaces the placeholder.

## Decisions

- 2026-08-18 Sign an immutable envelope over the draft plan digest instead of mutating the
  compiled plan: canonical artifacts stay byte-stable and `supply_chain.plan_digest` is the
  binding the runner verifies.
- 2026-08-18 Use Ed25519 via the `cryptography` package (Apache-2.0/BSD dual licence,
  maintained by the PyCA project) behind a `SigningPort`; the runner imports only the
  verify primitive, keeping signer and verifier identities separate.
- 2026-08-18 Community local dispatch is an outbound-only filesystem mailbox: the runner
  never listens, shares no database, and the protocol messages are transport-neutral so
  Sprint 7 can add a polling HTTP transport without changing verification.
- 2026-08-18 Approvals are signed canonical artifacts in Community local mode; the
  Sprint 3 `approvals` table stays unused until a deployment controller exists.
- 2026-08-18 The container adapter's apply is `docker create --network=none` of a
  digest-pinned, labelled, never-started container: a real, observable, fully reversible
  local mutation with no code execution inside the container.

## Post-implementation audit

A multi-agent adversarial audit ran against the completed sprint: four security lenses
(signing/trust, verifier completeness, adapter execution safety, control-plane state)
produced 35 candidate findings, each independently refuted or confirmed by a separate
agent. Ten survived refutation. Six were fixed in this sprint; four are recorded below as
known limitations.

Fixed:

- **Signature forgery through unauthenticated `key_id` (critical).** Verification used the
  public key embedded in the document under inspection, while the trust check compared that
  document's self-asserted `key_id` against the anchors. An attacker could sign with their
  own key, embed their own public key, and claim a trusted identifier; both checks passed.
  Trust anchors now hold public keys, verification uses the pinned key, and a key
  identifier must derive from the key it names. Reproduced as an exploit before the fix and
  covered by `tests/unit/test_runner_trust.py`.
- **Approved image digest bypass (critical).** The container adapter used a digest embedded
  in `image_reference` in preference to the approved `image_digest`, so an approval for one
  image could run another. References carrying their own digest are now refused.
- **Unverified operations could execute (high).** Verification kept one operation per kind
  while execution re-derived its work list from the raw plan, so a duplicate kind would
  execute unverified. Duplicate kinds are now rejected and execution consumes exactly the
  verified tuple.
- **Unenrolled runner completions (high).** Ingestion accepted any self-consistently signed
  message. Messages must now carry a key identifier that derives from their key and
  reference a lease this control plane actually dispatched.
- **Mailbox wedging and path traversal (medium).** A malformed approval identifier raised
  `IndexError` outside the fail-closed handler, and mailbox bookkeeping built paths from the
  envelope's self-declared id on the denial path. Identifiers are validated, and the on-disk
  directory name is authoritative.
- **Missing plan and approval scoping (medium).** Plan expiry and status were never checked,
  and approvals were not bound to the dispatch's tenant, environment, or case.

Known limitations, deliberately not fixed in this sprint:

- Revocation notices are unsigned and travel over a fail-open channel: deleting a notice
  from the mailbox restores the approval's usability. Signing revocations and treating an
  unreadable revocation directory as fail-closed belongs with the enterprise transport.
- The runner's trust-anchor directory currently defaults to the same directory that holds
  the control plane's private keys. They are separate concerns and should be separate paths
  once the runner runs on a different host; only public `*.identity.json` files are read.
- `default_executor` resolves `docker` through the inherited `PATH`; the hardened `os.defpath`
  applies to the child environment only.
- The image digest is not verified against what the container runtime actually resolved, and
  no registry allowlist is enforced.
- The signature block's own fields (`role`, `trust_level`) are outside the signed payload.
  Anchor-based verification now makes a mismatch unusable, but the fields remain claims.

## Discoveries and follow-ups

- `tests/e2e/test_cli.py::test_unimplemented_runner_fails_honestly` was replaced by tests
  asserting the real runner refuses to act without its environment and exposes only
  verification-bound commands.
- `docs/development.md`, the README limits, `docs/architecture.md`, and the STATUS.md safety
  boundary were revised rather than left contradicting the new behavior.
- The `approvals` PostgreSQL table remains unused: Community approvals are canonical signed
  artifacts. Wiring the table belongs to a later deployment controller.
- Signing, approval, dispatch, and ingestion are CLI-only. Exposing them through `/v1` and
  the web workspace is deliberately deferred to Sprint 7 interface parity.
