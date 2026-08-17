<!-- SPDX-License-Identifier: Apache-2.0 -->

# Examples

These fixtures are synthetic and non-production. They demonstrate serialization and validation; they do not approve a use case, component, legal conclusion, architecture or deployment.

The reference scenario is a read-only, cited-answer service over public technical manuals on a local single node. Empty fields and unresolved questions are deliberate because the real target brief is unknown.

Key build fixtures:

- `briefs/public-manual-qa.yaml` and its answer file drive the offline Community end-to-end journey;
- `example-design-case.yaml` proves every interface shares one versioned aggregate;
- `example-runner-plan.yaml` proves planning uses signed typed operations and contains no arbitrary command;
- `targets/local-fixture.yaml` permits inventory/render/plan only and is never a production target.
