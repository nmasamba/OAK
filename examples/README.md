<!-- SPDX-License-Identifier: Apache-2.0 -->

# Examples

These fixtures are synthetic and non-production. They demonstrate serialization and validation; they do not approve a use case, component, legal conclusion, architecture or deployment.

The reference scenario is a read-only, cited-answer service over public technical manuals on a local single node. Empty fields and unresolved questions are deliberate because the real target brief is unknown.

Key build fixtures:

- `briefs/public-manual-qa.yaml` and its answer file drive the offline Community end-to-end journey;
- `example-design-case.yaml` proves every interface shares one versioned aggregate;
- `example-catalogue-snapshot.yaml`, `example-architecture-pattern.yaml`, and `example-architecture-candidate.yaml` show governed candidate inputs and outputs;
- `example-evaluation-result.yaml`, `example-architecture-decision.yaml`, and `example-assurance-plan.yaml` show immutable review lineage;
- `example-runner-plan.yaml` demonstrates the canonical signed-plan schema shape and contains no arbitrary command;
- `targets/local-fixture.yaml` permits only inventory, validate, render, plan, and verify operations and is never a production target;
- `example-webhook-envelope.yaml` is a really-signed portal event envelope whose publisher key is pinned in `portal/webhook-publisher.identity.json`.

The executable Sprint 2 fixture uses `candidate-00` as the simpler baseline and `candidate-03` as the selected balanced candidate. Its generated runner plan remains unsigned and unapproved; the standalone signing example demonstrates only schema shape.

## Interface and portal starters

- `portal/` holds the signed webhook envelope contract for portals and CI: the pinned
  publisher identity (public key only — the private half was generated in a throwaway
  process and discarded) and the verification, deduplication, and ordering rules a consumer
  must apply. Verify an envelope with
  `oak validate webhook example-webhook-envelope.yaml --public-key portal/webhook-publisher.identity.json`;
  Community ships no webhook dispatcher.
- `backstage/` holds a developer-portal starter — a catalogue entity over the committed
  OpenAPI contract, a software template that creates a draft design case, and the proxy
  fragment that forwards only the documented command headers. It uses documented REST
  behavior and links only; a contract test pins every referenced path to
  `openapi/oak.openapi.json`, no Backstage type appears in the core, and no portal
  integration can create an approved state.
