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
digest of what `apply` installs; `rollback` and `destroy` never need it. A native install
([ADR-0019](adr/architecture/0019-native-installation-with-recorded-consent.md)) also needs
a current `native_consent` approval, recorded between the two, which names the consent text
by digest, every control a native installation relaxes, and that same installation digest.
The runner refuses
when the approval and envelope signatures share one identity, judged on the key material:
one public key pinned as both plan signer and approver is refused when the anchors are read.

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

Before the first ingest, enroll the runner: it signs what it reports with its own key,
created in its home on first use, and the control plane believes only enrolled keys. Pin
each runner's public half once (several runners may be enrolled, one file each under the
trust directory's `runners/`):

```bash
oak-runner identity > runner.identity.json      # the public identity; nothing secret
oak keys enroll-runner --identity runner.identity.json
```

Then ingest the result; delivery is never treated as success:

```bash
oak ingest --output json
```

`oak ingest` refuses until a runner is enrolled (`OAK-INGEST-RUNNER-UNENROLLED`). It
believes a message only when an enrolled runner signed it, it answers a lease this case
dispatched, and it reports only kinds that dispatch requested; anything else is listed as
rejected and left in the mailbox. Each message is recorded and only then acknowledged, so
one that cannot be recorded is reported and offered again rather than lost. A denial
names its lease and is recorded too, with its denial code. Only one `oak-runner run-once`
runs per runner home at a time (`OAK-RUNNER-BUSY`).

`oak revoke-approval apply --reason "..."` re-signs the approval as revoked and publishes
a **signed revocation notice** plus a **signed revocation manifest** — an inventory of
the complete notice set by canonical digest, with a strictly monotonic sequence — into
the mailbox's `revocations/` directory; the runner honors them on its next verification
pass. Each new manifest keeps every entry the last signed one listed, whether or not that
notice's file is still in the mailbox, so deleting a notice and waiting for the next
revocation no longer restores the approval: the set stays mismatched, and the runner denies
every dispatch until the notice is restored. A manifest this control plane did not sign is
refused before anything is revoked (`OAK-REVOCATION-CHANNEL`). The channel fails closed: every notice and the manifest must be schema-valid and
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

A native install (`--target examples/targets/local-native-stand-in.yaml`) needs one more
approval, between the two: the consent to what a native installation relaxes. Run without
`--consent`, it prints the consent text and its digest and records nothing; run again with
the digest of the text you read, it records the consent:

```bash
oak approve architecture
oak approve native_consent          # shows the text and its digest; records nothing (OAK-NATIVE-CONSENT)
oak approve native_consent --consent sha256:<the digest it showed>
oak approve apply                   # refused without a current native_consent (OAK-NATIVE-CONSENT)
oak dispatch apply                  # attaches all three approvals
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
     - its installation identity is the one derived from the plan's case reference (id
       and digest), this target and the plan's installation scope — the workspace that
       compiled it — so two workspaces built from the same brief never share one
       (`OAK-RUNNER-PARAMETERS`);
     - every container name is the one derived from that installation identity and the
       node, and is unique (`OAK-RUNNER-PARAMETERS`);
     - each node's image reference and digest are the profile's
       `execution.component_images` entry for that node's component (`OAK-RUNNER-IMAGE`);
     - if the profile declares `execution.allowed_registries`, each image's registry
       resolves inside it (`OAK-RUNNER-REGISTRY`);
   - for the native adapter, the installation, checked against the runner's own copy of
     the target profile in the same way:
     - the case, the target and the derived installation identity, as above
       (`OAK-RUNNER-PARAMETERS`);
     - a profile whose `execution.mutation_acknowledgement` is
       `native-non-production-user-consented` (`OAK-RUNNER-TARGET-CAPABILITY`);
     - the download hosts are exactly the profile's `execution.allowed_download_hosts`, and
       every component's harness kind, artifacts (source, SHA-256, size, format), port and
       health probe are exactly the profile's `execution.native_components` entry for its
       component, fit its harness kind, and use each node and port once
       (`OAK-RUNNER-PARAMETERS`);
     - every `https` artifact is on an acknowledged host (`OAK-RUNNER-NETWORK`);
   - empty secret references within the target allowance;
   - empty network destinations, except a native `apply`, whose destinations must be
     exactly the profile's download hosts (`OAK-RUNNER-NETWORK`).
9. **Approval** — current, unrevoked, and bound to the digest, target, action class and
   expiry:
   - each mutating kind requires a target profile that permits mutation and lists that
     kind (`OAK-RUNNER-TARGET-CAPABILITY`), and its own action's approval;
   - `apply` also requires a current `architecture` approval whose recorded decision and
     installation digest equal the dispatched bundle's architecture decision and the
     digest of the plan's `apply` parameters (`OAK-RUNNER-APPROVAL`); `rollback` and
     `destroy` never need it;
   - a native `apply` also requires a current `native_consent` approval whose binding names
     the plan's consent text, exactly the controls the native adapter relaxes, and the
     digest of the plan's `apply` parameters (`OAK-RUNNER-APPROVAL`); removing a native
     installation never needs it;
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

A third profile, `examples/targets/local-native-stand-in.yaml`, acknowledges
`native-non-production-user-consented`: each component is installed outside any container,
as the user, from the harness kind its `execution.native_components` entry names, and is
stopped once its check passes
([ADR-0019](adr/architecture/0019-native-installation-with-recorded-consent.md), `RR-056`,
`RR-057`). It installs OAK's own stand-in server for every synthetic component, so it
downloads nothing; see "What the native adapter does" below.

At compile, a component with no acknowledged image fails `preflight.installation`
(`OAK-TARGET-INCOMPATIBLE`); nothing falls back to another image. A profile that still
declares the superseded `container_image_reference`/`container_image_digest` is refused
(`OAK-TARGET-EXECUTION`).

Compilation emits typed `apply`, `rollback`, and `destroy` operations; `apply` fails over to
`rollback`, and the other two to `manual_recovery`. Each carries the same installation: one
container per node of the selected candidate that has a component, named
`oak-fixture-<node slug>-<first 12 hex digits of a SHA-256 over the installation identity
and node>`. The installation identity (`installation.<24 hex>`) is derived from the case
version, the target and the workspace that compiled the plan.

### What the container adapter does

The container adapter is `0.2.0`. For each container, `apply` runs `docker create
--network=none` with the labels `oak.fixture=true`, `oak.case=<case id>` and
`oak.node=<node id>`, `oak.installation=<installation id>` and `oak.isolation=<isolation>`,
and the image `<image>@<digest>`. On a hardened-start profile the
create also carries the fixed flags `--read-only --cap-drop=ALL
--security-opt=no-new-privileges --user=65534:65534 --memory=256m --memory-swap=256m
--cpus=0.5 --pids-limit=64 --restart=no --log-driver=none`. They are code, and part of the
adapter's identity digest. No create carries a volume, an environment variable or a port.

- **Idempotence.** A container that already has the derived name is adopted
  (`already_present`) only if it carries this case's, node's and installation's labels. Any
  other is denied with `OAK-RUNNER-FOREIGN` and never touched. One created under a
  different isolation — a never-started container on a profile that now acknowledges
  starting, say — is denied with `OAK-RUNNER-ISOLATION` rather than started as it is.
- **Configuration read-back.** After creating or adopting each container, and before
  anything is started or reported as installed, the adapter reads the container's actual
  configuration back from the daemon. Every container must have no network; one that will
  be started must also have a read-only root, every capability dropped, no new privileges,
  uid 65534, the 256 MiB memory and swap ceiling, the 64-process ceiling and no restart
  policy. Anything else is denied with `OAK-RUNNER-ISOLATION`: a label is a claim, and the
  daemon's own report is the check.
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
- **Lease deadline.** A heartbeat (below) reports; it extends nothing. Once the lease has
  lapsed, `apply` refuses to start another side effect (`OAK-RUNNER-LEASE`).
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
  the default daemon socket is reached (`RR-013`). `docker` is resolved once per run, to an
  absolute path on the absolute entries of `PATH`, and every command of that run uses it
  (`RR-002`); each command starts in the run's private working directory,
  `$OAK_RUNNER_HOME/run-*`, which is removed when the run ends (`RR-027`).
- **Bundled schemas.** The runner verifies every document against the schemas installed
  with it and ignores `OAK_SCHEMA_DIRECTORY`, which configures the control plane only
  (`RR-033`).

### What the native adapter does

`adapter.local-native` (`0.1.0`) runs on macOS on Apple silicon and on Linux on x86_64 and
aarch64, and refuses any other platform (`OAK-NATIVE-PLATFORM`). A native `apply` runs under
a lease of an hour rather than five minutes, because it downloads inside its dispatch; its
plan's lease policy admits that and no more. For a verified native `apply`, in order:

1. It creates `native/<installation id>` in the runner home, readable by the user only,
   under a name of its own first and renamed into place with its ownership marker
   `.oak-installation.json`, so the installation's path never exists without the marker. A
   directory it did not create and mark is never adopted, stopped or removed
   (`OAK-NATIVE-OWNERSHIP`).
2. It fetches each artifact over HTTPS from an acknowledged host, with TLS verified, no
   proxy taken from the environment, every redirect checked against the same hosts, a
   download refused as soon as it grows past the acknowledged size, and stopped when the
   lease ends (`OAK-NATIVE-HOST`, `OAK-NATIVE-SIZE`, `OAK-NATIVE-DOWNLOAD`,
   `OAK-RUNNER-LEASE-EXPIRED`); the stand-in is copied from inside OAK instead, and a file
   another component of the same installation already verified is linked, not fetched
   again. A file whose size or SHA-256 is not the profile's is refused before anything runs
   (`OAK-NATIVE-DIGEST`), and every `apply` checks the files again. An archive is unpacked
   afresh from its verified bytes on every `apply`, member by member. A link to a file
   inside it, such as a library's versioned name, is written as a copy of that file, so
   nothing unpacked is ever a link; a link that leaves the archive or names nothing in it,
   a device, an absolute path, a `..`, more than 10,000 members or more than 64 GiB is
   refused (`OAK-NATIVE-ARCHIVE`).
3. It starts each component from its harness kind's fixed argument template: the stand-in
   through the runner's own interpreter, `llama-server` with `--host 127.0.0.1`, its port,
   its model file and `--api-key-file`. The port must be free first, so another listener can
   never answer in the component's place (`OAK-NATIVE-START`). The process gets only `PATH`,
   `HOME` and `LANG`, a process group of its own, and three ceilings, each only ever lower
   than the runner's own: no core files, at most 4,096 open files, and no written file over
   2 GiB. Memory, CPU time and the number of processes are not limited, and the evidence records
   both lists. The adapter probes the health path on 127.0.0.1 until it answers `200`, for
   up to 20 seconds for the stand-in and 240 for `llama-server`; the component passes only
   if it is still running after answering twice, half a second apart. Then the adapter
   stops the whole group: `SIGTERM`, then, after up to 10 seconds, `SIGKILL` to whatever is
   left of it, including a child its first process left behind; it records the component
   as stopped only when nothing of the group remains (`OAK-NATIVE-STOP` otherwise). A
   component that does not pass fails the install (`OAK-NATIVE-SMOKE`), and the install is
   rolled back. `SIGTERM` or `SIGHUP` to the runner during a check stops the component
   before the runner exits.
4. Nothing keeps running, and nothing is registered to start with the computer; a program
   built to leave its process group could still leave a process behind (`RR-056`). The
   evidence names each verified artifact, each component's check, and whether it stopped.

A `llama_cpp_server` installation has a key of its own. Before it fetches anything, the adapter
writes 256 random bits to `api-key.txt` in the installation's directory, readable by the user
only, and it gives the server that file's path, never the key, so the key is in no argument
vector, environment, evidence, journal or record. `START.txt` names the file and shows how a
client sends the key (`Authorization: Bearer <key>`, handed to `curl` on its input so that the
client does not put it in `ps` either, and past any proxy), and does not hold it. A later
`apply` keeps a key that only its owner can read and that is still what the adapter wrote, so
the clients that hold it go on working. It replaces anything else, because a file that others
could read is no longer a secret, and `--api-key-file` skips empty lines and comments, which
would start the server with no key at all. It writes a new key aside and renames it into place,
so a write that fails leaves no file, which the server refuses to start without, and it refuses
anything but a file in that place (`OAK-NATIVE-OWNERSHIP`). Once the server has answered its
health probe twice, its check sends `GET /v1/chat/completions` with no key. The server refuses
that before it routes, so no model runs, and the row records the answer as
`status_without_key`. Any answer but `401` fails the install (`OAK-NATIVE-KEY`), and no answer
fails it as any other check does (`OAK-NATIVE-SMOKE`). The stand-in answers only its health path
and takes no key.

`rollback` and `destroy` remove exactly the installation's directory after checking its
marker: renamed out of the way first, so a removal that fails part way leaves the path
free and a leftover that the next removal finishes (`OAK-NATIVE-UNINSTALL`). A failed
`apply` removes the installation only when that `apply` created it, and a file the adapter
cannot write or read fails it with `OAK-NATIVE-IO`.

## Heartbeats

While a dispatch runs, the runner publishes a signed `heartbeat` message to the mailbox, a
message kind the runner-message schema has listed since the protocol's first version and
unused until Tier 3's Batch A. One goes out at the next step boundary once
`OAK_RUNNER_HEARTBEAT_SECONDS` (default 30) have passed since the last: when the lease is
accepted (always, the first), before and after each operation, between the containers an
`apply` creates and starts, and at each readiness poll. Each names the lease, a sequence
of its own within it, and the journal's head at that moment (`journal_sequence`,
`journal_digest`), and is signed with the runner's key like every message.

A heartbeat is a report, never an authority: it moves no state, extends no lease, and is
bound to its lease like a completion, so `oak ingest` believes one only from an enrolled
runner, for a lease this control plane dispatched. Ingest records each as a
`runner_heartbeat` audit event beside the case (`oak.community/runner_heartbeat_refs`),
a lease's heartbeats before its completion whatever order the mailbox lists them in, and
refuses a completion for the lease whose journal no longer reaches the head the last
heartbeat named (`OAK-INGEST-JOURNAL`), as it refuses one that falls short of an accepted
completion. A heartbeat the mailbox cannot take is dropped and the next one carries on the
sequence; the install is not stopped for it. `OAK_RUNNER_HEARTBEAT_SECONDS=0` publishes
none.

## What the runner keeps, and for how long

- **Journals** (`$OAK_RUNNER_HOME/journals/<dispatch>.jsonl`) are never removed. A run
  reads and verifies a journal once, when it opens it, and appends from the head it keeps
  in memory; before each append it checks that the file still ends at the entry it last
  wrote. So a journal that does not verify when a run opens it, or that is cut or edited
  under the run, is never extended (`OAK-JOURNAL-TAMPERED`); a heartbeat names the head
  the run holds.
- **The consumed-nonce ledger** (`$OAK_RUNNER_HOME/consumed-nonces.json`) maps each lease
  nonce the runner accepted to that lease's expiry and keeps it while the lease could still
  be replayed: until its expiry plus a five-minute clock-skew allowance. A nonce whose
  expiry it does not know (a ledger written before this batch is a list) or cannot read is
  kept for ever. The file is still rewritten whole on each accepted dispatch, but it holds
  only the leases still in play.
- **Processed dispatch directories** in the mailbox are removed at the end of a run once
  older than `OAK_RUNNER_DISPATCH_RETENTION_DAYS` (default 30; `0` keeps every one),
  except the newest processed one and any whose completion `oak ingest` has not taken yet.
  `oak-runner status` ties a journal to its completions by the lease its own
  `lease_accepted` entry names, so the comparison stays `matched` without the directory.

## Reading `oak-runner status`

`status` prints one JSON object per journal under `$OAK_RUNNER_HOME/journals`:

```json
{
  "journals": [
    {
      "dispatch": "d0001",
      "entries": 7,
      "chain": "verified",
      "signed_head": "matched",
      "manual_recovery_required": false
    }
  ],
  "missing_journals": []
}
```

`chain` has four values:

| Value | Meaning |
|---|---|
| `verified` | The hash chain is intact end to end |
| `truncated` | The chain verifies, but it stops short of the entry this runner signed into its newest completion for the dispatch: entries were removed from its end. Treated as requiring manual recovery |
| `tampered` | The chain is readable but does not verify — an entry was altered, removed or reordered |
| `unreadable` | A journal line could not be parsed at all: truncated, corrupt or the wrong shape. Reported rather than crashing the command, and treated as requiring manual recovery |

A hash chain alone cannot show that its end was cut, because any prefix of a valid journal
verifies. So every completion of a dispatch the runner took up names the head of its
journal, the last entry's `journal_sequence` and its `journal_digest`, and, with
`OAK_RUNNER_MAILBOX` set, `status` reads the newest completion for each dispatch that is
still in the mailbox (`messages/` or `acknowledged/`), believing only one whose signature
verifies under this runner's own key. Pass the mailbox to `status` as you do to `run-once`:
without it nothing is compared.
A journal is tied to its completions by its dispatch, by the lease its own
`lease_accepted` entry names and by the lease in the delivered envelope, so editing or
deleting the envelope does not hide a cut. `signed_head` says what the comparison found:

| Value | Meaning |
|---|---|
| `matched` | The journal reaches the entry the newest signed completion names |
| `missing_from_journal` | It does not, and `chain` is `truncated` |
| `none` | No completion of this dispatch signed by this runner is in the mailbox, so there was nothing to compare: an interrupted dispatch before its report, or a mailbox someone cleaned |
| `other_key` | The only completions of this dispatch verify under a key that is not the runner's current one: the key was replaced since (the next `run-once` or `identity` makes a new one when it is missing), or someone signed one. Nothing could be compared; compare the journal with those completions by hand |
| `unchecked` | `OAK_RUNNER_MAILBOX` is not set, the runner has no key yet (and the mailbox holds no completion), or the chain did not verify |

With the mailbox set, a runner key that cannot be read, or none while the mailbox holds a
completion that verifies under the key it carries, stops `status` with `OAK-RUNNER-KEY`
(exit `70`) rather than reporting journals it could not compare: moving the key aside
would otherwise turn a cut journal back into `verified`. Once a new key replaces it, the
old completions read `other_key`. A file in the mailbox that does not verify under the key
it carries (unsigned, malformed, nested past the interpreter's limit, or holding a `NaN`)
is ignored, with a key or without one. Whoever can replace the key can also sign a
completion naming a cut head; that is `RR-054`'s remaining risk, which the control plane's
accepted record bounds.

`missing_journals` lists each completion this runner signed that no journal file is tied
to (`{"completion": <message id>, "lease": <lease id>}`): a journal deleted outright, whose
recovery state is unknown, so treat its lease as requiring manual recovery.

The comparison defends against a journal cut by someone, or something (a restored backup,
a clean-up script), that did not also remove the completions from the mailbox. It does not
defend against whoever holds the runner's key and can write to the mailbox: they can sign
a completion naming the cut head. What defends the record past that point is the control
plane: `oak ingest` keeps every completion it accepted, out of reach of the runner's home,
and refuses a completion for the same lease whose journal is shorter than one it accepted
or as long with another last entry, and any completion but a denial that names no journal
head (`OAK-INGEST-JOURNAL`). The refused message stays in the
mailbox and is reported on every ingest. A longer journal is believed to extend the
earlier one on the strength of the runner's signature over both (`RR-054`).

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
an interrupted side effect refuses to continue and records `manual_recovery_required`.
A dispatch that an earlier run took up and never finished — the process died mid-operation
— is never re-run: the next run appends `manual_recovery_required` to its journal, naming
the open operation and the containers it lists, and publishes a signed completion saying
so, which `oak ingest` records as `runner_recovery_required`. `oak-runner status` reports
any journal with an open operation as needing recovery. Resolve it by inspecting the journal
and the installation's labelled containers
(`docker ps --all --filter label=oak.installation=<installation id>`), removing them with a
signed rollback or by hand, then re-dispatch. Losing the
trust directory invalidates outstanding envelopes and approvals, which are re-signable from
the unchanged canonical artifacts.
