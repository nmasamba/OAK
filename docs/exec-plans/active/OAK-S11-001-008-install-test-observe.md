<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-S11-001–008: install the chosen architecture, test it, record what was observed

**Authorized by the owner on 2026-09-29.** The owner asked for the sprint in
`SPRINT-11-PROMPT.md` (governance root) to be planned and implemented, with two additions:

1. **Nothing is installed until the user has approved the architecture *and* the installation
   step**, as two separate approvals.
2. **A user may stop once they have the architecture**, for example as YAML, and never install
   anything.

Execution is on branch `sprint-11-install-observe`, branched from `origin/main` at `3f47312`.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-09-29
- Last updated: 2026-09-29 (Milestones 1–6 committed; test sweep, audit and documentation next)
- State: in-progress
- Claimed tasks: `OAK-S11-001`–`OAK-S11-008`

## Owner's answers, and what they settle

| # | Question | Answer (2026-09-29) | Effect on this plan |
|---|---|---|---|
| A | How is architecture approval recorded, separately from install approval? | **A new signed approval** | A new approval action, `architecture`. `oak approve apply` is refused until one exists. Dispatch and the runner each check again, independently, that both are present. Rollback and destroy never need it. |
| 1 | Start the containers, or only create them? | **Start, opt-in per target** | A new `execution.mutation_acknowledgement` value opts a profile in to starting. Starts run under a fixed set of hardening flags. Profiles with today's value are still never started. |
| 2 | How is the smoke test expressed? | **Inside `apply`** (decision 2b) | No new operation kind and no change to the kind enums. `apply` waits for readiness as its own post-condition and emits `test_result` and `aggregate_metric` evidence. |
| B | How does a user stop at the architecture? | **An `oak architecture` command** | A new read-only command prints the chosen architecture as human-readable text, JSON or YAML. It works locally and in remote mode over the REST routes that already exist. It never compiles, signs or installs anything. |

The prompt's other five decisions (4–9) were not put to the owner. This plan takes the
prompt's recommendations, with the reasoning under `## Decisions`, so the owner can object.

## Outcome

Today a user can compile the candidate they chose, and a signed runner can create one
never-started container. That container is not part of the candidate: it is the target
profile's own PostgreSQL stand-in. Nothing tests it, the case never reaches `deployed`, and
nothing records what was observed.

After this plan, a user can choose how far to go.

**Stop at the architecture.** Nothing is installed:

```bash
oak architecture --output yaml > architecture.yaml
```

This prints the selected candidate: its nodes and edges, its components, and every prediction
with its interval. It also includes the owner's decision and, once compiled, the image each
node would run. Nothing is compiled, signed or installed.

**Or install it, test it, and read what was observed:**

```bash
oak plan candidate-03 --target examples/targets/local-started-fixture.yaml --output review
oak keys init && oak sign
oak approve architecture          # "I approve this architecture": prints nodes -> images
oak approve apply                 # "I approve installing it here"; refused without the above
oak dispatch apply
oak-runner run-once && oak ingest # case: deployed
oak dispatch apply && oak-runner run-once && oak ingest   # re-apply: every node already_present
oak observe --output yaml         # case: observing; the record beside the predictions
oak approve rollback && oak dispatch rollback && oak-runner run-once && oak ingest
oak observe                       # a second record, now with rollback recovery measured
docker ps --all --filter name=oak-fixture-   # empty
```

The record says, number by number:

- **Deployment measures:** install success (`EV-DEP-01`), idempotent re-apply (`EV-DEP-02`),
  rollback recovery (`EV-DEP-03`) and the smoke test. Each is `pass`, `fail` or `unknown`,
  with its sample size and evidence references. It also says that a single sample cannot
  satisfy a gate.
- **Calibration:** one row for every objective of the selected candidate and every contract
  metric. Each row has the estimator and version, the conditions, the point estimate and
  interval, and either an observed value or `unknown` with a reason code. It also has the
  error, interval coverage, and the recalibration decision "none — single non-production
  sample".
- **Unpredicted measurements:** startup seconds and steady-state memory per node. OAK
  measured these but never predicted them.

Every other boundary stays where it is. The web cannot approve, dispatch or observe. MCP
gains no tool. REST gains no write. The deterministic bytes are unchanged, except for the one
assurance-text correction that the changelog declares.

## Context and invariants

Terms:

- **Topology node:** an entry in `candidate.topology.nodes`. It has an `id` such as
  `node.retrieval`, and a `component_ref` of the form `<manifest_id>@<version>`, or `null`.
- **Component lock:** the manifests the candidate uses (`candidate.components`). A lock
  digest is the digest of the catalogue *manifest document* (`catalogue.py:45-51`), not an
  image digest.
- **Stand-in image:** an image the operator names in their target profile to stand in for a
  synthetic component. It proves the install, test and remove loop. It does not implement the
  component.

Verified facts, checked against `3f47312`:

- **What `apply` does today.** `apply` creates one container named
  `oak-fixture-<target>`, never started, from the target's
  `execution.container_image_reference`/`_digest` (`src/oak/runner/adapters.py:77-104`,
  `src/oak/compiler/planning.py:499-505`).
  - The image is checked against `RepoDigests` after it is created (`adapters.py:105-149`).
  - `rollback`/`destroy` run `docker rm --force` (`:179-186`). This leaks anonymous volumes
    from images that declare `VOLUME`.
- **Container adapter shape.** The container parameter schema is closed and holds a single
  container. Its `isolation` is a const, `network-none-never-started`
  (`src/oak/domain/runner_adapters.py:56-73`).
  - The runner refuses a plan that has two operations of the same kind
    (`src/oak/runner/verification.py:392-399`).
  - It runs verified operations in plan order (`:501-503`).
- **Failure path.** When `apply` fails, execution calls `container.rollback` with the whole
  parameter set (`src/oak/runner/execution.py:114-121`). Evidence from a failed operation is
  dropped (`:108-147`).
- **Approvals.** The approval action set is closed in four places:
  - `schemas/approval.schema.json:54-61`
  - `schemas/revocation.schema.json:36-42`
  - `APPROVAL_ACTIONS` at `src/oak/application/release.py:45`
  - `src/oak/application/gitops.py:98`

  `approve` is refused unless the case is `bundle_compiled` or `deployment_approved`
  (`release.py:164-168`). Its default idempotency key does not depend on the case version,
  and neither does dispatch's (`release.py:155-156`, `:331-332`). So a repeated
  `oak approve rollback` or a second `oak dispatch apply` returns the earlier result.
- **Ingest.** `oak ingest` sets `deployed` only when the completion applied `apply`, succeeded,
  and did not roll back in the same completion (`release.py:529-547`). Nothing sets
  `observing`. No test asserts either state.
- **Assurance.** The assurance plan's `gate_3` reason is stale: "Observed calibration,
  signing, approvals and runner verification are not implemented" (`assurance.py:98-99`).
  So is `control.read-only-plan` ("Limit Sprint 2 runner operations …", `:78`).
  - The assurance digest enters the provenance review artifact (`planning.py:135`), then the
    bundle's `supply_chain` (`:337`).
  - So correcting that text moves exactly `deployment_bundle`, `runner_plan` and the case
    among the pinned values (`tests/integration/test_reference_digests.py:37-55`). The
    candidate and semantic-manifest pins do not move.
- **Web.** The web hard-codes "compiled, unsigned", "none recorded" and "no runner execution
  authority" (`web/src/pages/BundlePage.tsx:281-304`). It links the bundle only at
  `assurance_planned`/`bundle_compiled` (`CasePage.tsx:357`). The phrase "no runner execution
  authority" is pinned at `web/e2e/journey.spec.ts:188-192`.
- **The reference candidate.** candidate-03 has **two** nodes: `node.retrieval` uses
  `component.fixture-lexical-search`, and `node.generation` uses
  `component.fixture-local-model` (`src/oak/compiler/candidates.py:437-451`). The example
  file's third node (`node.review-ui`, `component_ref: null`) is not something the compiler
  produces.
  - Objectives: `monthly_cost`, `latency_p95`, `quality`, `operability` and `energy`, each
    with a lower and upper bound (`candidates.py:469-540`).
  - The contract has three metrics, with fixture values and no interval
    (`evaluation.py:10-14`, `:40-54`).

Invariants, from `AGENTS.md`, ADR-0015 and the prompt:

- **The deterministic path stays byte-identical**, except for the assurance-text shift
  declared in decision 6.
- **No transport gains apply.** `approve`, `dispatch`, `ingest` and `observe` are local-only.
  Remote mode refuses them with `OAK-REMOTE-UNSUPPORTED`. MCP gains no tool; REST gains no
  write; the web gains no action.
- **No free-form execution.**
  - Argv is built from typed fields, against the executable allowlist `{"docker"}`.
  - `command`, `shell`, `executable` and `argv` stay forbidden.
  - No `exec`, no `logs`, no `run`, no port publishing, and no HTTP client under
    `src/oak/runner`.
- **Seven authorities, none collapsed.** Compile, sign, approve the architecture, approve the
  action, dispatch, execute and observe are each separate. Observation writes an artifact and
  an audit event and nothing else. It never promotes anything, and it never feeds a dispatch,
  an approval or the runner.
- **Evidence is typed measures and digests.** No container log, no environment, no raw
  stdout or stderr.
- **No new runtime dependency**, no new network client, no logging framework.

Requirements served:

- `OAK-FR-DEP-003` (preflight before mutation)
- `OAK-FR-DEP-004` (idempotent install, smoke test and rollback, or a recoverable checkpoint)
- `OAK-FR-DEP-005` (a current approval bound to the digest and target)
- `OAK-FR-ARC-006` (predictions compared with observations)
- `OAK-FR-IMP-001` (the "observe" stage only; nothing downstream of it)
- `EV-DEP-01`, `EV-DEP-02` and `EV-DEP-03`
- The calibration list in governance `docs/evaluation-contract.md:111-123`

## Scope

### In

- **Architecture approval** (owner answer A). `oak approve architecture` signs an approval in
  the approver role.
  - It binds the plan, bundle and target, as every approval does.
  - Its `extensions["oak.community/architecture"]` carries:
    - the architecture-decision reference;
    - the selected-candidate reference;
    - a digest of the node → image installation map.
  - It records while the case is `bundle_compiled`/`deployment_approved`. It is revocable
    through the existing signed-manifest channel.
  - `oak approve apply` fails with `OAK-APPROVAL-ARCHITECTURE` unless a current, unrevoked
    architecture approval for the same plan digest exists.
  - `oak dispatch apply` attaches both approvals. The runner requires both for `apply`, and
    checks that the architecture approval's decision digest equals the bundle's
    `architecture_decision_ref.digest`.
- **Install the topology** (`OAK-S11-002`).
  - The target profile gains `execution.component_images`, a list of
    `{manifest_id, image_reference, image_digest}` that the operator acknowledges.
  - The compiler emits one `apply` operation that lists one container per topology node with
    a component. Each container name carries the identity of its case, target and node.
  - A locked component with no image fails preflight (`preflight.installation`), with no
    fallback. The deprecated single-image pair is refused with `OAK-TARGET-EXECUTION`.
  - Apply is idempotent. It adopts only a container that carries the OAK label, this case,
    this node and the approved digest, and denies a foreign one (`OAK-RUNNER-FOREIGN`).
  - Rollback and destroy remove only containers OAK owns, with `--volumes`. They report
    `absent_after` from an inspect.
  - A failed apply compensates only for the containers it created in that invocation.
- **Smoke test inside apply** (`OAK-S11-003`).
  - This applies only on a profile whose acknowledgement is
    `isolated-non-production-hardened-start`.
  - Create runs with the hardening flags. Then `docker start`, then a bounded readiness wait
    over `docker inspect` (running, or healthy when the image declares a `HEALTHCHECK`),
    exit code, startup seconds, and one `docker stats --no-stream` memory reading.
  - Evidence goes in `test_result` and `aggregate_metric` items.
  - A failed test fails the apply, and the apply is compensated.
  - Key-based evidence redaction.
  - A lease-deadline check before each creating side effect (`RR-031`, in part).
  - Evidence from a failed or compensated operation now reaches the completion.
- **Observation** (`OAK-S11-004`).
  - A new schema, `observation-record.schema.json`, with an example.
  - A new `observation_record` artifact kind, indexed under
    `extensions["oak.community/observation_refs"]`.
  - A pure builder, `oak.compiler.observation`.
  - `oak observe`, which is local-only. It moves the case `deployed → observing`, and records
    another record at `observing` only when new runner results have arrived.
  - A new audit event type, `observation_recorded`.
  - `rollback`/`destroy` approvals are recordable at `deployed`/`observing`. `apply`,
    `dry_run` and `architecture` are refused there.
- **Truthful lifecycle** (`OAK-S11-005`).
  - The shipped journey reaches `deployed`, and a test says so.
  - Approve and dispatch get default idempotency keys scoped to the case version.
  - Re-approving an action publishes a new approval version instead of colliding with
    `OAK-ARTIFACT-IMMUTABLE`.
  - The assurance plan's `gate_3` reason and `control.read-only-plan` are corrected under a
    declared digest shift.
  - BundlePage and CasePage read what the case carries instead of hard-coding its absence.
- **`oak architecture`** (owner answer B).
- **Test sweep, audit and documentation** across both repositories (`OAK-S11-006`–`008`).

### Out

- A new operation kind. Owner answer 2 settled that the smoke test lives inside `apply`.
- Real component images in the catalogue. That would move every pinned digest. It would also
  need real artifacts the catalogue does not have.
- Any request workload, probe, port, `exec` or log read. Quality, latency, cost and energy
  therefore stay `unknown` in every calibration row, each with a reason. Observing them needs
  a workload and a person, and is a later sprint.
- A web observation view, change proposals and promotion (`OAK-FR-IMP-001` past "observe").
- Runner heartbeats. `RR-031` stays open. Its apply half gains a deadline check.
- Any release, tag or publication.

## Contract and data changes

| Surface | Change | Compatibility |
|---|---|---|
| `schemas/approval.schema.json` `action` | adds `architecture` | Conditionally compatible: a published reader cannot validate an architecture approval. |
| `schemas/revocation.schema.json` `action` | adds `architecture` | Conditionally compatible. |
| `schemas/target-profile.schema.json` `execution` | adds `component_images`, and the value `isolated-non-production-hardened-start` to `mutation_acknowledgement`; `container_image_reference`/`_digest` become optional and deprecated | Conditionally compatible. A published reader rejects a profile carrying the new field. A profile relying on the old pair must add `component_images`, or its compile refuses with a stable code. |
| Container adapter `adapter.local-container` | version `0.2.0`; the parameter schema becomes `{case_id, target_id, isolation, containers[]}`; `isolation` is one of `network-none-never-started` or `network-none-started-hardened` | **Breaking for plans compiled before this change.** Their adapter digest no longer matches, so the runner denies them with `OAK-RUNNER-ADAPTER`. Plans expire after one day, and no pinned plan uses the adapter. |
| `schemas/observation-record.schema.json` (new, `0.1.0`), and a new kind `observation_record` | new | Additive. |
| `schemas/audit-event.schema.json` `event_type` | adds `observation_recorded` | Conditionally compatible. |
| `schemas/workspace-manifest.schema.json` kind enum | adds `observation_record` | Conditionally compatible. |
| Runner completion payload | adds `requested_kinds` and `failed_kind`; evidence can now come from a failed operation | Compatible. The payload is a free object, and older completions are read as `unknown`. |
| CLI | adds `oak architecture`, `oak observe` and `oak approve architecture`; `oak approve apply` now requires an architecture approval | **Breaking for scripts** that approve `apply` without first approving the architecture. The migration is one command. |
| Case `extensions` | adds `oak.community/observation_refs`; `approval_refs` gains an `architecture` key | Compatible. Extensions are namespaced and free. |
| Assurance-plan text | `gate_3` reason and `control.read-only-plan` corrected | **Digest-shifting** under compatibility rule 4. `deployment_bundle`, `runner_plan` and the case pin move. Before-and-after values go in the changelog and in `test_reference_digests.py` in the same commit. |
| REST, OpenAPI, MCP | none | The artifacts are readable through the existing `GET /v1/design-cases/{id}` and artifact routes. |
| Persistence | none | The artifact `kind` column is free text (`String(80)`). No migration. |
| Runner protocol version | stays `0.1.0` | The message shapes are unchanged. |

## Milestones

### Milestone 1 — Branch, plan, governance (`OAK-S11-001`)

- **Work:**
  - The branch and this plan.
  - Sprint 11 registered in governance `sprints.md` from the backlog block, adjusted for the
    owner's answers.
  - Governance `STATUS.md` and `spec-manifest.yaml` updated.
  - Tasks claimed in `OAKCommunity/STATUS.md`.
- **Proof:** a baseline `make check` with PostgreSQL enabled on a throwaway database
  (`oak-s11-testpg`, `127.0.0.1:15433`), with zero `make: ***` lines. The governance validator
  is clean.
- **Rollback:** documentation only.

### Milestone 2 — Architecture approval (owner answer A)

- **Work:**
  - The `architecture` action is added to the two schemas, `APPROVAL_ACTIONS`, `gitops.py`
    and the CLI help strings.
  - `ReleaseService.approve`:
    - binds the architecture extension for `architecture`;
    - requires a current architecture approval before `apply`;
    - moves `deployment_approved` only on `apply`.
  - Dispatch requires `architecture` in addition to `apply` for an `apply` dispatch.
  - Runner step 9 requires both for `apply`, and checks the bound decision digest against
    the bundle.
- **Proof:**
  - Unit and integration tests for:
    - apply-before-architecture (`OAK-APPROVAL-ARCHITECTURE`);
    - a dispatch missing the architecture approval (`OAK-DISPATCH-APPROVAL`);
    - an envelope missing it, or carrying a revoked or mismatched one
      (`OAK-RUNNER-APPROVAL`);
    - a rollback dispatch needing no architecture approval.
  - Each guard is mutation-checked.
- **Rollback:** revert the commit. No stored data depends on it.

### Milestone 3 — Install the topology (`OAK-S11-002`)

- **Work:**
  - Target-profile schema fields.
  - `container_name_for(case_id, target_id, node_id)` in `oak.domain.runner_adapters`.
  - Container adapter `0.2.0` with the list-shaped parameter schema.
  - Compiler:
    - `preflight.installation`, for mutation targets only;
    - the node-list `apply`/`rollback`/`destroy` operations;
    - evidence categories `aggregate_metric` and `rollback_result`, for mutation targets
      only.
  - Runner verification: `case_id`/`target_id` must equal the envelope's, and each name must
    equal the recomputed one.
  - `ContainerFixtureAdapter` rewritten for idempotent create/adopt, foreign denial,
    owned-only verified removal and self-compensation. `execute_dispatch` compensates
    exactly what was created and keeps the failed operation's evidence.
  - The shipped `local-mutation-fixture.yaml` maps the components to the stand-in image. A
    new `local-started-fixture.yaml` carries the start acknowledgement.
- **Proof:**
  - Fake-executor tests: create, adopt, foreign, partial failure plus compensation, removal
    verified by inspect, and injection.
  - Compiler tests: an unmapped component fails preflight; the deprecated pair is refused;
    names are unique and within the pattern.
  - `test_reference_digests.py` unchanged.
- **Rollback:** revert. Plans compiled on this branch stop verifying, which is intended.

### Milestone 4 — Smoke test and hardening (`OAK-S11-003`)

- **Work:**
  - Hardened create argv for started profiles:
    - `--network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges`
    - `--user=65534:65534 --memory=256m --memory-swap=256m --cpus=0.5 --pids-limit=64`
    - `--restart=no --log-driver=none`
    - no `-v`, no `-e`, no `-p`
  - `docker start`, a readiness wait (15 s budget per node, polled every 0.5 s through an
    injected clock), and `docker stats --no-stream`.
  - Evidence items:
    - `status`: per node, `created` or `already_present`, plus the resolved digest;
    - `test_result`: per node, state, health, exit code, ready, startup seconds;
    - `aggregate_metric`: per node, memory bytes.
  - Key-based redaction, and a URL-credential pattern.
  - A lease-deadline guard.
- **Proof:**
  - Fake-executor tests for running, healthy, unhealthy, exited, timeout, unparsable stats,
    and a deadline past due.
  - Argv assertions: exact flags, never `exec`/`logs`/`run`/`-p`/`-e`/`-v`.
  - Profiles with the old acknowledgement produce no `start` argv.
  - Redaction tests for keys and URLs.
- **Rollback:** revert.

### Milestone 5 — Observation (`OAK-S11-004`)

- **Work:**
  - Schema, example, `EXAMPLE_BY_SCHEMA`, `KIND_SCHEMA`, `JSON_MEDIA_KIND`, the
    workspace-manifest enum, and the `schemas/README.md` row and count sentence.
  - The audit event type.
  - The pure builder:
    - `EV-DEP-01/02/03` and the smoke test, from the ingested completions;
    - calibration rows for every objective and contract metric;
    - unpredicted measurements;
    - the assurance status of `evidence.observed-calibration`, which says what is missing.
  - `ReleaseService.record_observation`, and `oak observe`, which is local-only.
  - `deployed → observing`.
  - Approvals for rollback and destroy at `deployed`/`observing`.
- **Proof:**
  - Builder unit tests: no evidence; one install; a failed then successful install; a
    re-apply; a rollback that verified `absent_after`; a false removal claim; a missing
    payload field.
  - Service tests:
    - observe before `deployed` fails with `OAK-OBSERVE-STATE`;
    - a second record with no new results fails with `OAK-OBSERVE-DUPLICATE`;
    - remote mode is refused.
  - A contract test that every `unknown` carries a reason.
- **Rollback:** revert. The kind is additive.

### Milestone 6 — Truthful lifecycle, assurance text, web, `oak architecture` (`OAK-S11-005`)

- **Work:**
  - Case-version-scoped default idempotency keys for approve and dispatch.
  - Approval re-versioning.
  - The assurance text correction, with the three digest values moved in the same commit.
  - BundlePage and CasePage truthfulness.
  - `oak architecture` (local, plus remote through a new `RemoteClient.get_artifact`).
  - An e2e CLI journey that asserts `deployed`, `observing`, `runner_result_refs` and the
    event classification, using a fake-daemon seam where docker is absent.
- **Proof:**
  - `test_reference_digests.py` with exactly three values moved, and the old and new values
    in the changelog.
  - `oak architecture --output yaml` from a case at `candidate_selected` and at
    `bundle_compiled`, locally and remotely.
  - Web unit build.
  - Browser suite against a throwaway stack.
- **Rollback:** revert. The digest shift reverts with it.

### Milestone 7 — Test sweep and adversarial audit (`OAK-S11-006`)

- **Work:**
  - `make check` with PostgreSQL enabled.
  - The real-daemon journey on the owner's machine, with the transcript below.
  - `make web-e2e` against a throwaway Compose project.
  - `make validate`, `make openapi-compatibility` and the governance validator.
  - A multi-lens adversarial audit covering:
    - runner changes;
    - the architecture approval;
    - the observation seam;
    - the digest declaration;
    - documentation honesty.

    Every finding goes to independent refute-by-default reviewers. Survivors are fixed.
- **Proof:** the gate output and the audit table in this plan.

### Milestone 8 — Documentation and coherence, both repositories (`OAK-S11-007`)

- **Work:** grep the whole corpus for the claims this sprint made false, not just the files
  edited (seed list in the prompt):
  - `RR-043`, with the count moved to 43 in `STATUS.md:332` and `CHANGELOG.md:504`;
  - `RR-023` re-scored;
  - threat-coverage verdicts, and the stale `STATUS.md` tally;
  - `docs/signed-runner.md`, the manual, the tour, the README and the interface contract;
  - governance ADR-0017 and its mirror;
  - `evidence/sources.yaml` for the stand-in image.
- **Proof:** the governance validator, `make check`, and the sweep table in this plan.

### Milestone 9 — Close (`OAK-S11-008`)

- **Work:** plan to `completed/`; both `STATUS.md` files and both `CHANGELOG.md` files
  updated; a PR with remote CI green. No tag, no release.

## Verification

- **Unit and contract:**
  - adapter argv and state machine;
  - parameter-schema binding;
  - naming;
  - redaction;
  - the observation builder;
  - schema and example conformance;
  - the kind-registration drift test;
  - the error-code reference;
  - the configuration reference;
  - the MCP tool set unchanged;
  - the remote-refusal list extended with `observe`.
- **Integration:**
  - the release service (approve ordering, dispatch attachments, ingest classification,
    observe);
  - the runner with a fake executor through `execute_dispatch` (the `executor=` seam no test
    used before);
  - reference digests;
  - the offline boundary;
  - PostgreSQL suites on.
- **End-to-end:**
  - the CLI journey to `observing` through a fake daemon;
  - the real-daemon journey, which is skipped unless `docker info` answers;
  - the browser suite against a throwaway stack.
- **Mutation checks:** break each new guard on purpose and watch its test fail. The guards:
  architecture-before-apply, runner architecture check, foreign denial, owned-only removal,
  name recompute, `case_id` binding, deadline, redaction keys, observe state and duplicate.
- **Failure and retry:**
  - a partial apply failure;
  - a failed readiness;
  - a re-apply;
  - a rollback of an absent container;
  - a repeated observe;
  - an expired approval renewed at `deployed`.

## Security, privacy and authority review

- **Input trust.**
  - The plan's node list is compiler output. The runner still recomputes each container name
    from the case, target and node, so a plan cannot address a container outside its own
    case.
  - Labels and names are validated by pattern before they reach argv.
  - Images are digest-pinned, allowlisted by registry, and checked against `RepoDigests` after
    creation.
- **Privileged operation.** Starting a process on the operator's machine is new. It is opt-in
  per profile, and bounded by:
  - `--network=none`;
  - a read-only root;
  - no capabilities and no new privileges;
  - uid 65534;
  - memory, CPU and pid ceilings;
  - no volumes, environment or ports;
  - `--restart=no`;
  - removal on every failure path.

  It is recorded as `RR-043` and in ADR-0017.
- **No free-form shell.** Every argv is a tuple literal plus validated fields. No `exec`,
  `logs`, `run` or `-p`. The executable allowlist is unchanged.
- **Data.**
  - Evidence carries typed fields and digests only: state strings from a fixed vocabulary,
    integers and floats.
  - `docker stats` output is parsed to a number and then discarded.
  - Key-based redaction catches any future adapter field named like a secret.
- **Authority.**
  - The architecture approval and the apply approval are separate signed artifacts, checked
    three times: at approve, at dispatch, and by the runner.
  - Observation reads only runner messages that ingest has accepted and signature-checked. It
    writes an artifact and an event, and nothing reads the record to authorize anything.
- **Failure state.**
  - Apply compensates for what it created.
  - Compensation that fails leaves `manual_recovery_required` in the journal, with the names
    recorded.
  - A crash mid-apply leaves an open journal bracket, and the existing resume logic refuses
    further work on that dispatch.

## Operational and rollback plan

- **Local-only.** The failure surface is the operator's Docker daemon on the default socket
  (`RR-013`).
- The operator removes everything OAK installed with `oak approve rollback && oak dispatch
  rollback`, or by hand:

  ```bash
  docker ps --all --filter label=oak.fixture=true
  ```

- `docs/operations.md` says both.
- Reverting the branch restores the old adapter. Plans compiled with `0.2.0` then stop
  verifying, which is intended.

## Progress

- [x] 2026-09-29 Branch `sprint-11-install-observe` from `origin/main` (`3f47312`); prompt claims verified by five read-only readers; the owner's four answers recorded.
- [x] 2026-09-29 Baseline gates at `3f47312`, PostgreSQL suites on a throwaway database (`oak-s11-testpg`, `127.0.0.1:15433`): validate, format, lint, typecheck green; 667 unit and contract passed; integration 276 passed, 4 skipped — three PostgreSQL tests first failed because the fresh database had no schema, and passed after `oak-db-migrate`; 42 e2e passed (the docker apply cycle ran against the local daemon); `openapi-compatibility` and `web-build` green.
- [x] 2026-09-29 Sprint 11 registered in governance `sprints.md`; governance `STATUS.md`, `spec-manifest.yaml`, `VERSION`, `README.md` and `CHANGELOG.md` at `0.4.0-draft.7`; governance validator passes; tasks claimed in `STATUS.md`.
- [x] 2026-09-29 Milestone 2 (`48a7157`): `architecture` approval action in `approval`/`revocation` schemas, `APPROVAL_ACTIONS`, gitops and CLI help; `approve apply` refuses without a current architecture approval (`OAK-APPROVAL-ARCHITECTURE`); dispatch attaches both for `apply`; runner step 9 requires both and checks the approval's decision and installation digests against the dispatched bundle and plan; rollback/destroy approvals recordable at `deployed`/`observing`, others refused there; case-version-scoped default idempotency keys for approve and dispatch; a renewed approval is a successor version. `tests/integration/test_architecture_approval.py` (7). Mutation checks: 4/4 killed (apply without architecture, dispatch without it, runner without it, runner binding ignored).
- [x] 2026-09-29 Milestones 3 and 4, landed as one commit (`08e1098`) because the smoke test lives inside `apply` (owner answer 2): container adapter `0.2.0` with the node-list parameter schema; `container_name_for`; `execution.component_images` and the hardened-start acknowledgement in the target-profile schema; `preflight.installation` and the superseded-pair refusal in the compiler (mutation targets only); runner `_check_installation` (case, target, derived names, acknowledged images, isolation, registry per container); idempotent create/adopt, foreign denial, owned-only verified removal with `--volumes`, self-compensation of exactly what was created; hardened start, bounded readiness with settle, `docker stats` memory; evidence kept on failure; key-based and URL-credential redaction; lease-deadline guard; `requested_kinds`/`failed_kind` in the completion payload. Tests: unit `test_runner_adapters.py` (rewritten, 50+ cases), `test_runner_evidence_redaction.py`, integration `test_topology_install.py` (17); `test_reference_digests.py` unchanged and green. Mutation checks: 21/21 killed after one survivor (the runner's `case_id` binding, masked by the name check) got its own test. Real daemon: `test_runner_journey.py` apply/rollback green; a manual hardened-start run reached `deployed` with both containers `ro=true net=none caps=[ALL] user=65534:65534 mem=268435456 pids=64 no-new-privileges log=none restart=no mounts=0`, smoke test 0.11–0.13 s, ~500 KiB each; rollback left zero containers.
- [x] 2026-09-29 Milestone 5 (`eaa44dd`): `observation-record` schema `0.1.0` and example (recorded by `oak observe` from a real-daemon run), `observation_record` kind, `observation_recorded` audit event; the pure builder `oak.compiler.observation` scoring `EV-DEP-01/02/03` and the smoke test from accepted completions, one calibration row per objective and contract metric (all `unknown` with a reason code today), unpredicted startup and memory measurements, and the `evidence.observed-calibration` status naming what is missing; `ReleaseService.record_observation` and local-only `oak observe`; `deployed → observing`. Tests: `tests/unit/test_observation_builder.py` (15), `tests/integration/test_install_lifecycle.py` (5, the real `run_once` path with a scripted daemon), remote refusal of `observe` and `approve architecture`. The builder tests caught one real defect before commit: a candidate predicting none of the four calibrated measures read as "satisfied"; an unpredicted measure now counts as missing. Mutation checks: 11/11 killed after one survivor (a denied completion's guard) got a sharper assertion.
- [x] 2026-09-29 Milestone 6 (`1169b8e`): `oak architecture` (local, and remote over the existing GET routes with digest verification; `tests/integration/test_remote_cli.py`); the assurance text correction under the declared digest shift (`deployment_bundle` `570abb66…` → `9da17d02…`, `runner_plan` `fad30959…` → `03c4541a…`, case `f54f3419…` → `61cee339…`; candidate and semantic unchanged), signed examples regenerated with `scripts/generate_examples.py`; BundlePage reads signature, approvals, runner results and observations, CasePage keeps the bundle link past `bundle_compiled`; the real-daemon e2e runs the whole exit demonstration (architecture, apply refused without the architecture approval, install, hardened containers running, idempotent re-apply, observe, rollback, observe again, zero containers) and skips only when `docker info` does not answer. Default idempotency keys for approve and dispatch now carry the case version.

## Decisions

- 2026-09-29 **A — architecture approval.** The owner's answer: a separate signed approval.
  - **When:** after `oak plan`, because the approval schema binds the plan, bundle and target
    (`approval.schema.json:14-18`). Only then does the architecture include the images it
    would install, so the user approves exactly what will run.
  - **The alternative:** a new pre-compile artifact bound to the decision digest. It would
    add a schema and a kind, and it could not show the images.
  - **Stopping at the architecture** needs no approval at all (see B).
  - **Cost:** one enum value in two schemas, conditionally compatible. One more CLI step
    before install.
- 2026-09-29 **1 — start.** The owner's answer: start, opt-in per target.
  - **The new acknowledgement value:** `isolated-non-production-hardened-start`. The
    parameter `isolation` becomes one of two values, and the plan digest of every
    mutation-profile plan moves. No pinned digest moves.
  - **Stand-in image:** `docker.io/rancher/mirrored-pause:3.10`, pinned by index digest
    `sha256:ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a`.
    - Read 2026-09-29 with `docker buildx imagetools inspect`: linux amd64, arm64, arm/v7,
      ppc64le and s390x.
    - Entrypoint `/pause`, user `65535:65535`, no `Volumes`, no `ExposedPorts`, no
      `Healthcheck`, one layer.
    - It runs until it is stopped and needs no network, which makes it a truthful stand-in.
      It proves the loop and implements nothing.
  - **Mapping:** both reference components map to it. The high-assurance component maps to
    it too, so the shipped profile covers every catalogue component.
- 2026-09-29 **2 — smoke test.** The owner's answer: inside `apply` (2b). There is no
  contract change to the kind enums.
  - **Cost:** mutation and test are one operation, so a failed test fails the install, and
    the install compensates. The prompt's doctrine that the smoke test be "visibly separate"
    is met in the evidence instead: `test_result` items distinct from the `status` install
    items. It is not a separate operation.
- 2026-09-29 **3 — images live in the target profile.** Accepted as recommended.
  - The catalogue stays synthetic and the pinned digests stay put.
  - A locked component with no image fails `preflight.installation`.
  - The deprecated single-image pair is refused, not silently ignored: a profile carrying it
    fails with `OAK-TARGET-EXECUTION` and a message naming `component_images`.
- 2026-09-29 **4 — one operation carrying the node list.**
  - The alternative, one operation per node, would break the runner's
    unique-kind-per-plan invariant (`verification.py:392-399`), which keeps verification and
    execution from diverging. It would also need per-node dispatch.
  - **Cost:** one approval covers every node, which is right, because the user approves the
    architecture as a whole. There is one journal bracket per operation, with the node names
    recorded in it. There is one evidence item per category, with a list per node.
- 2026-09-29 **5 — a new `observation-record` schema and `observation_record` kind.**
  Accepted as recommended.
  - It is indexed under `oak.community/observation_refs`.
  - It never goes under `evaluation_refs`, which `select` and the web resolve by candidate.
- 2026-09-29 **6 — correct the assurance text now.** Accepted as recommended.
  - Only `gate_3`'s reason and `control.read-only-plan` change.
  - `evaluation.py:72` and `candidates.py:590` stay: both are still true, and changing either
    would shift more pins (`candidate_refs`, `evaluation_result_ref`).
  - The assurance plan is sealed into the signed chain before install. So "satisfying"
    `evidence.observed-calibration` is a status the observation record states, not an edit
    to the plan. With stand-in images it states `not_satisfied`, naming the four unobserved
    measures.
- 2026-09-29 **7 — container naming:** `oak-fixture-<node slug ≤ 40>-<12 hex of
  sha256(case_id \n target_id \n node_id)>`.
  - It stays inside the existing pattern.
  - The hash, not the slug, carries case and target identity, so a long target id never
    truncates a name.
  - The labels `oak.fixture=true`, `oak.case=<case id>` and `oak.node=<node id>` let adoption
    and removal prove ownership.
- 2026-09-29 **8 — web: truthfulness only.**
  - BundlePage reads `plan_signature_ref`, `approval_refs` (including `architecture`) and
    `runner_result_refs`.
  - CasePage keeps the bundle link past `bundle_compiled`.
  - No new page and no action.
  - "No runner execution authority" stays true and stays asserted.
- 2026-09-29 **9 — docker-gated tests.**
  - The real-daemon journey is skipped unless `docker info` answers (today it checks only
    for the binary).
  - The skip is documented in `docs/development.md` beside the PostgreSQL one.
  - The journey runs on the owner's machine for the exit demonstration.
- 2026-09-29 **B — `oak architecture`.** The owner's answer: a new read-only command.
  - It assembles one document from the case, the chosen (or named) candidate, the decision
    if one is recorded, and the node → image map if the case is compiled for a mutation
    target.
  - One pure function builds it. Local mode reads the workspace. Remote mode reads the two
    existing GET routes and verifies digests. No REST route is added.
- 2026-09-29 **Lifecycle.**
  - The journey reaches `deployed` with apply and rollback in *separate* dispatches.
  - A completion that applied and then rolled back leaves nothing installed. Calling it
    `deployed` would be false, so today's ingest rule stays.
  - After rollback the case stays `observing`. The next observation record states
    `installation_state: removed`. The state machine has no "rolled back" state, and adding
    one is not needed to stay truthful.
- 2026-09-29 **Test database.** The gated suites run against a throwaway container
  (`oak-s11-testpg`), not the owner's `oak-community` PostgreSQL on 15432. The integration
  suites write to the database they are given.

## Post-implementation audit

2026-09-29, after Milestone 6 and a green full gate:
- **Method.** Six read-only reviewers, one per lens: runner authority, adapter argv and isolation, approvals and lifecycle, observation honesty, compiler determinism, interface boundaries. Each finding went to one independent skeptic told to refute it (35 agents in all).
- **Result.** 29 raised, 28 survived, 1 refuted: the refuted claim was that the schema lets a measure pass without evidence; the builder and the schema's `unknown` rules already prevent it.
- **Duplicates.** Several survivors are one defect seen from two lenses (S1/S5, S4/S8, S9/S10/S21, S11/S24, S12/S17).
- **Verification.** Every survivor was checked against the code before it was fixed.
- **Tests.** Each fix has a regression test that fails without it, mutation-checked below.

| # | Lens | Severity (verified) | Finding | Fix |
|---|---|---|---|---|
| S1 | runner-authority | medium | Adopted container is started without checking that it carries the hardening flags or --network=none | `oak.isolation` label must match; configuration read back before any start (`OAK-RUNNER-ISOLATION`) |
| S2 | runner-authority | medium | A crash mid-apply is reported as a replay denial; the journal's interrupted-operation recovery is unreachable, and status says no recovery is needed | `_resume_interrupted`: journal entry, signed `manual_recovery_required` completion; `status` counts open operations |
| S3 | runner-authority | low | All dispatches in one run are verified against a single start-of-run clock, and removal has no wall-clock lease guard | per-dispatch clock (removal deliberately keeps no lease guard: taking an installation down is always allowed) |
| S4 | runner-authority | low | A container created by a `docker create` that timed out is never compensated | `_created_despite_failure` adds an owned container left by a failed create to `created` |
| S5 | adapter-argv | medium | Hardened start can run a container that was never hardened, while the evidence says it was | same as S1 |
| S6 | adapter-argv | low | registry_host treats an uppercase first path component as docker.io, but Docker treats it as a registry host, so the registry allowlist can be bypassed | `registry_host` treats an uppercase first component as a host |
| S7 | adapter-argv | low | docker stats '0B / 0B' (memory accounting unavailable) is recorded as a measured 0 bytes | `0B / 0B` (or any zero) is `None` |
| S8 | adapter-argv | low | A container whose create timed out is left out of `created`, so compensation skips it and still reports a clean rollback | same as S4 |
| S9 | approval-lifecycle | medium | A re-approved action after a revocation passes dispatch but the runner always denies it | approval identity per issuance (`.issue-<n>`) |
| S10 | approval-lifecycle | medium | A second revocation of a re-approved action corrupts the revocation set and the runner then denies every dispatch | same as S9 |
| S11 | approval-lifecycle | medium | Revoking a re-approved action with the default key silently returns the earlier revocation, and the new approval stays live | derived keys scoped to the case version for revoke too |
| S12 | approval-lifecycle | medium | Only the last dispatch's completion is accepted: an earlier completion is rejected forever and the observation then misreports install and re-apply | `oak.community/dispatch_refs`; ingest accepts any issued lease; builder scores in dispatch order |
| S13 | approval-lifecycle | low | A completion that applied and then destroyed moves the case to deployed with nothing installed | `destroy` is a removal in ingest classification |
| S14 | approval-lifecycle | low | Retrying with the same --idempotency-key after a commit now fails with OAK-IDEMPOTENCY-CONFLICT instead of returning the result | only derived keys are scoped; an explicit key retries |
| S15 | observation-honesty | high | A failed rollback or compensation that ends in manual_recovery_required scores EV-DEP-03 as pass, or as 'no rollback has run' | a removal that ended in manual recovery is a failed sample, rows or not; failing row recorded |
| S16 | observation-honesty | medium | An interrupted smoke test counts as a passed smoke test | `complete` flag; incomplete never passes (adapter and builder) |
| S17 | observation-honesty | medium | Signed completions for a superseded lease are rejected forever, so the observation silently omits failed attempts and removals | same as S12 |
| S18 | observation-honesty | low | A rollback that removed nothing counts as a passing EV-DEP-03 recovery sample | a removal of nothing is not a sample |
| S19 | observation-honesty | low | The 'older completion' path crashes on the only plan shape older runners ran, and would hide older failed installs | both plan shapes read; unattributable older failures make EV-DEP `unknown` |
| S20 | observation-honesty | low | A re-apply replaces the install's startup time with the near-zero 'startup' of an already-running container | startup only from fresh installs; `already_running` rows carry none |
| S21 | compiler-determinism | medium | A renewed approval keeps the revoked approval's id, so the runner denies it forever, and revoking it again breaks the whole revocation channel | same as S9 |
| S22 | compiler-determinism | medium | Container names and ownership labels use only case, target and node, so two workspaces for the same brief adopt and remove each other's containers | installation identity scoped by case version, target and workspace |
| S23 | compiler-determinism | low | The superseded-pair refusal also applies to read-only profiles, contrary to the CHANGELOG and the plan | superseded-pair refusal applies to mutation profiles only |
| S24 | interfaces-boundary | high | A second revoke-approval, run with the default key after a re-approval, silently revokes nothing | same as S11 |
| S25 | interfaces-boundary | low | BundlePage shows revoked approvals as 'recorded' | bundle page reads approvals: current/expired/revoked |
| S26 | interfaces-boundary | low | `oak architecture` reports expired approvals as 'recorded' next to 'Approvals needed before any install' | `absent`/`current`/`expired`/`revoked` with expiry |
| S27 | interfaces-boundary | low | Bundle page still says apply is 'unavailable in Community' and calls the plan 'read-only, unsigned' next to the new signed/installed rows | page wording corrected; assertion kept on 'no runner execution authority' |
| S28 | interfaces-boundary | low | `oak architecture` crashes with an uncaught KeyError on plans compiled by 0.7.1/0.8.0 mutation targets | superseded plan reported, no traceback |

Mutation checks on the fixes: see Progress.

## Discoveries and follow-ups

- **The runner could not pull any image on Docker Desktop (pre-existing, latent).** Its child environment was `{"PATH": os.defpath}`, but the Docker CLI still reads the operator's `~/.docker/config.json` (it finds the home directory without `HOME`); Docker Desktop writes `credsStore: desktop`, and `docker-credential-desktop` is not on `/bin:/usr/bin`, so every pull failed with "error getting credentials", even for a public image. It never surfaced because the old stand-in (`postgres:17.6-alpine`) was already cached by the operator's own Compose stack. Fixed by giving the child an empty runner-owned `DOCKER_CONFIG` (`isolated_executor`): public images pull anonymously, the operator's credentials, helpers and CLI contexts are never used, and only the default socket is reached (`RR-013`). A unit test pins the exact child environment.

- **The prompt's counts undercount.**
  - "A new kind touches nine places" undercounts (15+ sites). It no longer applies, because
    of answer 2.
  - `docs/signed-runner.md` has no approval table, only step 9.
  - No document states the runner protocol version. The six sites are five code or schema
    sites plus two signed examples.
- **The existing docker journey already runs in `make check`** wherever the `docker` binary
  exists (`tests/e2e/test_runner_journey.py:128`). It never runs `oak ingest`, so no test
  ever reached `deployed`.
- **The OAK-IMPORT-SCOPE barrier is untested**, and it only blocks file-born cases. This is
  outside this sprint; it is recorded for a follow-up.
- **REST has no test forbidding new write routes.** A cheap negative test is added in
  Milestone 7.
