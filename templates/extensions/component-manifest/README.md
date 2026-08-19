<!-- SPDX-License-Identifier: Apache-2.0 -->

# Component-manifest extension template

1. Replace `component.yaml` with your component manifest: identity, release,
   digest-pinned artifact, per-domain licence classes, evidence with checked
   times, targets, operations, and substitutes. It must validate against
   `component-manifest.schema.json`.
2. Edit `extension.yaml`, then `oak extensions sign`, `install`, `verify`,
   `activate`. Catalogue eligibility still applies its own policy: a
   quarantined or stale manifest is rejected at compile time with
   machine-readable reasons.
