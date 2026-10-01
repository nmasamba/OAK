<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.9.0

**Status: unsigned.** The owner asked for `0.9.0` to be cut on 2026-09-30, after merging
Sprint 11. The tag `v0.9.0` is cut on the merge commit of the pull request that carries this
record, **ahead of any signature**, as `v0.8.0` was. The three approval rows below are
empty. Approval is not publication, and `0.9.0` is published nowhere.

This document assembles the evidence a maintainer needs to decide whether to declare
`0.9.0` released, and it will record who signed. It was prepared by the release work
`OAK-S11-009`, recorded in the Sprint 11 plan
(`docs/exec-plans/completed/OAK-S11-001-008-install-test-observe.md`). Whoever prepared it
is not in a position to approve it, and has not. It inherits no signature from `0.8.0`:
`RR-043` post-dates that approval, as does everything in Sprint 11.

## What is being decided

Whether to declare OAK Community `0.9.0` released: a **local-first developer release**
with no production or customer readiness claim. It supersedes `0.8.0` (approved on
2026-09-23 and published nowhere) and `0.7.1` (published as a GitHub Release on
2026-09-03).

It is a **minor** release, and not an additive one:
- Three changes are breaking, and in the `0.x` series a break lands only in a minor release
  ([compatibility.md](../../compatibility.md)):
  - an install script now needs `oak approve architecture` before `oak approve apply`;
  - the runner denies a plan compiled before this release (container adapter `0.2.0`);
  - a mutation profile that still declares the single stand-in image pair is refused.
- **None of the three had a deprecation window.** From `0.7.0`,
  [compatibility.md](../../compatibility.md) sets that window at one minor release or more.
  Each break takes effect in this release with a changelog note. No earlier release carried
  the old behaviour with a warning. Signing this record accepts that exception.
- It carries one **declared digest shift**. See
  [reference-comparison.md](reference-comparison.md) and "Evidence" below.

Explicitly *not* being decided:

- **Whether to publish anywhere.** This release publishes nothing by itself. A GitHub
  Release is the owner's separate act. PyPI is a separate, later decision weighed against
  `RR-005`, and a container registry is furthest out.
- **Anything about deploying OAK to a customer or production environment.** A release
  approval is **not** a Gate 2/3 deployment approval, and no evidence here supports one.
  In particular, `oak observe` records calibration rows that are all `unknown` today,
  because nothing runs a representative workload against an installation.

## What changed since the 0.8.0 approval

Everything merged to `main` after `v0.8.0`:
- **PR #24–#26:** the `0.8.0` approval, its clean-room record and a platforms citation.
- **PR #27:** the plain-language README, tour and manual chapter 5.
- **PR #28:** the candidate-explanation display fix.
- **PR #29:** the browser suite's Compose-target guard.
- **Sprint 11, as PR #30 (`cb28160`):**
  - **Two approvals before any install.**
    - `oak approve architecture` signs an approval of the selected architecture as
      compiled. It binds the plan, bundle and target, and names the decision, the
      candidate and the digest of what `apply` would install.
    - `oak approve apply` is refused without a current one.
    - Dispatch attaches both, and the runner verifies both independently.
    - Rollback and destroy never need it.
  - **Install the topology.**
    - One labelled `--network=none` container is created per node of the selected
      candidate. Its image is the digest-pinned image the target profile acknowledges
      for that component.
    - A component with no image fails `preflight.installation`, with no fallback.
    - Container names derive from an installation identity scoped to the case version,
      the workspace and the target. The runner re-derives every name, image, isolation
      and registry from its own profile.
    - Apply adopts only its own container, after reading its configuration back from the
      daemon. It compensates exactly what it created.
    - Removal touches only owned containers and proves absence.
  - **Start and smoke-test only where the profile says so.**
    - A profile acknowledging `isolated-non-production-hardened-start` gets each node
      started under a fixed hardening set that is part of the adapter's identity.
    - The smoke test runs inside `apply` and reports typed evidence.
    - Other profiles still never start anything.
  - **`oak observe`** records the deployment measures and a calibration row per
    objective and contract metric, and proposes nothing.
  - **`oak architecture`** is a read-only place to stop at the design.
  - **Runner hardening:**
    - the Docker child gets an empty, runner-owned `DOCKER_CONFIG`;
    - evidence is redacted by key and by URL credential;
    - a lapsed lease stops the next side effect;
    - an interrupted dispatch is reported as manual recovery.

Schema changes are additive enum members and optional fields, plus the new
`observation-record` schema at `0.1.0` (recorded in `docs/compatibility.md`). A `0.8.0`
reader cannot validate a document that uses them.

## Evidence

| Question | Where it is answered |
|---|---|
| Does it install on a clean machine? | `make release` at `d5717de`, run with `UV_OFFLINE=1`, installed the built wheel into a throwaway environment holding only the locked runtime closure. It then ran the installed console script from outside the checkout: `clean_environment_install_verified: true` in `dist/release/build-provenance.json`. The dependencies were synced from the lockfile offline, which leaves the optional `keychain` extra out, as a first-time installer has it. Platform support is in [platforms.md](../../platforms.md) |
| Does the artifact that ships actually work? | `tests/e2e/test_installed_wheel.py`, plus the release build's own out-of-checkout run. The full gate at `d5717de`, the commit the release artifacts were built from, run with `UV_OFFLINE=1` and PostgreSQL enabled: zero `make: ***` lines; 751 unit and contract tests (1 skipped); 313 integration tests (4 skipped), including the PostgreSQL-gated suites that CI skips (`RR-019`); 43 end-to-end tests; strict mypy over 140 source files; the OpenAPI compatibility check and the web build. In the first run of that gate, 20 PostgreSQL tests failed or errored because a Docker Desktop update (29.3.1 to 29.8.1), applied two minutes before the gate started, restarted the daemon and stopped the test database. The gate was re-run from the start with the database back up |
| Do the artifacts reproduce? | **Yes.** `make release` builds twice into separate directories and compares digests, and refuses to finish unless they match (`reproducible_rebuild_verified: true` at `d5717de`). Container images do **not** reproduce (`RR-006`) |
| Did the reference digests move? | **Yes, by exactly the declared shift and nothing else.** The reference case was compiled at `v0.8.0` and at `d5717de` and compared artifact by artifact. Both index 43 artifacts, and 35 are byte-identical, including `candidate-03` (`576b0ca6…`) and the semantic manifest (`2ef34758…`). The other eight differ only by the three corrected assurance strings, or by digests that carry them forward, so `deployment_bundle`, `runner_plan` and the case at `0.1.7` moved to the values `CHANGELOG.md` states: [reference-comparison.md](reference-comparison.md). `tests/integration/test_reference_digests.py` pins the new values and passed in the gate |
| Were the images scanned? | **Yes**, from a clean tree at `c067aad` (`source_tree_dirty: false`) with `--no-cache --pull`: zero fixable CRITICAL or HIGH findings. The web image reports nothing at any severity. The API image's 44 HIGH findings are the same eight unfixable advisories as at `0.8.0`. [container-scan.md](container-scan.md) |
| Do the images carry SBOM and provenance? | **Yes.** Per-image CycloneDX SBOMs and an unsigned `image-provenance.json` are in this directory. They come from the same pinned scanner and the same exported tarball as the vulnerability scan |
| Are the dependency closures clean? | **Yes.** `make audit` at `d5717de`: `pip-audit` and `pnpm audit` both reported no known vulnerabilities, and no dependency had changed since `v0.8.0`. Later the same day, three advisories were published against `urllib3` 2.7.0 (`CVE-2026-97687`, `-97688`, `-97689`), and CI's audit step failed. `urllib3` is a development-only dependency, reached through `pip-audit` and `requests`; it is not in the runtime closure, and the release SBOM does not list it. It was raised to 2.8.0 in the lockfile, which moved nothing else, and `make audit` is clean again ([dependencies.md](../../dependencies.md)). The artifacts below were built before that change. It cannot alter the wheel or the SBOM, but it does change the sdist, which carries `uv.lock` |
| Does install, test and observe work on a real Docker daemon? | **Yes**, three ways. The gate's `tests/e2e/test_runner_journey.py` ran the whole exit demonstration against the daemon on this machine: `approve apply` refused without an architecture approval, then both approvals, install, re-apply, observe, rollback, observe. The same journey ran on CI's Linux runner for the Sprint 11 merge, and the Sprint 11 plan transcribes a manual run on Docker Desktop (arm64): install, re-install, observe, roll back, observe, with no OAK container left afterwards |
| How fast is it? | **Re-measured**, because Sprint 11 changed code on the compile path that every target runs (plan compilation reads the workspace manifest once more, and three assurance strings changed): the reference compiler median was 8.92 s against 8.66 s at `0.7.0`, and the p95 interactive read was 36.8 ms against 30.5 ms. Both are far inside their requirements (120 s and 500 ms). [performance.json](performance.json), summarised in [performance.md](../../performance.md) |
| Was a clean-room rehearsal run? | **Yes, before signature**, repeating the six steps of the `0.8.0` rehearsal: [clean-room.md](clean-room.md). The gate and release build ran offline, and both refusal paths of the artifact verifier were exercised (exit 2 and exit 3). The CLI journey, ending with `oak architecture`, ran inside the linux/amd64 image. The browser suite ran twice against one throwaway stack, with zero axe violations. The backup-and-restore procedure ran with all three volumes destroyed, and `verify_deployment.py` returned 0 on the restored root, as it did at `0.7.0` and could not at `0.8.0`. No product defect was found |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md): 43 entries with stable ids on 2026-09-30, when this record was prepared, of which eight rows are closed. `RR-043` is new since the `0.8.0` signatures. Sprint 11 rewrote `RR-003`, `RR-013`, `RR-023` and `RR-031` |
| Was it externally reviewed? | **No.** No external security review was commissioned. Sprint 11's internal adversarial audit is recorded in its ExecPlan: six lenses, 29 findings raised, 28 surviving a refute-by-default check, all fixed with regression tests. The wording restrictions recorded in the [`0.7.0` decision](../0.7.0/release-decision.md#external-review) apply unchanged |

## The register count, made legible

The `0.8.0` signatures covered 42 entries. This record was prepared against 43, the
register as it stood on 2026-09-30, and the one addition is `RR-043`:
- **What it records:** a profile that acknowledges starting runs processes from pinned
  images on the operator's machine.
- **The bound:** those processes run under a fixed hardening set, with no network, no
  volumes, no environment and no ports, after two signed approvals, and only once the
  runner has read each container's configuration back from the daemon.
- **What remains:** the code inside the image, which OAK neither builds nor inspects; the
  host's kernel and container runtime, which they share; and the Docker daemon, which runs
  with whatever privileges the operator gave it.

It is not proposed as a release blocker. Starting is opt-in per target profile:
`examples/targets/local-mutation-fixture.yaml` does not opt in, and
`examples/targets/local-started-fixture.yaml` does, to show what opting in looks like. Both
map every component to a pause image whose process only waits.

**When this record is signed, the count it covers is the count at signature.** If entries
are added before then, this section must be updated before anyone signs it.

## What this release does not defend against

Read `RR-043` and the four rewritten rows in full before signing. In short: a user
who acknowledges hardened start is asking OAK to run a container on their machine. The
container is confined, but it is not isolated from the host the way a virtual machine
would be. The image it runs is whatever the profile's digest names: OAK checks that digest
and does not check what the image does.

## Approvals required

Each of these is a named human accepting accountability for a specific judgement. None
may be self-assigned by whoever prepared this record, and none is satisfied by an agent
signature.

| Role | Approving that | Name | Date |
|---|---|---|---|
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | | |
| Security | The residual-risk register is complete and correctly scoped, including `RR-043` and the four entries Sprint 11 rewrote | | |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct. Sprint 11 added no runtime dependency, and the stand-in image is referenced by digest, never redistributed | | |

> If one person signs all three rows, as happened for `0.7.1` and `0.8.0`, the record
> should say so. The security and licence judgements are then **not independent** of the
> maintainer judgement.

## What this build produced

`make release` at `d5717de`, from a clean tree, built and verified these. They are the
artifacts an approval would be approving, and nothing here has been uploaded anywhere.

```
68eaac2c6932ec5c2fd67acfcf5d4f5e2f800dc63123a47ab4da1c09841c67bd  THIRD-PARTY-LICENCES.md
dc0c649a8f5838358b3f840f894c218e2a2628e91202e072c6b10d08e48ce9dc  oak-community-0.9.0.cdx.json
ba26e6385dca6f74d6fcf46478fb02b0ef17ae2867b808ec6321c912c08a11e9  oak_community-0.9.0-py3-none-any.whl
7aa7b51c69c52dc80697b426cdb44abce2d18628f8551e4147016b65f2da6e1a  oak_community-0.9.0.tar.gz
```

`make verify-release` checks these against `SHA256SUMS`. Checksums prove the bytes match
the manifest; they do not prove who produced them, and these artifacts are unsigned
(`RR-005`). The sdist carries documentation and tests, so later documentation commits move
its digest. The wheel carries neither.

## The tag, and when it was cut

`v0.9.0` points at the merge commit of the pull request that cut this release: the one
carrying the version touch-list, the evidence and this record. It does not point at the
Sprint 11 merge (`cb28160`), which predates all three. It is cut on 2026-09-30 because the
owner asked for the release to be cut, and the approval rows above are empty at that
commit. If they are signed later, the tag will not be moved onto the commit that carries
the signatures, for the reason the `0.8.0` record gives: moving a published tag rewrites
what a reader already fetched.

## Publication

Approval is not publication, and neither is a tag. Pushing the tag runs `release.yml`,
which builds and verifies under read-only permissions and publishes nothing. A GitHub
Release, PyPI and a container registry are each a separate, later decision, and none has
been taken.
