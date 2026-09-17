<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.7.1

**Status: approved by `nmasamba` on 2026-08-27, all three roles.**

This document assembles the evidence a maintainer needs to decide whether to declare
`0.7.1` released, and records who signed. It was prepared by the pre-launch hardening
work (`docs/exec-plans/completed/OAK-PL-001-007-pre-launch-hardening.md`); the person or
agent who prepared it is not in a position to approve it, and has not.

## What is being decided

Whether to declare OAK Community `0.7.1` released: a **local-first developer release**
with no production or customer readiness claim, superseding the approved but
never-published `0.7.0`.

Explicitly *not* being decided:

- Whether to publish anywhere. Like `0.7.0`, this release publishes nothing by itself —
  not to PyPI, not to a container registry, not as a GitHub release. That is a separate
  decision.
- Anything about deploying OAK to a customer or production environment. A release
  approval is **not** a Gate 2/3 deployment approval, and no evidence here supports one.

## Why 0.7.1 exists

`0.7.0` was approved by `nmasamba` on 2026-08-22
([release-decision.md](../0.7.0/release-decision.md)) and never published. The approval
carried two standing conditions — `RR-001` and `RR-003` become P0 before any release
that permits a runner off the operator's machine or a non-fixture target. The pre-launch
hardening closed both conditions, plus `RR-011`, `RR-032`, `RR-034`, `RR-037` and
`RR-038`, while nothing published bound the compatibility promises. The `RR-032` closure
is a deliberate digest migration: the canonical bytes of compiled bundles changed, so
the signed `0.7.0` record describes a build whose digests no longer match. Rather than
reuse the version, the release was re-cut as `0.7.1` and the `0.7.0` record stays as
history.

**The digest migration, precisely.** At reference case `0.1.7`:

| Document | `0.7.0` (approved, unpublished) | `0.7.1` |
|---|---|---|
| `deployment_bundle` | `sha256:042313be7ccd8355cfb7eb21b67b3137bc897cbe92d0d77c2f8189a8f9175c00` | `sha256:570abb66ee53eb6433588b865fb4a77dc4d5d7133bc1275fbe433a9a37936596` |
| `runner_plan` | `sha256:5e0a65ba9c1f17945c5100c5532c890806e71bed4c0c40c5e7099a97d4f459dc` | `sha256:fad309590f1d09da0019f52dce9bd3d31da5b6285f5246d899657a8f161e18c4` |
| `selected_candidate` | `sha256:576b0ca62835a521439e44b280ffdfca79438323d45ae79e70521a27d14118b3` | unchanged — recompiled on both sides, byte-identical |
| `semantic_manifest` | `sha256:2ef34758128e13038d26b82847589b2b0ec2c5f25ba6ba56982a520a92a34d63` | unchanged — recompiled on both sides, byte-identical |

The blast radius is exactly the two documents that embed the corrected content, called
out in `CHANGELOG.md` as [compatibility.md](../../compatibility.md) rule 4 requires. No
schema shape changed; stored workspaces remain valid and importable.

## What changed since the 0.7.0 approval

Seven register entries closed, each with adversarial tests; no other code, contract,
schema or canonical surface moved:

- **`RR-001`** — revocation notices are signed (`approver` role, `revocation.schema.json`)
  and a signed revocation manifest inventories the complete set with a monotonic,
  runner-recorded sequence; the channel fails closed, and deleting a notice — one file,
  the whole set, or a rollback to an older signed state — no longer restores an
  approval. The manifest was added after the plan's closing audit refuted the first
  fix's claim; the audit record in the exec plan has the full history.
- **`RR-003`** — post-create resolved-digest verification (`OAK-RUNNER-IMAGE`) and a
  target-profile registry allowlist (`OAK-RUNNER-REGISTRY`); TM-08 moved to **direct**
  in [threat-coverage.md](../../security/threat-coverage.md).
- **`RR-032` + `RR-011`** — the compiled verification policy is target-derived and its
  clauses are enforced before any adapter exists (`OAK-RUNNER-POLICY`); the stale
  `not_signed` reason is corrected. This is the digest migration above.
- **`RR-034`** — pnpm provisions the pinned Node (`devEngines.runtime`) and
  `make toolchain-check` fatally compares the running binaries against the pins.
- **`RR-037`** — the web image runs unprivileged (uid 101, verified in the running
  container) and Compose applies `cap_drop`/`no-new-privileges`/read-only/limits.
- **`RR-038`** — per-image CycloneDX SBOMs and unsigned provenance, generated locally
  and in the release workflow.

The runner protocol tightened accordingly (signed revocations; three new denial paths).
Nothing was published under the old protocol, so no deprecation window was owed;
[compatibility.md](../../compatibility.md) now states the publication-boundary reading
explicitly.

After the hardening merged, a documentation-only final sweep added the illustrated user
manual ([docs/manual/](../../manual/)), neutralized the AI-vendor names in the completed
exec plans' author descriptions, and brought the manual's HTML source under the
document-policy gates. It touched no code path a release artifact is built from except
those gates and the configuration-reference test, and the four reference digests above
were re-verified by direct recompilation afterwards — byte-identical.

## Evidence

| Question | Where it is answered |
|---|---|
| Does it install on a clean machine? | Inherited from `0.7.0`: [platforms.md](../../platforms.md); `make release` installs the built wheel into a throwaway environment on every build. The wheel path is unchanged by this work |
| Does the artifact that ships actually work? | `tests/e2e/test_installed_wheel.py`, unchanged; the full gate ran green on every hardening milestone (final: 419 unit/contract + 191 integration + 42 e2e, PostgreSQL suites enabled) |
| Do the artifacts reproduce? | Inherited from `0.7.0`: `make release` builds twice and compares digests. Container images do **not** reproduce (`RR-006`) |
| Were the images scanned? | **Yes, re-scanned at `0.7.1`** after the web base change: zero fixable findings; the web image reports no findings at any severity; the API residue equals `RR-036`. [container-scan.md](container-scan.md) |
| Do the images carry SBOM and provenance? | **Yes** — per-image CycloneDX SBOMs and unsigned `image-provenance.json` in this directory, regenerated by `make scan-images` and by the release workflow's `images` job (`RR-038`, closed) |
| Are the dependency closures clean? | `make audit` re-run clean at `0.7.1` (`pip-audit` + `pnpm audit`) |
| How fast is it? | Inherited from `0.7.0`: [performance.md](../../performance.md) / [../0.7.0/performance.json](../0.7.0/performance.json). The migration changed compiled *content*, not the compile path; figures were not re-measured |
| Was a clean-room rehearsal re-run? | **No** — inherited from `0.7.0` ([../0.7.0/clean-room.md](../0.7.0/clean-room.md)). The install path (wheel, packaged data) is unchanged; the web image base changed and is covered by the rescan and `make web-e2e` instead. An approver who weighs the rehearsal heavily may ask for a re-run |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md) — 39 entries with stable ids, of which eight rows are closed (seven by this work; `RR-035` previously) |
| Was it externally reviewed? | **No.** As for `0.7.0`, no external security review was commissioned; the wording restrictions recorded in the [`0.7.0` decision](../0.7.0/release-decision.md#external-review) apply to this release unchanged |

## The register count, made legible

The `0.7.0` decision says the register carries 38 entries, but its own addendum records
that `RR-036` and `RR-037` entered the register *after* the signatures, and `RR-038` was
added later still and never separately signed. So the `0.7.0` signatures actually
covered 35 entries; the "38" in that document describes the register as it stood when
the count was last updated, not as it stood at signature. This approval is asked to
cover the full 38-entry register as it stood at signature — including the three entries that
post-dated the previous signatures and the seven closures made since. Entries from `RR-039`
onward were added after this approval by the Sprint 9 model-provider work and are not
covered by these signatures; the count quoted above tracks the live register, as the count
gate requires, not the register as signed.

## Conditions from the 0.7.0 approval

Both standing conditions — `RR-001` and `RR-003` become P0 before any release that
permits a runner off the operator's machine or a non-fixture target — are **discharged
by closure**, not by rescoping: both risks are fixed and adversarially tested. No new
condition is proposed. The remaining open register entries are documented limitations of
a local-first developer release, unchanged in kind from what the `0.7.0` approval
accepted.

## Approvals required

Each of these is a named human accepting accountability for a specific judgement. None
may be self-assigned by whoever prepared this record, and none is satisfied by an agent
signature.

| Role | Approving that | Name | Date |
|---|---|---|---|
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | `nmasamba` | 2026-08-27 |
| Security | The residual-risk register is complete and correctly scoped, including the seven closures and the digest migration made since `0.7.0` | `nmasamba` | 2026-08-27 |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct. The Python and web dependency closures are unchanged since the `0.7.0` licence approval, but two adjacent things did change and are recorded in [dependencies.md](../../dependencies.md): the web runtime base image moved from the Docker Official `nginx` to NGINX's `nginxinc/nginx-unprivileged` community image, and `pnpm-lock.yaml` now locks the Node.js 24.18.0 runtime itself (MIT-licensed, integrity-pinned per platform) for pnpm's managed-runtime provisioning | `nmasamba` | 2026-08-27 |

> **All three roles are held by one person.** That is a normal situation for a project
> this size, and it is recorded rather than hidden: the security and licence judgements
> were **not independent** of the maintainer judgement. A reader weighing this release
> should read the three approvals as one person's, not three.

## Publication

Approval was not publication, and the record above did not decide it. That decision was
taken separately: on 2026-09-03 the owner published `0.7.1` as a GitHub Release —
<https://github.com/nmasamba/OAK/releases/tag/v0.7.1> — attaching the wheel, sdist,
CycloneDX SBOM, licence inventory, `SHA256SUMS` and build provenance produced by the
`v0.7.1` run of `release.yml`, each verified against `SHA256SUMS` before upload and again
anonymously after publication.

Two things happened between approval and publication, and neither changed what was
approved. The `v0.7.1` tag was re-cut from `4754c85` to `c614414` with the owner's
approval, to pick up two image-tooling fixes — the SBOM stamp that crashed the first tag
build on a root-owned file, and cache-free scan builds — and a refreshed image scan from
a clean tree; the wheel, sdist and all four canonical reference digests are identical
across the two. And the first tag build's alarm about a fixable OpenSSL finding was traced
to a cached local build, not to the images: a cache-free build installs the patched
packages, and the refreshed evidence in this directory records zero fixable findings.

Published digests:

```
d75526f8ebe86fed3e4c9a8cbd3592a5296d7fb70b628160f3ea6463afd22385  oak_community-0.7.1-py3-none-any.whl
b68fe34f627f9c73c0ccf09c4923914a4c24ff4361881c8e17ffd6e033a449f0  oak_community-0.7.1.tar.gz
```

Not on PyPI and not in a container registry; both remain separate decisions.

