<!-- SPDX-License-Identifier: Apache-2.0 -->

# Reference case compared with 0.8.0 — OAK Community 0.9.0

The release checklist asks for reference-case byte-stability to be "verified directly
against the previous mainline". `0.9.0` carries one declared digest shift, so the useful
question is narrower: **did anything move apart from the change that was declared?**

## Method

On 2026-09-30, the reference case was compiled twice with the repository's own harness
(`tests/runner_support.py::build_compiled_case`, the fixed clock `2026-08-18T12:00:00Z` and
fixed idempotency keys): once in a worktree at `v0.8.0` (`d9762dc`), and once at
`d5717de` on the release branch. Every artifact that each workspace indexed was then
compared by digest, and every artifact that differed was compared by content.

## Result

Both workspaces index the same **43** artifacts under the same kinds, ids and versions,
and both end at `design-case.public-manual-qa@0.1.7`.

- **35 are byte-identical.** They include `candidate-03` (`576b0ca6…`), the semantic
  manifest (`2ef34758…`) and both intent versions.
- **8 differ.** Only one of them differs in content: the assurance plan
  `assurance.candidate-03`, in exactly the three strings the changelog declares.

  | Field | `0.8.0` | `0.9.0` |
  |---|---|---|
  | `control.read-only-plan` description | Limit Sprint 2 runner operations to typed non-mutating planning phases. | Run only typed runner operations; an install needs a signed plan, a separate architecture approval and an apply approval, each verified again by the runner. |
  | `evidence.observed-calibration` description | Collect observed target cost, latency, quality and energy before deployment. | Observe target cost, latency, quality and energy under a representative workload before any production deployment decision. |
  | `gate_3` reason | Observed calibration, signing, approvals and runner verification are not implemented. | Observed cost, latency, quality and energy under a representative workload are still missing. |

- **The other 7 differ only in digests that carry that change forward.** The provenance
  review artifact records the assurance digest. The bundle records the provenance
  artifact's digest. The runner plan records the bundle's digest and the digest of case
  `0.1.6`. Both case versions and the two audit events record digests of the artifacts
  above them, and their audit hash chain. No other field of any of these seven changed.

| Artifact | `0.8.0` | `0.9.0` |
|---|---|---|
| `assurance_plan` `assurance.candidate-03` | `sha256:7431881d…` | `sha256:c01f5f83…` |
| `review_artifact` `provenance.candidate-03` | `sha256:f0db8126…` | `sha256:fbc50ea9…` |
| `deployment_bundle` | `sha256:570abb66…` | `sha256:9da17d02…` |
| `runner_plan` | `sha256:fad30959…` | `sha256:03c4541a…` |
| `design_case` `0.1.6` | `sha256:d092a51a…` | `sha256:ce08eb93…` |
| `design_case` `0.1.7` | `sha256:f54f3419…` | `sha256:61cee339…` |
| `audit_event` 7 | `sha256:d9181218…` | `sha256:62d0e11b…` |
| `audit_event` 8 | `sha256:d0f052bd…` | `sha256:45585344…` |

The pinned values in `tests/integration/test_reference_digests.py` are the bundle, the
runner plan, the case at `0.1.7`, the candidate, the semantic manifest and the two intent
versions. Their movement matches the table and the before-and-after values in
`CHANGELOG.md` exactly.

## What this does not show

It compares the deterministic reference journey against `target.local-fixture`, which is
read-only. Plans compiled for a mutation-capable target change shape in `0.9.0` (container
adapter `0.2.0`, a node list, an installation identity), and that change is declared as
breaking in `CHANGELOG.md`. It is not a byte-stability question.
