<!-- SPDX-License-Identifier: Apache-2.0 -->

# Documentation index

## Start here

| If you want to | Read |
|---|---|
| Run OAK on your machine | [../README.md](../README.md), then [platforms.md](platforms.md) |
| Operate it: back up, restore, upgrade, uninstall | [operations.md](operations.md) |
| Look up a setting | [configuration.md](configuration.md) |
| Look up an `OAK-*` code you just hit | [error-codes.md](error-codes.md) |
| Understand what it does | [architecture.md](architecture.md), [compiler-flow.md](compiler-flow.md) |
| Contribute | [../CONTRIBUTING.md](../CONTRIBUTING.md), [development.md](development.md) |
| Report a vulnerability | [../SECURITY.md](../SECURITY.md) |

## Using OAK

- [local-design-case.md](local-design-case.md) — the offline brief-to-plan journey.
- [compiler-flow.md](compiler-flow.md) — what each compilation stage produces and binds.
- [interfaces.md](interfaces.md) — CLI, REST, MCP and portals; the permission model and
  the capability matrix, including what is deliberately unavailable.
- [signed-runner.md](signed-runner.md) — signing, approval, dispatch and the verification
  order before any target access.
- [extension-sdk.md](extension-sdk.md) — writing a governed extension.

## Operating OAK

- [platforms.md](platforms.md) — supported OS, architecture and install path, with the
  glibc and architecture floors read from the lockfile, and why there is no Kubernetes
  profile.
- [operations.md](operations.md) — the runbook: install, configure, observe, back up,
  restore, upgrade, troubleshoot, export, uninstall, secure local binding and keys.
- [configuration.md](configuration.md) — every `OAK_*` variable, pinned to the source by
  a contract test.
- [error-codes.md](error-codes.md) — generated reference for every `OAK-*` code.
- [performance.md](performance.md) — measured numbers with hardware and workload
  provenance, and an explicit statement of what was not measured.

## Contracts and governance

- [compatibility.md](compatibility.md) — what may change under you, per public surface.
- [release-process.md](release-process.md) — what a release consists of and how to verify
  one.
- [dependencies.md](dependencies.md) — the dependency record and every review.
- [adr/README.md](adr/README.md) — implementation and mirrored architecture decisions.
- [../schemas/README.md](../schemas/README.md) — the canonical schema set.

## Security

- [../SECURITY.md](../SECURITY.md) — reporting, scope, and what this release does and does
  not assure.
- [security/threat-coverage.md](security/threat-coverage.md) — every threat id mapped to
  the tests that exercise it, and every gap named.
- [security/residual-risk.md](security/residual-risk.md) — what is not defended, with
  stable ids.

## Release evidence

[release/0.7.0/](release/0.7.0/) holds the artefacts produced while preparing `0.7.0`:
measurements, rehearsal records, and the release decision record.

## Engineering history — not product documentation

`exec-plans/completed/` holds one plan per delivered sprint. They are candid internal
records, including post-mortems of defects found and fixed, and they describe the state of
the world when they were written rather than the state today. They are kept because they
are the fastest way to understand why something is the way it is — but if you are looking
for how OAK behaves now, every document above is a better source.
