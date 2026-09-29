<!-- SPDX-License-Identifier: Apache-2.0 -->

# Signed typed runner

Sprint 5 adds local signing, approvals, outbound-only dispatch, and a separate runner trust
domain. Everything here is development-grade: keys are labelled `development`, and the only
reachable target is an isolated non-production local profile. The sole permitted mutation
installs the selected candidate's topology on the runner's local Docker daemon, one
network-isolated container per node, and removes it again. Whether those containers are
ever started is the target profile's acknowledgement (see
[Mutation profiles](#mutation-profiles)).

## Authority separation

Four authorities stay distinct and no step may be collapsed into another:

| Authority | Holder | Produces |
|---|---|---|
| Compilation | `oak plan` | draft `RunnerPlan`, `DeploymentBundle` |
| Signing | `plan-signer` key | `plan-signature`, dispatch envelope |
| Approval | `approver` key | per-action `approval` bound to digests, target, expiry |
| Execution | `oak-runner` identity | journal, evidence, signed completion |

A plan alone never authorizes execution; an approval alone never dispatches. A mutating
operation needs a current approval for exactly that action. `apply` also needs a current
`architecture` approval, recorded first, which names the architecture decision and the
digest of what `apply` installs; `rollback` and `destroy` never need it. The runner refuses
when the approval and envelope signatures share one identity.

## Local journey

```bash
oak keys init                       # create the development plan-signer, approver and extension-steward keys
oak sign                            # bind the compiled plan digest into a signed document
oak approve dry_run                 # read-only authorization; an install needs more (below)
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

`oak revoke-approval apply --reason "..."` re-signs the approval as revoked and publishes
a **signed revocation notice** plus a **signed revocation manifest** — an inventory of
the complete notice set by canonical digest, with a strictly monotonic sequence — into
the mailbox's `revocations/` directory; the runner honors them on its next verification
pass. The channel fails closed: every notice and the manifest must be schema-valid and
verify against a pinned `approver` anchor, the notice set must match the manifest
exactly, the sequence may never regress below the high-water mark the runner records in
its own home, and a missing manifest on a dispatched mailbox, a missing directory, an
unreadable, oversized or malformed entry, or anything unexpected denies every pending
dispatch (`OAK-RUNNER-REVOCATION`). Deleting a notice — one file or the whole set — no
longer restores a revoked approval. `oak … dispatch` establishes an empty signed manifest
with the first dispatch, so from then on "no manifest" and "no notices" are
distinguishable states. The runner's consumed-nonce replay ledger likewise
fails closed: an unreadable ledger refuses (`OAK-RUNNER-REPLAY`) rather than reading as
empty and being silently rewritten. `oak gitops --output ./gitops` renders deterministic
branch-ready manifests with a patch description that promotes nothing automatically.

### Installing, testing and observing

An install needs a plan compiled against a mutation profile (`oak plan <candidate> --target
examples/targets/local-started-fixture.yaml`, say; see [Mutation profiles](#mutation-profiles))
and a runner whose `OAK_RUNNER_TARGET_PROFILE` is that same profile. `oak architecture`
prints the selected architecture and, once such a plan is compiled, the image each node
would run and whether the two approvals exist. It writes nothing, so a user who wants only
the design can stop there. After `oak keys init` and `oak sign` as above:

```bash
oak architecture                    # read-only; also works in remote mode
oak approve architecture            # approves the selected architecture as compiled; installs nothing
oak approve apply                   # refused without a current architecture approval (OAK-APPROVAL-ARCHITECTURE)
oak dispatch apply                  # attaches both approvals
oak-runner run-once
oak ingest                          # a successful apply moves the case to deployed
oak observe                         # local-only; records an observation_record, case moves to observing
oak approve rollback
oak dispatch rollback               # then run the runner and ingest again
```

`oak observe` reads only runner completions that ingest has already accepted for the case.
It records four measures, each with its sample size: install success, idempotent re-apply
and rollback recovery (`EV-DEP-01`, `EV-DEP-02`, `EV-DEP-03`), and the smoke test. None of
them satisfies a gate. It adds one calibration row per candidate objective and contract
metric, with the prediction beside the observed value or `unknown` and a reason code. Today
every row is `unknown`, because no workload runs. Startup time and memory are recorded as
measurements with no prediction to compare. The record says whether
`evidence.observed-calibration` is satisfied and what is missing. It proposes nothing and
promotes nothing. Once a case is `deployed` or `observing`, only `rollback` and `destroy`
approvals can be recorded (`OAK-APPROVAL-STATE`).

## What the runner checks before touching a target

In this order, and any failure denies the dispatch before an adapter is constructed:

0. **Revocation set.** Before the envelope is read, the signed revocation manifest is
   schema-validated and anchor-verified, its sequence checked against the high-water
   mark the runner records in its own home, and the notices on disk matched to its
   inventory both ways by canonical digest; any failure — including a missing manifest
   on a dispatched mailbox — denies every pending dispatch (`OAK-RUNNER-REVOCATION`).
1. **Protocol and schema.** The envelope's `protocol_version` must be supported, and the
   envelope, plan, deployment bundle and plan signature must each be schema-valid.
2. **Attachment digests** for the plan, bundle, plan signature, verification policy and
   every approval, each against the reference carried in the envelope.
3. **Signatures**, verified against **pinned trust anchors** — never a key embedded in the
   document being checked.
4. **Identity**: tenant, environment, target identity, and a target fingerprint recomputed
   locally rather than taken from the envelope. The plan must be in a dispatchable state
   (`OAK-RUNNER-PLAN-STATE`) and not expired (`OAK-RUNNER-PLAN-EXPIRED`).
5. **Lease**: validity window, expiry, policy bound on lease duration, and nonce replay —
   with the consumed-nonce ledger failing closed (`OAK-RUNNER-REPLAY`) if it cannot be
   read, never reading as empty.
6. **Separation of duties** between the signing and approving identities.
7. **Verification policy.** The attachment is schema-validated before any operation is
   admitted, its clauses are read from `content`, and a policy that contradicts the
   signing or approval requirements is refused. The compiler derives the policy from the
   target profile, and the runner enforces it: a requested kind outside
   `allowed_operation_kinds`, a mutating kind under `mutation_allowed: false`, or a
   malformed clause denies the dispatch (`OAK-RUNNER-POLICY`) before any adapter exists.
8. **Operations**:
   - adapter identity and parameter-schema digest against the code-level allowlist;
   - typed parameters against the adapter schema, with execution fields rejected
     recursively;
   - for the container adapter, the installation, checked against the runner's own copy of
     the target profile rather than the plan's:
     - it names the case the envelope names and this profile's target
       (`OAK-RUNNER-PARAMETERS`);
     - its `isolation` is the one the profile's `execution.mutation_acknowledgement`
       permits (`OAK-RUNNER-TARGET-CAPABILITY`);
     - every container name is the one derived from case, target and node, and is unique
       (`OAK-RUNNER-PARAMETERS`);
     - each node's image reference and digest are the profile's
       `execution.component_images` entry for that node's component (`OAK-RUNNER-IMAGE`);
     - if the profile declares `execution.allowed_registries`, each image's registry
       resolves inside it (`OAK-RUNNER-REGISTRY`);
   - empty secret references within the target allowance;
   - empty network destinations.
9. **Approval** — current, unrevoked, and bound to the digest, target, action class and
   expiry:
   - each mutating kind requires a target profile that permits mutation and lists that
     kind (`OAK-RUNNER-TARGET-CAPABILITY`), and its own action's approval;
   - `apply` also requires a current `architecture` approval whose recorded decision and
     installation digest equal the dispatched bundle's architecture decision and the
     digest of the plan's `apply` parameters (`OAK-RUNNER-APPROVAL`); `rollback` and
     `destroy` never need it;
   - every other requested kind requires the `dry_run` approval.

Steps 8 and 9 run for each requested kind in turn.

## Mutation profiles

Two shipped `0.2.0` profiles opt in explicitly. Each sets `status: non-production-local`
and `permissions.mutation_allowed: true`, and declares an
`execution.mutation_acknowledgement` and `execution.component_images`: the one
digest-pinned image the operator acknowledges for each catalogue component. Both map every
synthetic component to `docker.io/rancher/mirrored-pause:3.10`, pinned by its index digest.
They differ in what an install does:

- `examples/targets/local-mutation-fixture.yaml` acknowledges
  `isolated-non-production-fixture-only`: its containers are created and never started.
- `examples/targets/local-started-fixture.yaml` acknowledges
  `isolated-non-production-hardened-start`: each container is also started and
  smoke-tested
  ([ADR-0017](adr/architecture/0017-acknowledged-local-installation.md), `RR-043`).

At compile, a component with no acknowledged image fails `preflight.installation`
(`OAK-TARGET-INCOMPATIBLE`); nothing falls back to another image. A profile that still
declares the superseded `container_image_reference`/`container_image_digest` is refused
(`OAK-TARGET-EXECUTION`).

Compilation emits typed `apply`, `rollback`, and `destroy` operations; `apply` fails over to
`rollback`, and the other two to `manual_recovery`. Each carries the same installation: one
container per node of the selected candidate that has a component, named
`oak-fixture-<node slug>-<first 12 hex digits of a SHA-256 over case, target and node>`.

### What the container adapter does

The container adapter is `0.2.0`. For each container, `apply` runs `docker create
--network=none` with the labels `oak.fixture=true`, `oak.case=<case id>` and
`oak.node=<node id>`, and the image `<image>@<digest>`. On a hardened-start profile the
create also carries the fixed flags `--read-only --cap-drop=ALL
--security-opt=no-new-privileges --user=65534:65534 --memory=256m --memory-swap=256m
--cpus=0.5 --pids-limit=64 --restart=no --log-driver=none`. They are code, and part of the
adapter's identity digest. No create carries a volume, an environment variable or a port.

- **Idempotence.** A container that already has the derived name is adopted
  (`already_present`) only if it carries this case's and node's labels. Any other is denied
  with `OAK-RUNNER-FOREIGN` and never touched.
- **Resolved digest.** After creating or adopting each container, the adapter reads back
  what the daemon actually resolved and requires a `RepoDigests` entry carrying the
  approved digest. An inspect failure, an image that cannot prove its identity (no repo
  digest), or a mismatch denies with `OAK-RUNNER-IMAGE`. This closes the time-of-use half
  of TM-08, which the create argv's pin alone cannot.
- **Hardened start and smoke test.** On a hardened-start profile, `apply` then starts each
  container. It must be running (or healthy, when the image declares a health check)
  within 15 seconds, and still running one second later. The adapter records each
  container's startup time and one `docker stats` memory reading. On a fixture-only
  profile the smoke test checks only that each container is `created`. A failed smoke
  test fails `apply` (`OAK-RUNNER-SMOKE-TEST`).
- **Compensation.** A failed `apply` removes exactly the containers it created. One it
  adopted is left for an operator. If that removal fails too, the dispatch ends in
  `manual_recovery_required`.
- **Lease deadline.** The runner does not heartbeat, so once the lease has lapsed `apply`
  refuses to start another side effect (`OAK-RUNNER-LEASE`).
- **Removal.** `rollback` and `destroy` remove only containers carrying this case's
  labels, with `docker rm --force --volumes`, and then inspect each name to prove it is
  gone (`OAK-RUNNER-ROLLBACK` otherwise). A foreign container with the name is denied
  with `OAK-RUNNER-FOREIGN`, never removed.
- **Evidence.** `apply` reports the installation as `status`, the smoke test as
  `test_result`, and the memory readings as `aggregate_metric`. `rollback`, `destroy` and
  compensation report `rollback_result`: whether each container was present before and is
  absent after. Only typed fields parsed from `docker` output reach evidence, never a log, an
  environment or raw output. Evidence outside the plan's allowed categories is dropped,
  the total is capped at 1 MiB, and it is redacted by key and by value, including
  credentials inside URLs (`RR-023`).
- **Isolated Docker client.** Every `docker` command runs with only `PATH` and
  `DOCKER_CONFIG` set, and `DOCKER_CONFIG` is the empty, runner-owned
  `$OAK_RUNNER_HOME/docker-config`. The operator's registry credentials, credential
  helpers and CLI contexts are never used, public images are pulled anonymously, and only
  the default daemon socket is reached (`RR-013`).

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
back to the mailbox as completion messages with `"outcome": "denied"` and a
`denial_code`. A completion of a verified dispatch carries `requested_kinds`,
`applied_kinds` and `failed_kind`, and keeps the evidence of a failed or compensated
operation, so it says on its own whether an install was attempted and which kind failed.
To find out what actually happened, read those messages or the journal — not the exit
status. A non-zero exit means the runner itself could not run: `64` for a missing required
variable, `70` for a configuration or verification refusal that stopped it before
processing.

## Recovery

Journals are append-only and hash-chained under `OAK_RUNNER_HOME/journals`. A run that finds
an interrupted side effect refuses to continue and records `manual_recovery_required`;
resolve it by inspecting the journal and the case's labelled containers
(`docker ps --all --filter label=oak.case=<case id>`), then re-dispatch. Losing the
trust directory invalidates outstanding envelopes and approvals, which are re-signable from
the unchanged canonical artifacts.
