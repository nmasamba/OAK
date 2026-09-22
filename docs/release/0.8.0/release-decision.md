<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.8.0

**Status: tagged, approvals unsigned.** `v0.8.0` was cut on 2026-09-22 on the owner's
explicit instruction, ahead of the signatures. Nothing below is approved until the three
rows in "Approvals required" carry a name and a date, and nothing is published on the
strength of the tag alone.

This document assembles the evidence a maintainer needs to decide whether to declare
`0.8.0` released, and records who signed. It was prepared by the Sprint 10 work
(`docs/exec-plans/completed/OAK-S10-001-008-huggingface-only-modes.md`); the person or
agent who prepared it is not in a position to approve it, and has not. It inherits no
signature from `0.7.1`: `RR-039`, `RR-040`, `RR-041` and `RR-042` post-date that approval,
as does everything in Sprints 9 and 10.

## What is being decided

Whether to declare OAK Community `0.8.0` released: a **local-first developer release**
with no production or customer readiness claim, superseding `0.7.1` (published as a GitHub
Release on 2026-09-03). It is a minor release because it is additive: the deterministic
journey `0.7.1` shipped is byte-identical, and everything new is opt-in per request.

Explicitly *not* being decided:

- Whether to publish anywhere. This release publishes nothing by itself. A GitHub Release
  is the owner's separate act; PyPI is a separate later decision weighed against `RR-005`;
  a container registry is furthest out.
- Anything about deploying OAK to a customer or production environment. A release
  approval is **not** a Gate 2/3 deployment approval, and no evidence here supports one.

## What changed since the 0.7.1 approval

Two sprints, both merged to `main` (Sprint 9 as PR #21 `88fa876`; Sprint 10 as PR #22):

- **An optional model seat, and exactly one hosted family.** A brief is read in one of
  three modes named per request: `deterministic` (the default on every interface; the
  `0.7.1` output byte for byte), `online` (one open model on Hugging Face Inference
  Providers, called with the user's own token) or `local` (an OpenAI-compatible server on a
  loopback address). Nothing resolves to a model on its own. Five other hosted families
  Sprint 9 described were removed in Sprint 10.
- **The token is corroborated before it is spent.** Storing it asks the Hub's `whoami-v2`
  — one free request that generates nothing — and the verdict is stored with the time it
  was given, shown with its age, stale after a day, and refused before spend when rejected.
  The account's name and email are never stored.
- **A merge seam that never trusts the model.** Model output can write only the typed intent
  paths, never overwrites what the brief states, carries `model_proposed` provenance, raises
  a confirmation question for every section it touched, and blocks candidates until each
  is answered.
- **One transport, pinned egress.** `oak.adapters.models.transport` is the only module that
  opens a connection: fixed host allowlist (`router.huggingface.co`, `huggingface.co`, or
  the loopback endpoint), https except loopback plain http, no redirects, no proxies,
  verified TLS, one total deadline. The egress gates prove the deterministic journey loads
  no provider module.
- **The loopback guard and a per-process capability token** on every model route and on a
  model-mode interpretation.

No canonical schema `0.7.1` shipped changed shape except by additive enum members and
optional fields (recorded in `docs/compatibility.md`); `model-configuration.schema.json`
is new and machine-local. No reference digest moved.

## Evidence

| Question | Where it is answered |
|---|---|
| Does it install on a clean machine? | `make release` at `8e70825` installed the built wheel into a throwaway environment holding only the locked runtime closure and ran it from outside the checkout (`clean_environment_install_verified: true` in `dist/release/build-provenance.json`). Platform support is unchanged: [platforms.md](../../platforms.md) |
| Does the artifact that ships actually work? | `tests/e2e/test_installed_wheel.py`, plus the release build's own out-of-checkout run. The full gate at the release commit, with PostgreSQL: zero `make: ***` lines, 665 unit/contract, 276 integration (4 skipped), 42 e2e |
| Do the artifacts reproduce? | **Yes.** `make release` builds twice into separate directories and compares digests (`reproducible_rebuild_verified: true`); two independent runs on this machine, one before and one after the documentation commit, produced identical digests for all four artifacts. Container images do **not** reproduce (`RR-006`) |
| Are the four reference digests unchanged? | **Yes.** `tests/integration/test_reference_digests.py` pins them and passed at the release commit; the deterministic journey is byte-identical to `0.7.1` |
| Were the images scanned? | **Yes**, from a clean tree at `07880eb` (`source_tree_dirty: false`): zero fixable CRITICAL or HIGH findings, the web image reports nothing at any severity, and the API image's 44 HIGH findings are eight distinct unfixable advisories. [container-scan.md](container-scan.md) |
| Do the images carry SBOM and provenance? | **Yes** — per-image CycloneDX SBOMs and unsigned `image-provenance.json` in this directory, from the same pinned scanner and the same exported tarball as the vulnerability scan |
| Are the dependency closures clean? | **Yes.** `make audit` at the release commit: `pip-audit` and `pnpm audit` both report no known vulnerabilities. The same command ran clean in CI on the Sprint 10 merge |
| Did the model path work against the real provider? | **Yes**, on 2026-09-22 with the owner's own Hugging Face token: verification, discovery and one online interpretation that spent real credit, recorded under `## Live run` in [the Sprint 10 plan](../../exec-plans/completed/OAK-S10-001-008-huggingface-only-modes.md). It failed twice first, and both failures were product defects that are fixed |
| How fast is it? | Inherited from `0.7.0` ([performance.md](../../performance.md)); the deterministic compile path is unchanged and figures were not re-measured |
| Was a clean-room rehearsal re-run? | **No** — inherited from `0.7.0` ([../0.7.0/clean-room.md](../0.7.0/clean-room.md)). The install path is unchanged: no packaged data moved, no entry point changed, and the model seat is an optional import the deterministic journey never loads. An approver who weighs the rehearsal heavily may ask for a re-run |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md) — 42 entries with stable ids, of which eight rows are closed; `RR-039` to `RR-042` are new since the `0.7.1` signatures |
| Was it externally reviewed? | **No.** No external security review was commissioned; two internal adversarial audits (Sprint 9 and Sprint 10) are recorded in their ExecPlans, and the wording restrictions recorded in the [`0.7.0` decision](../0.7.0/release-decision.md#external-review) apply unchanged |

## The register count, made legible

The `0.7.1` signatures covered 38 entries as the register then stood; this approval is
asked to cover all 42, including `RR-039` (a brief chosen for Online AI leaves the machine),
`RR-040` (a stored token is readable by same-user processes), `RR-041` (nothing caps
aggregate provider spend) and `RR-042` (a verification verdict is a claim about the past).
None is proposed as a release blocker: each is by design, opt-in, and stated on the
surfaces that expose it.

## What this release does not defend against

Read the four new entries in full before signing. In one sentence each: a brief the user
sends to Hugging Face is governed by Hugging Face's and the routed provider's terms, not
OAK's; a process running as the user can read the stored token; the user's own Hugging Face
credit is the only budget; and a token revoked after it was verified reads `accepted` until
it is checked again or used.

## Approvals required

Each of these is a named human accepting accountability for a specific judgement. None
may be self-assigned by whoever prepared this record, and none is satisfied by an agent
signature.

| Role | Approving that | Name | Date |
|---|---|---|---|
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | | |
| Security | The residual-risk register is complete and correctly scoped, including the four entries added since `0.7.1` and the narrowing of `RR-039` | | |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct, including the optional `keychain` extra (`keyring`, MIT) added in Sprint 9 | | |

> **All three roles are held by one person.** That is a normal situation for a project
> this size, and it is recorded rather than hidden: the security and licence judgements
> are **not independent** of the maintainer judgement. A reader weighing this release
> should read the three approvals as one person's, not three.

## What this build produced

`make release` at `8e70825`, from a clean tree, built and verified these. They are the
artifacts an approval would be approving; nothing here has been uploaded anywhere.

```
37951c871733de598cb251265852d55e3ef5bc7aa8ce744f783014fb833907a7  THIRD-PARTY-LICENCES.md
1d391dda282fad926873ce7e4c19ec67acd57c23e856754b3c242b336ec741be  oak-community-0.8.0.cdx.json
40d108c6354bd679b2617acac171b8d1d62fb2514a06de3dafe84436680b00d3  oak_community-0.8.0-py3-none-any.whl
96a6110a9fd2c66e426eb9400f5fc39fa760bf11fafa131e58cb6541846dbbd5  oak_community-0.8.0.tar.gz
```

`make verify-release` checks these against `SHA256SUMS`. Checksums prove the bytes match
the manifest; they do not prove who produced them, and these artifacts are unsigned
(`RR-005`).

## The tag, and what it does not mean

`v0.8.0` points at the merge commit of the pull request that cut this release — the one
carrying the version touch-list, the evidence and this record — not at the Sprint 10 merge
(`052211e`), which predates all three. It was cut because the
owner asked for it on 2026-09-22, having been told the approval rows were empty. Recording
that plainly is the point: a reader comparing this tree with the record should find the
tag present and the signatures absent, and should not read one as standing in for the
other. Signing the rows below remains the act that makes `0.8.0` an approved release.

## Publication

Approval is not publication, and neither is a tag. Pushing the tag runs `release.yml`,
which builds and verifies under read-only permissions and publishes nothing. A GitHub
Release, PyPI and a container registry are each a separate, later decision, and none has
been taken.
