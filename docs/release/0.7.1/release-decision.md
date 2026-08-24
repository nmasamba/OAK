<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.7.1

**Status: draft — not approved. Do not release against this document.**

This document is being assembled by the pre-launch hardening work
(`docs/exec-plans/active/OAK-PL-001-007-pre-launch-hardening.md`). It will hold the
evidence a maintainer needs to decide whether to declare `0.7.1` released, and will record
who signed. Until the approvals table below carries names and dates, nothing here
authorises anything.

## What is being decided

Whether to declare OAK Community `0.7.1` released: a **local-first developer release** with
no production or customer readiness claim, superseding the approved but never-published
`0.7.0`.

Explicitly *not* being decided:

- Whether to publish anywhere. Like `0.7.0`, this release publishes nothing by itself —
  not to PyPI, not to a container registry, not as a GitHub release. That is a separate
  decision.
- Anything about deploying OAK to a customer or production environment. A release approval
  is **not** a Gate 2/3 deployment approval, and no evidence here supports one.

## Why 0.7.1 exists

`0.7.0` was approved by `nmasamba` on 2026-08-22
([release-decision.md](../0.7.0/release-decision.md)) and never published. The approval
carried two standing conditions — `RR-001` and `RR-003` become P0 before any release that
permits a runner off the operator's machine or a non-fixture target. The pre-launch
hardening work closes both conditions, plus `RR-011`, `RR-032`, `RR-034`, `RR-037` and
`RR-038`, and the `RR-032` closure is a deliberate digest migration: the canonical bytes of
compiled bundles change, so the `0.7.0` record would describe a build whose digests no
longer match. Rather than reuse the version, the release is re-cut as `0.7.1` and the
`0.7.0` record stays as history.

*(To be completed before signature: the digest before/after values, the register count
reconciliation, and the evidence table below.)*

## Evidence

*(Draft — rows are filled in as the hardening milestones land; entries marked `0.7.0` are
inherited evidence that remains valid because the underlying behaviour did not change.)*

| Question | Where it is answered |
|---|---|
| Does it install on a clean machine? | Inherited from `0.7.0`: [platforms.md](../../platforms.md); `make release` installs the built wheel into a throwaway environment on every build |
| Do the artifacts reproduce? | Inherited from `0.7.0`: `make release` builds twice and compares digests. Container images do **not** reproduce (`RR-006`) |
| What changed since the `0.7.0` approval? | `CHANGELOG.md` `0.7.1` section; the exec plan's digest before/after record |
| Were the images scanned? | *(pending — rescan lands with `OAK-PL-007`)* |
| Do the images carry SBOM and provenance? | *(pending — `OAK-PL-007`)* |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md) — 38 entries with stable ids |
| Was it externally reviewed? | **No.** As for `0.7.0`, no external security review was commissioned; the wording restrictions recorded in the [`0.7.0` decision](../0.7.0/release-decision.md#external-review) apply to this release unchanged |

## Approvals required

Each of these is a named human accepting accountability for a specific judgement. None may
be self-assigned by whoever prepared this record, and none is satisfied by an agent
signature.

| Role | Approving that | Name | Date |
|---|---|---|---|
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | *(unsigned)* | — |
| Security | The residual-risk register is complete and correctly scoped, including the closures made since `0.7.0` | *(unsigned)* | — |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct | *(unsigned)* | — |
