<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR-0002: Release the first OAK Community version as `0.7.0`

- Status: Accepted
- Date: 2026-08-21
- Owners: @owner, @maintainers
- Requirement IDs: OAK-NFR-PORT-001–002, OAK-NFR-REL-001–003

## Context

`sprints.md` names the first Community release `0.1.0`. The repository has meanwhile been
versioned `0.<sprint>.0.dev<n>` — a scheme `docs/compatibility.md` documents explicitly — and
sits at `0.6.0.dev6`.

Those two facts contradict each other. Under PEP 440 and semantic-versioning intent alike,
`0.1.0` sorts *below* `0.6.0.dev6`. Publishing `0.1.0` would make the first release lower than
development builds that already exist, so a resolver configured to accept pre-releases would
prefer a development build over the release, and anyone holding a development wheel would need
a forced downgrade to move to it. The contradiction had to be resolved before any release
artifact was built, because the version string is stamped into the wheel, the sdist, the
OpenAPI document, the image tag, the SBOM subject and the checksum manifest.

The pre-`0.1.0` scheme was never wrong on its own terms — it encoded "sprint 6, development
build 6" and never claimed ordering against the eventual release. What it did not anticipate
was that the release target had been named independently and numerically lower.

## Decision

The first OAK Community release is **`0.7.0`**.

- `VERSION`, `pyproject.toml`, `package.json`, `web/package.json`, `STATUS.md` and the
  generated `openapi/oak.openapi.json` all carry `0.7.0`, and contract tests bind them
  together so they cannot drift again.
- `docs/compatibility.md` keeps every rule it states and moves its threshold: the deprecation
  window that it said begins at `0.1.0` begins at `0.7.0`. The `0.<sprint>.0.dev<n>`
  development scheme is retired at this release; subsequent versions follow semantic-versioning
  intent from `0.7.0`.
- `0.7.0` remains firmly pre-`1.0`. It is a local-first developer release. It carries no
  production or customer readiness claim, and the release approval is not a Gate 2/3 deployment
  approval.

## Alternatives

- **Release `0.1.0` and document the reset.** Matches `sprints.md` verbatim and reads naturally
  as "first release". Rejected: it is a real ordering regression. Mitigating it properly needs a
  PEP 440 epoch (`1!0.1.0`), which is obscure, is not expressible in npm semver for the web
  workspace, and would confuse every consumer to save a label.
- **Release `0.6.0`.** The smallest legal monotonic step, since `0.6.0.dev6` is literally a
  development version *of* `0.6.0`, and it needs no scheme change at all. Rejected: the number
  reads as "sprint 6" while the release contains Sprint 7 (MCP, remote CLI, portal parity) and
  Sprint 8 (release hardening) work, which would misdescribe the release in its own changelog.
- **Keep shipping `0.x.y.devN` and never cut a final version.** Rejected: it makes every
  consumer opt into pre-releases and gives the compatibility policy no threshold to attach to.
- **Rename the target in `sprints.md` to whatever the version happens to be at the time.**
  Rejected as a non-decision; the ordering problem would recur at the next release.

## Consequences

`sprints.md`'s "`0.1.0`" label no longer names a version — it names *the first Community
release*, which is `0.7.0`. The governance repository is updated to say so. Anyone reading the
sprint backlog and expecting a `0.1.0` tag will not find one.

Because the repository version is not embedded in any canonical document — `minimum_oak_version`
and `generator_version` in the compiler are hardcoded literals, verified directly rather than
assumed — the bump cannot shift any canonical digest, and the reference case stays byte-stable
at `0.1.7`.

Object schema versions (`schema_version` inside canonical documents) are unaffected and remain
per-object, as `schemas/README.md` describes. The repository version and the object schema
versions were never assumed identical and still are not.

## Revisit triggers

A decision to publish to a public index under a different name or scheme; an owner decision to
declare `1.0.0`; or evidence that consumers are confused by the gap between the sprint
backlog's label and the released version.
