<!-- SPDX-License-Identifier: Apache-2.0 -->

# Schema catalogue

All schemas use JSON Schema Draft 2020-12. YAML examples are parsed to the equivalent JSON data model before validation.

| Schema | Canonical object | Example |
|---|---|---|
| `design-case.schema.json` | `DesignCase` workspace aggregate | `examples/example-design-case.yaml` |
| `system-intent.schema.json` | `SystemIntentSpec` | `examples/example-intent.yaml` |
| `decision-cost-model.schema.json` | `DecisionCostModel` | `examples/example-decision-cost-model.yaml` |
| `regulatory-nexus.schema.json` | `RegulatoryNexus` | `examples/example-regulatory-nexus.yaml` |
| `regulatory-profile.schema.json` | `RegulatoryProfile` | `examples/example-eu-regulatory-profile.yaml` |
| `obligation-control-mapping.schema.json` | `ObligationControlMapping` | `examples/example-obligation-control-mapping.yaml` |
| `evaluation-contract.schema.json` | `EvaluationContract` | `examples/example-evaluation-contract.yaml` |
| `component-manifest.schema.json` | `ComponentManifest` | `examples/example-component.yaml` |
| `architecture-candidate.schema.json` | `ArchitectureCandidate` | `examples/example-architecture-candidate.yaml` |
| `deployment-bundle.schema.json` | `DeploymentBundle` | `examples/example-deployment-bundle.yaml` |
| `runner-plan.schema.json` | `RunnerPlan` typed execution plan | `examples/example-runner-plan.yaml` |
| `change-proposal.schema.json` | `ChangeProposal` | `examples/example-change-proposal.yaml` |

`common.schema.json` contains shared identifiers, evidence, provenance, constraints, approvals and artifact references.

`DesignCase` and `RunnerPlan` begin at object schema version `0.4.0`; existing `0.3.0` canonical artifacts retain their own version until a breaking/additive migration is deliberately defined. Repository version and individual object schema versions are related but not assumed identical.

`DeploymentBundle.procedures` contains human-review lifecycle descriptions. It is never executable input. The runner accepts only a `RunnerPlan` operation whose kind and adapter parameters validate against pinned schemas; command/shell fields are absent by design.

## Provenance convention

`SystemIntentSpec.spec` is typed normally. `provenance` is a map from an RFC 6901-style JSON Pointer to a provenance record. The repository validator requires one record for every populated scalar leaf in `spec`; production OAK MUST enforce the same invariant transactionally. A pointer to an array element uses its index, for example `/spec/purpose/desired_outcomes/0`.

## Compatibility

- Additive optional fields are compatible within a major schema version.
- New required fields, changed meanings, enum removals and state changes are breaking.
- Unknown provider/target fields belong under `extensions` with a namespaced key.
- `additionalProperties: false` is deliberate for normative objects.
- An `unknown` value does not satisfy a gate; it only makes uncertainty machine-visible.
