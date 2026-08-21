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

Protocol version and schema validity; every attachment digest against the envelope
references; envelope, plan-signature, and approval signatures against pinned trust anchors;
tenant, environment, target identity, and a locally recomputed target fingerprint; lease
validity window, policy bound, and nonce replay; separation of duties; adapter identity and
parameter-schema digest against the code-level allowlist; typed parameters against the
adapter schema with execution fields rejected recursively; empty secret references within
the target allowance; empty network destinations; and a current, unrevoked, digest and
target bound approval for the action class. Any failure denies the dispatch before an
adapter is constructed.

## Mutation profile

`examples/targets/local-mutation-fixture.yaml` is a `0.2.0` profile that opts in explicitly
with `status: non-production-local`, `permissions.mutation_allowed: true`, and an
`execution.mutation_acknowledgement` of `isolated-non-production-fixture-only`. Compilation
then emits typed `apply`, `rollback`, and `destroy` operations whose failure actions are
`rollback` and `manual_recovery`. The container adapter runs
`docker create --network=none --label oak.fixture=true --name <name> <image>@<digest>`;
the container is never started, and rollback removes exactly the journaled name.

## Recovery

Journals are append-only and hash-chained under `OAK_RUNNER_HOME/journals`. A run that finds
an interrupted side effect refuses to continue and records `manual_recovery_required`;
resolve it by inspecting the journal and the fixture container, then re-dispatch. Losing the
trust directory invalidates outstanding envelopes and approvals, which are re-signable from
the unchanged canonical artifacts.
