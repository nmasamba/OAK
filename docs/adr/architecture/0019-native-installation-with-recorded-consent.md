<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from OAK's original spec repo, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0019: Install the chosen architecture natively, after a signed consent, and stop it once it is proven

- Status: Accepted
- Date: 2026-11-02
- Owners: @architecture, @security, @operations
- Requirement IDs: OAK-FR-DEP-003, OAK-FR-DEP-004, OAK-FR-DEP-005, OAK-FR-IMP-001, OAK-NFR-SEC-001–004
- Amends: ADR-0017 (adds a second installation mode beside the container one; changes none of its rules)

## Context

ADR-0017 installs the selected candidate as one hardened container per node. That needs Docker,
and it isolates each process so far (no network, a read-only root, no capabilities, resource
ceilings) that a real serving harness could not do its work. The owner's definition of native
installation, in `sprints.md`: the user downloads the architecture to their machine instead of
using Docker, once they have approved installation, on two platforms, with the security
requirements relaxed because the user has given permission and the risks have been explained.

At Tier 3 Batch B's kickoff on 2026-11-02 the owner chose: three platforms (macOS on Apple
silicon, Linux x86_64, Linux aarch64); only ADR-0017's container isolation set relaxes; the
shipped profile installs a stand-in that `make check` runs offline, plus a documented example
for one real harness and one small model rehearsed by hand, with a real catalogue component
after 1.0; and no supervision: "After the install process is complete, the service should shut
down until launched again by the user. The point is to get a suitable AI system installed for
the user, and no more".

The security invariants forbid "downloaded executable selection" in a runner adapter. A native
install runs an executable the runner downloaded, so this record amends that rule explicitly
rather than letting the mode contradict it silently.

## Decision

- **A second mode, chosen by the target profile.**
  - A profile opts in with the acknowledgement `native-non-production-user-consented` and maps
    each catalogue component it may install to a **harness kind** the runner's native adapter
    knows, with typed parameters and nothing else: the artifacts (each a source, its SHA-256,
    its size and its format), a loopback listen port and a health-probe path. No document
    carries a command, an argument vector, an executable path or a shell: the argument
    template lives in the adapter, per harness kind.
  - Two harness kinds ship. `oak_stand_in` is a small HTTP server inside OAK, run through the
    runner's own interpreter, so the whole native path runs offline on every CI platform with
    nothing downloaded. `llama_cpp_server` is llama.cpp's `llama-server` from a release
    archive with one GGUF model file. A new kind is a code change with its own review.
  - Only binary releases of kinds OAK has typed can be installed natively; nothing a package
    manager would resolve (pip, apt, Homebrew).
- **What relaxes: ADR-0017's container isolation set, and nothing else.** A native process runs
  as the user, outside any container: it has the user's network (it is bound to loopback, but
  it can open connections), it can write wherever the user can, it has the user's privileges,
  and only three ceilings apply while the runner checks it: no core files, a bounded
  number of open files and a bounded size for any file it writes. Memory, CPU time and the
  number of processes are not limited, because a limit on them would break a model server
  or count the user's other processes; the runner records both lists.
- **What stays**, because it protects the user from a poisoned bundle and from OAK itself rather
  than from their own choice:
  - the signed plan bound to the bundle digest and the target;
  - the `architecture` and `apply` approvals of ADR-0017, and a third signed approval for the
    action `native_consent`, which names the consent document by digest, every relaxed control
    by its id, and the digest of what `apply` installs. The runner refuses a native install
    without a current consent, with one for another installation, or with a list of relaxed
    controls that differs from the adapter's own;
  - typed operations with fixed argument vectors and no shell;
  - every artifact fetched only over HTTPS from a host the profile acknowledges
    (`execution.allowed_download_hosts`), each redirect checked against the same list, its size
    and SHA-256 verified before anything executes, written into a runner-owned directory with
    modes the runner sets, and unpacked without following a link, an absolute path or `..`;
  - an ownership marker in each installation, and a refusal to stop or remove anything the
    runner did not install;
  - the journal before and after each side effect;
  - the smoke test inside `apply`, after which the process is **stopped**: no unit file, no
    agent, nothing left running. The runner tells the user how to start it;
  - a tested uninstall that removes exactly what the install created.
- **The consent is a record, not a checkbox.** Its text is a document in the catalogue,
  `consent/native-installation.yaml`, validated by `native-consent.schema.json`, naming each
  relaxed control and its risk; the CLI shows it before `oak approve native_consent`, and the
  web workspace before the install approval. The owner signs off its text.
- **The security invariant is amended, not bypassed.** The runner may run an executable it
  downloaded only in this mode, and only when its digest is acknowledged in the target profile
  the signed plan was compiled against, it is verified before any execution, it sits in a
  runner-owned directory with modes the runner set, and the harness kind fixes which file runs
  and with which arguments.
- **Observation reuses the smoke test.** `oak observe` on a native installation starts it,
  probes it and stops it, recording what it measured beside the predictions, as ADR-0017's
  observation does.

## Alternatives

- **Docker only.** Rejected by the owner's direction: a user without Docker gets nothing.
- **A supervised service** (a `launchd` agent or a `systemd --user` unit). Rejected by the owner
  (Q4d): the point is to install a suitable system, not to run one.
- **Installing through a package manager.** Rejected: the resolution of transitive packages is
  outside OAK's control and could not be pinned by digest in a signed plan.
- **A real harness in the curated catalogue now.** Deferred by the owner to after 1.0: it moves
  every reference digest, as ADR-0017 noted.
- **An unsigned consent.** Rejected: the consent must be bound to what will run and checkable
  by the runner, like every other approval.

## Consequences

- **New residual risks.** A native process runs with the user's privileges and network while
  it is smoke-tested and whenever the user starts it; a downloaded harness is trusted as far
  as its acknowledged digest; on macOS, Gatekeeper and code signing decide whether a
  downloaded binary runs at all, which the rehearsal verifies before `platforms.md` claims it.
  The register records each; `RR-043` covers containers only.
- **Three platforms, one stand-in.** CI proves the native path on macOS on Apple silicon and on
  both Linux architectures with the stand-in; a real harness is proven by hand on the owner's
  machine, with its digests recorded.
- **More approvals before a native install.** `oak approve native_consent` joins
  `oak approve architecture` and `oak approve apply`.

## Evidence and validation

Unit and integration tests for every refusal (a digest or size mismatch, an archive member
that escapes or links, a host or redirect the profile does not name, a foreign process, a
consent for another installation or with another list of controls); the native journey in
`make check` on all three CI jobs; an uninstall proven with a canary file beside the
installation; the rehearsal of the example profile, recorded with its digests.

## Revisit triggers

- A non-loopback bind, a supervised service, or a harness kind installed through a package
  manager is proposed.
- A non-local target, or GPU access for the container mode, is proposed.
- A real harness enters the curated catalogue.

Any of these needs a new decision. None may drop the signed consent, the verified download or
the tested uninstall.
