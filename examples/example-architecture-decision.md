<!-- SPDX-License-Identifier: Apache-2.0 -->

# Example architecture decision — public-manual QA fixture

- **Status:** Draft fixture; not approved
- **Selected candidate:** `candidate-03@0.1.0`
- **Decision owner:** Unassigned

## Decision

Select the balanced local candidate for the bounded compiler fixture while retaining deterministic lexical search as the simpler baseline. This is a review decision only; observed calibration, signing, approvals and target verification remain required before any execution path could exist.

## Alternatives

| Variant | Disposition | Reason |
|---|---|---|
| Simpler baseline | Retained | Smallest reversible system and necessary comparator |
| Minimum sufficient | Retained | Feasible low-burden alternative |
| Balanced retrieval + local generation | Selected for fixture | Exercises bounded generation, evaluation and assurance contracts |
| High-assurance sovereign | Infeasible | Required accelerator compatibility is unconfirmed |

## Conditions

- Assign accountable, security and environment owners.
- Measure the target hardware rather than relying on fixture values.
- Confirm the corpus licence and provenance.
- Complete the decision-cost and EU nexus reviews.
- Treat all referenced component and bundle artifacts as synthetic.

This example demonstrates decision structure; it is not an `ArchitectureDecision` approval record.
