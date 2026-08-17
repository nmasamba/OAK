<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build status

- **Updated:** 2026-08-17
- **Repository version:** `0.4.0.dev3`
- **Phase:** Sprint 1 complete — local DesignCase, interpretation, and confirmation
- **Completed plans:** `docs/exec-plans/completed/OAK-S0-001-009-walking-skeleton.md` and `docs/exec-plans/completed/OAK-S1-001-010-local-design-case.md`
- **Next task:** `OAK-S2-001` — baseline and feasible candidate models

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
| `OAK-S1-001` | complete | Atomic file workspace, immutable content-addressed artifacts, concurrency, retries, and portable import/export |
| `OAK-S1-002` | complete | Full immutable DesignCase artifact index and complete allowed/denied lifecycle matrix |
| `OAK-S1-003` | complete | Bounded YAML/JSON/Markdown/text intake and separate untrusted source records |
| `OAK-S1-004` | complete | Deterministic public-fixture interpretation into a schema-valid intent with complete scalar provenance |
| `OAK-S1-005` | complete | Provider-neutral bounded proposal port and deterministic failure adapter, optional and read-only |
| `OAK-S1-006` | complete | Stable missing, contradictory, declared-unknown, and infeasible-claim findings |
| `OAK-S1-007` | complete | At most five stable materiality-ranked questions with candidate-impact reasons |
| `OAK-S1-008` | complete | Actor-bound confirm/correct/reject/accept-risk successors with value digests and audit lineage |
| `OAK-S1-009` | complete | Offline init/design/questions/confirm/export/import CLI with human, JSON, and YAML output |
| `OAK-S1-010` | complete | Malformed, prompt-injection, Unicode, path, size, provenance, race, corruption, and provider-outage coverage |

## Verification evidence

- `make bootstrap` completed from the committed lockfiles.
- `make check` passed: 30 unit/contract, 4 integration, and 4 end-to-end tests plus formatting, lint, boundary, hygiene, toolchain-consistency, type, generated-contract, and web-build gates.
- The bootstrapped environment produced the Python source/wheel artifacts offline, and `make build` produced the production web bundle.
- Python and web dependency audits reported no known vulnerabilities; `make sbom` produced an ignored development CycloneDX artifact.
- The Compose exit demonstration made PostgreSQL, API, and web healthy; direct and web-proxied `/version` returned `0.4.0.dev3`; teardown left no project containers running.
- Documentation policy scan found no prohibited product references. Git ignore checks cover agent instructions/state, local secrets, environments, build output, runtime data, editors, and operating-system metadata.
- `make toolchain-check` proves that contributor compatibility, exact CI/container builders, package metadata, and documented versions agree; these implementation toolchains are explicitly independent of future target profiles.
- Sprint 1 `make check` passed: 183 unit/contract, 18 integration, and 6 end-to-end tests plus formatting, lint, boundaries, hygiene, types, generated contracts, and web build.
- `make build` produced the source archive, wheel, and web bundle; an isolated wheel install resolved all 18 bundled canonical schemas outside the source checkout.
- The installed-wheel offline exit journey produced case `0.1.1`, converged an identical confirmation retry without a third event, and imported a byte-identical manifest with two audit events and two idempotency records.
- Current Python and web dependency audits reported no known vulnerabilities, and the ignored development SBOM was regenerated.

## Safety boundary

The current harness accepts bounded local architecture briefs and quarantines their normalized bytes as untrusted artifacts. It has no mandatory or real model-provider call, approval, signing, runner dispatch, secret resolution, subprocess execution, or target mutation behavior. All committed fixtures are public or synthetic.
