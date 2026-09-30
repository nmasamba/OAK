<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0017: Install the chosen architecture only after two approvals, and start it only where the operator acknowledges it

- Status: Accepted
- Date: 2026-09-29
- Owners: @architecture, @security, @operations
- Requirement IDs: OAK-FR-DEP-003, OAK-FR-DEP-004, OAK-FR-DEP-005, OAK-FR-ARC-006, OAK-FR-IMP-001, OAK-NFR-SEC-001–004

## Context

Through Sprint 10 the signed runner could mutate one thing on the acknowledged non-production local target. It created a single network-isolated container from the target profile's own stand-in image, and it never started it. That proved the signed path, but it did not install the architecture the user chose. Nothing tested an installation, and nothing compared a prediction with an observation.

Sprint 11 closes that loop on the local target. That means OAK starts a process on the operator's machine from an image the operator names. On 2026-09-29 the owner set two conditions. Nothing is installed until the user has approved the architecture and the installation step, separately. And a user who wants only the design can stop there.

## Decision

- **Two signed approvals before any install.**
  - An `architecture` approval, signed in the approver role, binds the plan, bundle and target like every approval. It also names:
    - the architecture decision;
    - the selected candidate;
    - the digest of what `apply` would install.
  - `apply` cannot be approved without a current architecture approval.
  - Dispatch sends both approvals.
  - The runner verifies both independently. It refuses an install whose architecture approval names a different decision or installation.
  - Removal (`rollback`, `destroy`) never needs the architecture approval, so an installation can always be taken down.
- **Install exactly the chosen topology.**
  - One container per node of the selected candidate that has a component.
  - Each container's image is the digest-pinned image the operator acknowledges for that component in the target profile (`execution.component_images`). A component without one fails compile-time preflight, and nothing falls back to another image.
  - Names derive from the installation — the case version, the workspace that compiled it and the target — and the node; labels carry the same identity.
  - Before anything is adopted or started, the runner reads each container's configuration back from the daemon and refuses one whose network or hardening does not match what was approved.
  - Apply adopts only its own labelled, digest-matching container and denies a foreign one.
  - A failed apply removes exactly what it created. Removal touches only owned containers and proves absence afterwards.
- **Start only on acknowledgement.**
  - A target profile opts in to starting with the acknowledgement `isolated-non-production-hardened-start`. Profiles acknowledging only the fixture keep never-started containers.
  - A started container runs with a fixed set of flags that are part of the adapter identity:
    - no network, a read-only root, no capabilities and no new privileges;
    - an unprivileged user;
    - memory, CPU and process ceilings;
    - no restart policy and no log driver;
    - no volumes, environment or ports.
  - Its smoke test is part of `apply`: running (or healthy) within a bounded wait and still running after a settle.
  - The runner never runs `exec`, never reads logs, publishes no port and opens no network client.
  - The Docker client runs with an empty, runner-owned configuration, so the operator's registry credentials, helpers and CLI contexts are never used.
- **Observe, record, propose nothing.** `oak observe` writes an immutable observation record, built only from signed runner completions the control plane accepted. It puts deployment measures and, for every prediction, an observed value or `unknown` with a reason, beside the prediction. It moves the case to `observing`. It feeds nothing back into a dispatch, an approval or the runner.
- **The design is a stopping point.** `oak architecture` prints the chosen architecture and writes nothing, so a user who wants only the design needs no approval and installs nothing.

## Alternatives

- **Treat candidate selection as the architecture approval.**
  - Rejected. Selection is an unsigned design decision, reachable over REST and the web.
  - An install consent must be signed, bound to what will run, and independently checkable by the runner.
- **Record the architecture approval before compilation.**
  - Rejected. The approval would need a new schema.
  - More importantly, it could not name the images, which are known only once the plan is compiled against a target.
- **Keep containers never-started.**
  - Retained as the default for profiles that do not opt in.
  - Not sufficient on its own: a smoke test of a process that never ran says little.
- **A separate `test` operation kind.**
  - Deferred by the owner. It would change a closed enum in three schemas and several code tables.
  - The smoke test's evidence is kept separate from the install's instead.
- **Real component images in the catalogue.**
  - Rejected for now. It moves every pinned digest, and the catalogue's components are synthetic.
  - The target profile carries the operator's acknowledgement instead.

## Consequences

- **A new residual risk.** A process from an acknowledged image runs on the operator's machine (`RR-043`).
- **The image choice is the operator's.** The hardening bounds what the image can reach, but not what it computes. The shipped profiles use one tiny stand-in image. It proves the install, test and remove loop and implements no component.
- **Calibration is mostly `unknown`.** No request workload runs. Observing cost, latency, quality and energy needs a representative workload and human review, which is future work.
- **An extra command before install.** Install scripts now need `oak approve architecture` before `oak approve apply`.

## Revisit triggers

- A request workload or probe is proposed.
- A non-local target is proposed.
- A container registry that OAK itself publishes to is proposed.
- The hardening set must change for an image to run.

Any of these needs a new decision. None may relax the two-approval rule or let an observation promote anything.
