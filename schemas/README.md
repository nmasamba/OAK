<!-- SPDX-License-Identifier: Apache-2.0 -->

# Schema catalogue

All schemas use JSON Schema Draft 2020-12. YAML examples are parsed to the equivalent JSON data model before validation.

| Schema | Canonical object | Example |
|---|---|---|
| `design-case.schema.json` | `DesignCase` workspace aggregate | `examples/example-design-case.yaml` |
| `workspace-manifest.schema.json` | Atomic local workspace pointer and artifact index | `examples/example-workspace-manifest.yaml` |
| `source-record.schema.json` | Quarantined source metadata | `examples/example-source-record.yaml` |
| `audit-event.schema.json` | Append-only local command lineage | `examples/example-audit-event.yaml` |
| `confirmation-answers.schema.json` | Bounded confirmation input | `examples/briefs/public-manual-qa-answers.yaml` |
| `interpretation-proposal.schema.json` | Untrusted provider-neutral claim proposal | `examples/example-interpretation-proposal.yaml` |
| `system-intent.schema.json` | `SystemIntentSpec` | `examples/example-intent.yaml` |
| `decision-cost-model.schema.json` | `DecisionCostModel` | `examples/example-decision-cost-model.yaml` |
| `regulatory-nexus.schema.json` | `RegulatoryNexus` | `examples/example-regulatory-nexus.yaml` |
| `regulatory-profile.schema.json` | `RegulatoryProfile` | `examples/example-eu-regulatory-profile.yaml` |
| `obligation-control-mapping.schema.json` | `ObligationControlMapping` | `examples/example-obligation-control-mapping.yaml` |
| `evaluation-contract.schema.json` | `EvaluationContract` | `examples/example-evaluation-contract.yaml` |
| `component-manifest.schema.json` | `ComponentManifest` | `examples/example-component.yaml` |
| `catalogue-snapshot.schema.json` | Eligible and rejected manifest snapshot | `examples/example-catalogue-snapshot.yaml` |
| `architecture-pattern.schema.json` | Provider-neutral candidate pattern | `examples/example-architecture-pattern.yaml` |
| `architecture-candidate.schema.json` | `ArchitectureCandidate` | `examples/example-architecture-candidate.yaml` |
| `evaluation-result.schema.json` | Digest-linked deterministic evaluation | `examples/example-evaluation-result.yaml` |
| `architecture-decision.schema.json` | Immutable selected-candidate decision | `examples/example-architecture-decision.yaml` |
| `assurance-plan.schema.json` | Test, evidence, control, owner and blocker plan | `examples/example-assurance-plan.yaml` |
| `target-profile.schema.json` | Non-production compile target input | `examples/targets/local-fixture.yaml` |
| `review-artifact.schema.json` | Semantic/supply-chain review artifact | `examples/example-review-artifact.yaml` |
| `deployment-bundle.schema.json` | `DeploymentBundle` | `examples/example-deployment-bundle.yaml` |
| `runner-plan.schema.json` | `RunnerPlan` typed execution plan | `examples/example-runner-plan.yaml` |
| `change-proposal.schema.json` | `ChangeProposal` | `examples/example-change-proposal.yaml` |
| `plan-signature.schema.json` | Signed binding over a compiled plan and bundle digest | `examples/example-plan-signature.yaml` |
| `approval.schema.json` | Digest, target, action and expiry bound apply authorization | `examples/example-approval.yaml` |
| `runner-envelope.schema.json` | Signed outbound dispatch envelope and lease | `examples/example-runner-envelope.yaml` |
| `runner-message.schema.json` | Runner protocol message | `examples/example-runner-message.yaml` |
| `policy-pack.schema.json` | Effective-dated, scoped, self-testing governed rule pack | `examples/example-policy-pack.yaml` |
| `policy-decision.schema.json` | Engine-neutral canonical policy decision | `examples/example-policy-decision.yaml` |
| `extension-manifest.schema.json` | Governed extension identity, payload digests and compatibility | `examples/example-extension-manifest.yaml` |
| `extension-activation.schema.json` | Record of a verified, explicitly activated extension | `examples/example-extension-activation.yaml` |
| `webhook-envelope.schema.json` | Signed portable audit-event wrapper for portal and CI consumers | `examples/example-webhook-envelope.yaml` |

`common.schema.json` contains shared identifiers, evidence, provenance, constraints, approvals and artifact references.

Object schema versions are per-object and are deliberately not aligned to one number: twelve schemas (including `design-case`, `runner-plan`, `audit-event`, `architecture-decision`, `assurance-plan`, and `catalogue-snapshot`) pin `0.4.0`, ten (including `system-intent`, `deployment-bundle`, `architecture-candidate`, and `component-manifest`) remain at `0.3.0`, and the schemas introduced from Sprint 5 onward (`plan-signature`, `approval`, `runner-envelope`, `runner-message`, `policy-pack`, `policy-decision`, `extension-manifest`, `extension-activation`, `webhook-envelope`) start at `0.1.0`. Each object retains its own version until a breaking or additive migration is deliberately defined; the repository version and the object schema versions are related but never assumed identical. [Compatibility rules for changing any of them are in ../docs/compatibility.md](../docs/compatibility.md).

`DeploymentBundle.procedures` contains human-review lifecycle descriptions. It is never executable input. The runner accepts only a `RunnerPlan` operation whose kind and adapter parameters validate against pinned schemas; command/shell fields are absent by design.

## Provenance convention

`SystemIntentSpec.spec` is typed normally. `provenance` is a map from an RFC 6901-style JSON Pointer to a provenance record. The repository validator requires one record for every populated scalar leaf in `spec`; production OAK MUST enforce the same invariant transactionally. A pointer to an array element uses its index, for example `/spec/purpose/desired_outcomes/0`.

## Compatibility

- Additive optional fields are compatible within a major schema version.
- New required fields, changed meanings, enum removals and state changes are breaking.
- Unknown provider/target fields belong under `extensions` with a namespaced key.
- `additionalProperties: false` is deliberate for normative objects.
- An `unknown` value does not satisfy a gate; it only makes uncertainty machine-visible.
