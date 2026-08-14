<!-- SPDX-License-Identifier: Apache-2.0 -->

# Example architecture decision — public-manual QA fixture

- **Status:** Draft fixture; not approved
- **Selected candidate:** `candidate.public-manual-qa.minimum@0.1.0`
**Decision owner:** Unassigned

## Decision

Use the deterministic lexical-search candidate as the initial baseline. Do not add a foundation model until the baseline has been measured and a generated-synthesis candidate demonstrates a material user-outcome gain without violating citation correctness, no-egress, licence or latency constraints.

## Alternatives

| Variant | Disposition | Reason |
|---|---|---|
| Minimum sufficient | Provisionally selected | Smallest reversible system and necessary comparator |
| Balanced retrieval + local generation | Deferred | Model, hardware, licence and measured quality are unknown |
| High-assurance sovereign | Infeasible to assess | No real sovereignty, availability, hardware or organization brief |

## Conditions

- Assign accountable, security and environment owners.
- Measure the target hardware rather than relying on fixture values.
- Confirm the corpus licence and provenance.
- Complete the decision-cost and EU nexus reviews.
- Treat all referenced component and bundle artifacts as synthetic.

This example demonstrates decision structure; it is not an `ArchitectureDecision` approval record.
