<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release decision record — OAK Community 0.7.0

**Status: approved by `nmasamba` on 2026-08-22, all three roles.**

This document assembles the evidence a maintainer needed to decide, and records who signed.
The person or agent who prepared the evidence was not in a position to approve it, and did
not: the approval below was given by the repository owner after review.

## What is being decided

Whether to declare OAK Community `0.7.0` released: a **local-first developer release** with
no production or customer readiness claim.

Explicitly *not* being decided:

- Whether to publish anywhere. `0.7.0` publishes nothing — not to PyPI, not to a container
  registry, not as a GitHub release. That is a separate decision.
- Anything about deploying OAK to a customer or production environment. A release approval
  is **not** a Gate 2/3 deployment approval, and no evidence here supports one.

## Evidence

| Question | Where it is answered |
|---|---|
| Does it install on a clean machine? | [platforms.md](../../platforms.md); `make release` installs the built wheel into a throwaway environment and runs it from outside the checkout on every build |
| Does the artifact that ships actually work? | `tests/e2e/test_installed_wheel.py` — the wheel is unpacked with no source tree above it and drives the reference journey from packaged data |
| Do the artifacts reproduce? | `make release` builds twice and compares digests; it fails the release if they differ. Container images do **not** reproduce (`RR-006`) |
| Can a user verify what they downloaded? | [release-process.md](../../release-process.md#verifying-a-release); the refusal path is tested against tampered, substituted, missing and path-escaping inputs |
| Can it be upgraded, backed up and restored? | [operations.md](../../operations.md); `scripts/verify_deployment.py` plus `tests/integration/test_backup_restore.py`, which rehearses a restore into a clean migrated database and proves a database-only restore is detected |
| What does it defend against? | [security/threat-coverage.md](../../security/threat-coverage.md) — 19 threats, 8 direct, 9 partial, 2 structural, 0 uncovered |
| What does it *not* defend against? | [security/residual-risk.md](../../security/residual-risk.md) — 38 entries with stable ids |
| How fast is it, and on what? | [performance.md](../../performance.md) and [performance.json](performance.json) |
| Is every claim backed? | A build gate rejects unqualified assurance vocabulary; `tests/contract/test_assurance_claims.py` proves it is not vacuous |
| Was it externally reviewed? | **No.** See below |
| Were the images scanned? | **Yes, after approval.** See the addendum below — this said "no" when the approval was given |

## External review

**No external security review was commissioned for this release.** Every security artefact
in this repository records work the project performed on itself: the threat-coverage index,
the adversarial suites, the secret and log review, the runner sandbox review, and the
multi-agent adversarial audit of the Sprint 8 diff.

<!-- assurance-claim-reviewed: this sentence forbids the claim -->
Nothing in this release may be described as audited, certified, or independently assured.
A documentation gate now enforces that wording; the substance is the maintainers' to
preserve.

## Addendum, 2026-08-22: the container scan was performed after approval

**The approval above was given on the strength of a record that said the images had not
been scanned.** They have been since, at the owner's instruction, and the section below is
kept as it was written so the basis of the decision stays legible. What changed after the
signatures:

- The scan found **6 CRITICAL and 72 HIGH** in the API image and **3 and 33** in the web
  image. Three causes: `uv` and `uvx` shipping in the runtime layer, base images lagging
  their distributions' patch streams, and a residue with no vendor fix.
- The API image is now multi-stage and both images apply distribution security updates.
  End state: the web image is clean and the API image has **3 CRITICAL and 14 HIGH, all
  with no vendor fix available**. **Zero fixable findings remain.**
- `RR-035` is closed. `RR-036` (the unfixable residue) and `RR-037` (the web image runs
  nginx as root) were added to the register afterwards.

**Does this invalidate the approval?** In the maintainer's judgement it does not: the
release is strictly better than the one approved, and the two conditions attached to the
approval — the `RR-001`/`RR-003` scoping — are untouched. But a reader should know that
`RR-036` and `RR-037` entered the register *after* the signatures, and neither has been
separately signed off. The full record is
[container-scan.md](container-scan.md).

## Container scanning as it stood at approval

`OAK-S8-003` asks for dependency **and container** scans. Only the dependency half was
done. `make audit` runs `pip-audit` over the Python closure and `pnpm audit` over the web
closure — both clean — but neither looks inside a built image, so the **OS packages in the
shipped images are unscanned**. No scanner was available in the release environment:
`trivy`, `grype` and `syft` are not installed, and `docker scout` requires a Docker Hub
login that the release preparation deliberately did not perform.

What stands in its place is weaker and should be read as such: every base image is pinned
by tag *and* immutable `sha256` digest, `make toolchain-check` fails if the `uv`, Python or
Node pins drift, and the images derive from `python:3.13.12-slim` and `nginx`/`node` Alpine
rather than anything bespoke.

**This is the one place where the sprint's own task list is not fully satisfied**, which is
why it is raised here rather than buried in the register. A maintainer may reasonably treat
it as a blocker. Closing it needs one scanner run against
`oak-community/api:0.7.0` and `oak-community/web:0.7.0` — `trivy image` is the smallest
option and needs no account — plus a record of the result. Recorded as `RR-035`.

## Defects found and fixed during release preparation

Recorded because a release decision should see what the preparation turned up, not only
what survived it.

| Defect | Why it mattered |
|---|---|
| Canonical and MCP validation diagnostics echoed the rejected value | An over-long MCP argument returned the whole argument to the client, into an agent transcript. REST already dropped it, so the transports disagreed |
| SQLAlchemy bound parameters reached uvicorn's error log | Brief text is a bound parameter; the API's own handler was safe but Starlette re-raises and uvicorn logs the traceback. The concrete TM-10 log-leak path |
| `oak-runner` and `oak-db-migrate` answered misconfiguration with tracebacks | Absolute paths, profile fragments and connection host/user disclosed; unactionable for an operator |
| A malformed `If-Match` returned 409 / exit 4 | Both mean "re-read and retry"; retrying a weak entity tag never succeeds, so an automated retry loop spins forever |
| `OAK-WORKSPACE-NOT-FOUND` also meant "one artifact lookup missed" | On REST and MCP the message is opaqued, leaving the code as the only signal — pointing an operator at a storage failure that had not happened |
| `rfc3987` (GPL-3.0-or-later) in the runtime closure of an Apache-2.0 distribution | Pulled by an unused `jsonschema[format]` extra; the inventory recorded jsonschema as "MIT" |
| A developer cache directory shipped inside the sdist | Made the sdist digest a function of the build machine rather than the source tree |
| Three of four copies of a message stated an exact-length rule the code does not enforce | Operators would size idempotency keys to exactly 16 characters |

## Proposed P0 blocker list

**Proposed: none — with one item explicitly handed to the maintainer.**

`RR-035` (no container scan) is not a defect but an *unperformed task*: `OAK-S8-003` names
container scans and this release does not have them. It is listed as the maintainer's call
rather than proposed either way, because the judgement — ship with the base-image pinning
that exists, or run a scanner first — is a risk-appetite decision, not a technical one.

That needs justifying rather than asserting. `RR-001` (unsigned, fail-open revocation
notices) and `RR-003` (the resolved image digest is never verified, and no registry
allowlist exists) are genuine weaknesses in security controls, and in a distributed
deployment either would be P0. They are proposed as non-blocking **for this release only**,
because of what this release actually permits: the runner touches one network-isolated,
never-started fixture container on the operator's own machine through an explicitly
acknowledged target profile. An attacker who can delete a file from that mailbox, or steer
that Docker daemon, already holds the private keys in `~/.oak/trust`. Neither weakness is an
escalation in that configuration.

**Both become P0 before any release that permits a runner off the operator's machine, or a
target that is not the fixture profile.** That condition is the substance of the proposal;
a maintainer who disagrees with the scoping should treat them as blockers now.

Everything else in the register is a documented limitation, published where a user will
find it rather than buried in a sprint post-mortem.

## Known limitations, published

[security/residual-risk.md](../../security/residual-risk.md) is the published statement, linked
from the README, `SECURITY.md`, the operations runbook and the release process. It carries
38 entries with stable ids, severities scored for the shipped configuration, and an explicit
note that every owner field is unassigned pending this decision.

## Approvals required

Each of these is a named human accepting accountability for a specific judgement. None may
be self-assigned by whoever prepared this record, and none is satisfied by an agent
signature.

| Role | Approving that | Name | Date |
|---|---|---|---|
| Maintainer | The release is functionally what it claims to be, and the evidence above is sufficient | `nmasamba` | 2026-08-22 |
| Security | The residual-risk register is complete and correctly scoped, and the P0 proposal above is accepted or amended | `nmasamba` | 2026-08-22 |
| Licence | The Apache-2.0 declaration and the generated third-party inventory are correct, including the LGPL-3.0 Psycopg entry | `nmasamba` | 2026-08-22 |

> **All three roles are held by one person.** That is a normal situation for a project this
> size, and it is recorded here rather than left to be inferred, because it means the
> security and licence judgements were **not independent** of the maintainer judgement. A
> reader weighing this release should read the three signatures as one person's decision,
> not as three separate reviews that happened to agree.

### What was accepted

- `RR-035`, that no container scan was performed and the OS packages in the shipped images
  are unassessed, with the base-image digest pinning accepted as the weaker control it is.
- The P0 proposal as written: `RR-001` (unsigned, fail-open revocation) and `RR-003` (the
  resolved image digest is never verified) are accepted as non-blocking **for this release
  only**, on the scoping argument above. **Both become P0 before any release that permits a
  runner off the operator's machine, or a target that is not the fixture profile.** That
  condition travels with the approval; it is not discharged by it.
- The full residual-risk register as published, and the absence of any external review.

Approval covers `0.7.0` as a local-first developer release. It is **not** a Gate 2/3
deployment approval, and it does not authorise publication: where these artifacts go, if
anywhere, remains a separate decision.
