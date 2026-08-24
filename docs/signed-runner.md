<!-- SPDX-License-Identifier: Apache-2.0 -->

# Signed typed runner

Sprint 5 adds local signing, approvals, outbound-only dispatch, and a separate runner trust
domain. Everything here is development-grade: keys are labelled `development`, the only
reachable target is an isolated non-production fixture, and the sole permitted mutation is
creating and removing one network-isolated, never-started container.

## Authority separation

Four authorities stay distinct and no step may be collapsed into another:

| Authority | Holder | Produces |
|---|---|---|
| Compilation | `oak plan` | draft `RunnerPlan`, `DeploymentBundle` |
| Signing | `plan-signer` key | `plan-signature`, dispatch envelope |
| Approval | `approver` key | per-action `approval` bound to digests, target, expiry |
| Execution | `oak-runner` identity | journal, evidence, signed completion |

A plan alone never authorizes execution; an approval alone never dispatches. A mutating
operation needs a current approval for exactly that action, and the runner refuses when the
approval and envelope signatures share one identity.

## Local journey

```bash
oak keys init                       # create the development plan-signer, approver and extension-steward keys
oak sign                            # bind the compiled plan digest into a signed document
oak approve dry_run                 # read-only authorization; add apply/rollback as needed
oak dispatch inventory validate render plan verify
```

Dispatch writes a signed envelope and content-addressed attachments to the mailbox
(`OAK_DISPATCH_MAILBOX`, default `~/.oak/mailbox`). The runner is started separately:

```bash
export OAK_RUNNER_MAILBOX="$HOME/.oak/mailbox"
export OAK_RUNNER_TRUST_ANCHORS="$HOME/.oak/trust"
export OAK_RUNNER_TARGET_PROFILE=examples/targets/local-fixture.yaml
oak-runner run-once
oak-runner status                   # journal integrity and recovery state
```

Then ingest the result; delivery is never treated as success:

```bash
oak ingest --output json
```

`oak revoke-approval apply --reason "..."` publishes a revocation the runner honors on its
next verification pass, and `oak gitops --output ./gitops` renders deterministic
branch-ready manifests with a patch description that promotes nothing automatically.

## What the runner checks before touching a target

In this order, and any failure denies the dispatch before an adapter is constructed:

1. **Protocol and schema.** The envelope's `protocol_version` must be supported, and the
   envelope, plan, deployment bundle and plan signature must each be schema-valid.
2. **Attachment digests** for the plan, bundle, plan signature, verification policy and
   every approval, each against the reference carried in the envelope.
3. **Signatures**, verified against **pinned trust anchors** — never a key embedded in the
   document being checked.
4. **Identity**: tenant, environment, target identity, and a target fingerprint recomputed
   locally rather than taken from the envelope. The plan must be in a dispatchable state
   (`OAK-RUNNER-PLAN-STATE`) and not expired (`OAK-RUNNER-PLAN-EXPIRED`).
5. **Lease**: validity window, expiry, policy bound on lease duration, and nonce replay.
6. **Separation of duties** between the signing and approving identities.
7. **Operations**: adapter identity and parameter-schema digest against the code-level
   allowlist; typed parameters against the adapter schema with execution fields rejected
   recursively; empty secret references within the target allowance; empty network
   destinations.
8. **Approval** for any mutating kind — current, unrevoked, and bound to the digest,
   target, action class and expiry.
9. **Verification policy.** The attachment is schema-validated, its clauses are read from
   `content`, and a policy that contradicts the signing or approval requirements is
   refused. Two clauses it carries — `mutation_allowed` and `allowed_operation_kinds` —
   are **not** enforced; see `RR-032` in
   [security/residual-risk.md](security/residual-risk.md) for why, and what would have to
   change first.

## Mutation profile

`examples/targets/local-mutation-fixture.yaml` is a `0.2.0` profile that opts in explicitly
with `status: non-production-local`, `permissions.mutation_allowed: true`, and an
`execution.mutation_acknowledgement` of `isolated-non-production-fixture-only`. Compilation
then emits typed `apply`, `rollback`, and `destroy` operations whose failure actions are
`rollback` and `manual_recovery`. The container adapter runs
`docker create --network=none --label oak.fixture=true --name <name> <image>@<digest>`;
the container is never started, and rollback removes exactly the journaled name.

## Reading `oak-runner status`

`status` prints one JSON object per journal under `$OAK_RUNNER_HOME/journals`:

```json
{
  "journals": [
    {
      "dispatch": "d0001",
      "entries": 7,
      "chain": "verified",
      "manual_recovery_required": false
    }
  ]
}
```

`chain` has three values, and the difference between the last two matters:

| Value | Meaning |
|---|---|
| `verified` | The hash chain is intact end to end |
| `tampered` | The chain is readable but does not verify — an entry was altered, removed or reordered |
| `unreadable` | A journal line could not be parsed at all: truncated, corrupt or the wrong shape. Reported rather than crashing the command, and treated as requiring manual recovery |

**`run-once` reports whether the runner ran, not whether anything succeeded.** It exits `0`
when every dispatch in the mailbox was *denied*, because denying a dispatch is the runner
working correctly. Denials go to stderr as `denied <dispatch>: <reason>` and are published
back to the mailbox as completion messages with `"outcome": "denied"`. To find out what
actually happened, read those messages or the journal — not the exit status. A non-zero
exit means the runner itself could not run: `64` for a missing required variable, `70` for
a configuration or verification refusal that stopped it before processing.

## Recovery

Journals are append-only and hash-chained under `OAK_RUNNER_HOME/journals`. A run that finds
an interrupted side effect refuses to continue and records `manual_recovery_required`;
resolve it by inspecting the journal and the fixture container, then re-dispatch. Losing the
trust directory invalidates outstanding envelopes and approvals, which are re-signable from
the unchanged canonical artifacts.
