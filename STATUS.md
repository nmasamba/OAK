<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build status

- **Updated:** 2026-08-14
- **Repository version:** `0.4.0.dev3`
- **Phase:** Sprint 0 complete — foundation and walking skeleton
- **Completed plan:** `docs/exec-plans/completed/OAK-S0-001-009-walking-skeleton.md`
**Next task:** `OAK-S1-001` — file-backed local workspace repository

## Claimed work

| Task | State | Observable outcome |
|---|---|---|
| `OAK-S0-001` | complete | Locked Python workspace, importable package, and checked local/builder toolchain contract |
| `OAK-S0-002` | complete | Stable developer commands |
| `OAK-S0-003` | complete | Enforced module dependency rules |
| `OAK-S0-004` | complete | Schema/runtime conformance harness |
| `OAK-S0-005` | complete | Shared-service CLI version/help behavior |
| `OAK-S0-006` | complete | Loopback-safe health, readiness, and version API |
| `OAK-S0-007` | complete | Strict TypeScript status shell |
| `OAK-S0-008` | complete | Local PostgreSQL/API/web Compose profile |
| `OAK-S0-009` | complete | CI and supply-chain baseline |

## Verification evidence

- `make bootstrap` completed from the committed lockfiles.
- `make check` passed: 30 unit/contract, 4 integration, and 4 end-to-end tests plus formatting, lint, boundary, hygiene, toolchain-consistency, type, generated-contract, and web-build gates.
- The bootstrapped environment produced the Python source/wheel artifacts offline, and `make build` produced the production web bundle.
- Python and web dependency audits reported no known vulnerabilities; `make sbom` produced an ignored development CycloneDX artifact.
- The Compose exit demonstration made PostgreSQL, API, and web healthy; direct and web-proxied `/version` returned `0.4.0.dev3`; teardown left no project containers running.
- Documentation policy scan found no prohibited product references. Git ignore checks cover agent instructions/state, local secrets, environments, build output, runtime data, editors, and operating-system metadata.
- `make toolchain-check` proves that contributor compatibility, exact CI/container builders, package metadata, and documented versions agree; these implementation toolchains are explicitly independent of future target profiles.

## Safety boundary

The current sprint is a non-production serving harness. It has no brief ingestion, model call, approval, signing, runner dispatch, secret resolution, or target mutation behavior. All fixtures are public or synthetic.
