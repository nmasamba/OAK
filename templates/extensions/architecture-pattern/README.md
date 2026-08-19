<!-- SPDX-License-Identifier: Apache-2.0 -->

# Architecture-pattern extension template

1. Replace `pattern.yaml` with your pattern: unique variant, roles with
   component categories and required capabilities, edges, one component
   requirement per role, and hard requirements. It must validate against
   `architecture-pattern.schema.json`; the catalogue compiler additionally
   cross-checks every role against real component manifests.
2. Edit `extension.yaml`, then `oak extensions sign`, `install`, `verify`,
   `activate`.
