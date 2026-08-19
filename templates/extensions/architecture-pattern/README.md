<!-- SPDX-License-Identifier: Apache-2.0 -->

# Architecture-pattern extension template

1. Replace `pattern.yaml` with your pattern: unique variant, roles with
   component categories and required capabilities, edges, one component
   requirement per role, and hard requirements. It must validate against
   `architecture-pattern.schema.json`; the catalogue compiler additionally
   cross-checks every role against real component manifests.
2. Edit `extension.yaml`, then `oak extensions sign`, `install`, `verify`,
   `activate`.

Scope note: activation does not yet add the pattern to the compiler's
catalogue. `LocalCatalogue` reads only the bundled `catalogue/` directory, so
an activated architecture-pattern extension is verified and inspectable but is
not yet offered to candidate generation. Wiring activated catalogue extensions
into compilation is deliberately deferred: it changes the catalogue snapshot
every compiled artifact is digest-bound to.
