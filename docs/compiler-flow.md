<!-- SPDX-License-Identifier: Apache-2.0 -->

# Offline candidate and planning flow

Sprint 2 compiles a confirmed local `DesignCase` into review artifacts without contacting a provider, runner, registry, or target. All catalogue entries are synthetic fixtures; they demonstrate the contract and are not component recommendations.

## Run the reference journey

Starting after `oak init`, `oak design`, and `oak confirm` from the local-design guide:

```bash
oak candidates --output table
oak evaluate candidate-03 --output json
oak select candidate-03 --rationale-file decision.md
oak assure candidate-03 --output assurance/
oak plan candidate-03 \
  --target /path/to/OAKCommunity/examples/targets/local-fixture.yaml \
  --output bundle/
```

`candidate-00` is the simpler non-generative baseline, `candidate-01` is the minimum candidate, `candidate-03` is the balanced candidate used by the exit fixture, and `candidate-04` is the high-assurance candidate. The last candidate is deliberately infeasible because its accelerator requirement is unconfirmed. An unknown hard constraint never becomes a pass or a Pareto-frontier member.

## What each stage records

1. `candidates` validates every bounded catalogue manifest and pattern, applies licence/evidence/freshness eligibility, creates a content-addressed snapshot, expands four provider-neutral graphs, evaluates hard constraints, estimates five transparent objective ranges, and computes the feasible Pareto frontier.
2. `evaluate` runs a deterministic public fixture against the stored evaluation contract. It records pass, fail, or blocked status without selecting a candidate.
3. `select` requires a passing evaluation and records the owner, bounded rationale, alternative reasons, and dependency digests as an immutable decision.
4. `assure` links required tests, evidence, controls, owners, and gate blockers to the selected candidate and evaluation.
5. `plan` validates the non-production target profile, binds it to the command tenant, checks its declared platform/capacity and read-only capabilities against the selected candidate, and emits canonical decision, assurance, semantic, deployment-bundle, and runner-plan JSON files.

Every mutation uses the file workspace’s expected version, idempotency record, immutable objects, and append-only audit event. Repeating the same mutation returns its original result without creating another case version.

## Plan safety boundary

The emitted runner plan has status `draft`, an empty approval list, and an explicit `not_signed` marker. For a read-only target profile it contains only `inventory`, `validate`, `render`, `plan`, and `verify` operations; an acknowledged non-production mutation profile additionally receives typed `apply`, `rollback`, and `destroy` operations. Parameters are recursively schema-checked against `command`, `shell`, `executable`, and `argv` fields. No operation may mutate the target, and compilation invokes no executable, network connection, secret resolver, runner, or target API.

The target profile is invocation data, not a description of the machine running OAK. Its digest changes the semantic manifest. An undersized or incompatible platform, a mismatched tenant, or missing planning capability is rejected before publication. The bundle retains the declared-versus-required capacity, platform, network, certificate, policy, and rollback preflight evidence; certificate transport is explicitly not applicable because this sprint opens no target connection.

`deployment-bundle.json` includes human-review lifecycle procedures. Those strings are documentation, not executable input. The compiled plan is inert on its own: dispatch requires a separately signed envelope, a current digest and target bound approval, and independent runner verification. See [signed-runner.md](signed-runner.md).

## Determinism and portability

Operational timestamps and immutable case lineage can differ between clean workspaces. `semantic-manifest.json` intentionally excludes that metadata and binds the normalized intent meaning, candidate topology and objectives, component lock, target profile, and allowed operation kinds. Two clean runs with the same normalized inputs produce byte-equivalent semantic manifests.

The entire workspace remains exportable through `oak export`. Import revalidates every new compiler artifact, digest, canonical reference, case pointer, idempotency record, and audit event before publishing the imported workspace.

## Failure and recovery

- Invalid, aliased, oversized, stale, restricted, incomplete, or symlinked catalogue/target inputs fail before publication.
- Candidate generation is denied until every blocking question is resolved or explicitly accepted through the confirmation contract.
- Infeasible and unevaluated candidates cannot be selected.
- A second evaluation cannot overwrite an immutable result; an exact retry returns the original result, while a new key is denied until a successor candidate exists.
- A target with the wrong tenant, insufficient capacity, incompatible platform, or incomplete operation permissions cannot be compiled.
- A stale expected version returns `OAK-EXPECTED-VERSION`; a reused key with different normalized input returns `OAK-IDEMPOTENCY-CONFLICT`.
- Output directories must not exist. Canonical files are written to a temporary sibling and renamed only after all files are complete.
- If output publication fails after the workspace commit, repeat the same command with the same input to retrieve the idempotent result and write a new output directory.

Compilation itself still has no target-access path, so no compiler failure requires target cleanup; runner-side failures are journaled and use typed rollback or an explicit manual-recovery state.
