<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.8.0

**Status: prepared, unsigned.** Nothing below is approved until the three rows in
"Approvals required" carry a name and a date.

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
| Does it install on a clean machine? | TODO: `make release` installs the built wheel into a throwaway environment on every build; state the run |
| Does the artifact that ships actually work? | TODO: `tests/e2e/test_installed_wheel.py`; the full gate at the release commit (counts) |
| Do the artifacts reproduce? | TODO: `make release` builds twice and compares digests. Container images do **not** reproduce (`RR-006`) |
| Are the four reference digests unchanged? | `tests/integration/test_reference_digests.py` pins them; TODO: state the run at the release commit |
| Were the images scanned? | TODO: `make scan-images` from a clean tree; `container-scan.md` in this directory; never from a tree stamped `source_tree_dirty: true` |
| Do the images carry SBOM and provenance? | TODO: per-image CycloneDX SBOMs and `image-provenance.json` in this directory |
| Are the dependency closures clean? | TODO: `make audit` (`pip-audit` + `pnpm audit`) |
| Did the model path work against the real provider? | TODO: the live run recorded in the Sprint 10 ExecPlan — verification, discovery and one online interpretation with the owner's token |
| How fast is it? | Inherited from `0.7.0` ([performance.md](../../performance.md)); the deterministic compile path is unchanged and figures were not re-measured |
| Was a clean-room rehearsal re-run? | TODO |
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

## Publication

Approval is not publication. Pushing the tag runs `release.yml`, which builds and verifies
under read-only permissions and publishes nothing. A GitHub Release, PyPI and a container
registry are each a separate, later decision.
