<!-- SPDX-License-Identifier: Apache-2.0 -->

# Component-manifest extension template

1. Replace `component.yaml` with your component manifest: identity, release,
   digest-pinned artifact, per-domain licence classes, evidence with checked
   times, targets, operations, and substitutes. It must validate against
   `component-manifest.schema.json`.
2. Edit `extension.yaml`, then `oak extensions sign`, `install`, `verify`,
   `activate`. Activation governs and records the manifest — schema, payload
   digests, compatibility, licence, and steward signature — and the contract
   test kit checks it against the same rules the bundled catalogue obeys.

Scope note: activation does not yet add the manifest to the compiler's
catalogue. `LocalCatalogue` reads only the bundled `catalogue/` directory, so
an activated component-manifest extension is verified and inspectable but is
not yet offered to candidate generation. Wiring activated catalogue
extensions into compilation is deliberately deferred: it changes the
catalogue snapshot every compiled artifact is digest-bound to.
