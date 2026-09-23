<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.8.0

**Status: approved by `nmasamba` on 2026-09-23, all three roles.** The tag `v0.8.0` was
cut a day earlier, on 2026-09-22, at the owner's instruction and ahead of these signatures;
it therefore points at a commit whose copy of this record still says the rows were empty.
That sequence is recorded rather than tidied away. Approval is still not publication, and
`0.8.0` is published nowhere.

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
| Was a clean-room rehearsal re-run? | **Not at signature** — inherited from `0.7.0` ([../0.7.0/clean-room.md](../0.7.0/clean-room.md)) on the grounds that the install path is unchanged: no packaged data moved, no entry point changed, and the model seat is an optional import the deterministic journey never loads. The owner asked for it the day after signing, and it was run in full — see [clean-room.md](clean-room.md) and "After approval" below |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md) — 42 entries with stable ids at signature, of which eight rows are closed; `RR-039` to `RR-042` are new since the `0.7.1` signatures |
| Was it externally reviewed? | **No.** No external security review was commissioned; two internal adversarial audits (Sprint 9 and Sprint 10) are recorded in their ExecPlans, and the wording restrictions recorded in the [`0.7.0` decision](../0.7.0/release-decision.md#external-review) apply unchanged |

## The register count, made legible

The `0.7.1` signatures covered 38 entries as the register then stood; this approval covers
all 42 as it stood on 2026-09-23, including `RR-039` (a brief chosen for Online AI leaves the machine),
`RR-040` (a stored token is readable by same-user processes), `RR-041` (nothing caps
aggregate provider spend) and `RR-042` (a verification verdict is a claim about the past).
None is proposed as a release blocker: each is by design, opt-in, and stated on the
surfaces that expose it.

**That 42 is the count at signature and does not move.** Entries added after 2026-09-23
are not covered by these signatures; the live count is in
[security/residual-risk.md](../../security/residual-risk.md) and in `STATUS.md`.

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
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | `nmasamba` | 2026-09-23 |
| Security | The residual-risk register is complete and correctly scoped, including the four entries added since `0.7.1` and the narrowing of `RR-039` | `nmasamba` | 2026-09-23 |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct, including the optional `keychain` extra (`keyring`, MIT) added in Sprint 9 | `nmasamba` | 2026-09-23 |

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

## After approval: the clean-room rehearsal was re-run

The evidence table above says the clean-room rehearsal was **inherited** from `0.7.0` rather
than re-run, and the approval rows were signed with it reading that way. That row is left as
it was signed. This section records what happened next.

On 2026-09-23, after signing, the owner asked for the rehearsal. It was run in full and is
recorded in [clean-room.md](clean-room.md): the gate offline with the network refused, the
release build offline, both artifact-verification refusal paths, the documented journey
inside a linux/amd64 image, and the backup-and-restore procedure run verbatim with all three
volumes destroyed.

It found three things, none of which changes what was approved:

1. **`make web-e2e` was not re-runnable against a live stack.** One spec filled a constant
   brief file name, so its second run collided with its own leftover case and died on a
   two-minute timeout that named a missing button rather than the conflict. The workspace
   itself behaved correctly, refusing with `OAK-EXPECTED-VERSION` and a correlation id. The
   spec now timestamps its slug like every other spec in that directory.
2. **`scripts/verify_deployment.py` cannot return 0 on a development database** that has
   been shared with the PostgreSQL-gated test suites, because those suites leave
   `artifact_versions` rows whose bytes lived in temporary directories. After a faithful
   restore the tool still reports damage. The runbook now says so and says how to tell that
   apart from a genuinely broken backup.
3. **The runtime image ships no `examples/`**, so a journey run inside it needs the brief
   mounted in.
4. **The backup procedure writes its two files into the repository root, and neither was
   ignored.** Following the runbook verbatim put a 5.5 MB dump of a live control-plane
   database where the next `git add -A` would stage it. It was caught before it left the
   machine; both filenames are now ignored.

None is treated as a release blocker: the first is a test-isolation defect in the
repository's own suite, the second a reporting ambiguity on development machines only, the
third a deliberate omission from a runtime image, and the fourth a hygiene gap now closed.
None touches the artifacts this approval covers. A future release can
therefore answer the rehearsal row with **yes** and cite this run.

## The tag, and when it was cut

`v0.8.0` points at the merge commit of the pull request that cut this release — the one
carrying the version touch-list, the evidence and this record — not at the Sprint 10 merge
(`052211e`), which predates all three. It was cut on 2026-09-22 because the owner asked for
it, having been told the approval rows were empty, and the signatures came the next day.
The tag has deliberately **not** been moved onto the commit that carries them. Moving a
published tag rewrites what a reader already fetched, and the sequence here is worth
keeping legible: whoever checks out `v0.8.0` finds a record that says, accurately, that it
was unsigned at that moment. The signed record is on `main`, one commit later.

## Publication

Approval is not publication, and neither is a tag. Pushing the tag runs `release.yml`,
which builds and verifies under read-only permissions and publishes nothing. A GitHub
Release, PyPI and a container registry are each a separate, later decision, and none has
been taken.
