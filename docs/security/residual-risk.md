<!-- SPDX-License-Identifier: Apache-2.0 -->

# Residual risk register — OAK Community 0.7.0

What this release does **not** defend against, in one place, with stable identifiers.

Until now these were scattered across three completed sprint plans with no ids, no
severities and no links to the threats or invariants they touch. Anything documented in a
sprint post-mortem was effectively undiscoverable to a user of the software, which is the
wrong place for a statement about what a release does not protect.

**Every entry here is a known, accepted gap, not a discovered vulnerability.** For
reporting something not on this list, see [SECURITY.md](../../SECURITY.md).

## How to read this

- **Severity** is scored *for the shipped configuration* — a local-first developer
  release whose runner reaches only an explicitly acknowledged fixture profile and whose
  keys are labelled `development`. Several entries would be materially more severe in a
  deployment Community does not support, and say so.
- **Owner** is unassigned for every entry. Assigning owners is part of the release
  decision and requires accountable humans; see
  [release/0.7.0/release-decision.md](../release/0.7.0/release-decision.md).
- **Blocks release** records whether the entry is proposed as a P0 blocker. That
  proposal is a recommendation to the maintainers, not a decision taken here.

## Register

### Signing, approval and the runner

| ID | Risk | Severity | Blocks release | Source |
|---|---|---|---|---|
| `RR-001` | **Revocation notices are unsigned and the channel is fail-open.** Deleting a revocation notice from the mailbox restores a revoked approval's usability. | High in a distributed deployment; **low as shipped** | Proposed: no — see rationale | Sprint 5 |
| `RR-002` | `docker` and `opa` are resolved through the inherited `PATH`, and no minimum OPA version is enforced. The hardened `os.defpath` applies to the child environment, not to resolution. | Medium | Proposed: no | Sprints 5–6 |
| `RR-003` | **The image digest is not verified against what the container runtime actually resolved**, and no registry allowlist exists — any registry host matching a character-set regex is accepted. The digest pin is an input assertion, not an enforced control. | High for a real target; **low as shipped** | Proposed: no — but P0 before any non-fixture target | Sprint 5 |
| `RR-012` | The runner's trust-anchor directory defaults to the same path that holds the control plane's **private** signing keys (`~/.oak/trust`). Only `*.identity.json` files are read, but the two concerns share a directory. | Medium | Proposed: no | Sprint 5 |
| `RR-013` | The runner's subprocess executor strips `HOME`, `DOCKER_HOST`, `XDG_RUNTIME_DIR` and `TMPDIR` from the child, so only a daemon on the default socket is reachable. Rootless Docker, Colima and Podman socket shims are not supported. | Low (availability, not security) | No | Sprint 8 |
| `RR-023` | **Runner evidence redaction matches dict *values*, not dict *keys*.** `{"password": "…"}`, `{"api_key": "…"}`, `{"Authorization": "…"}` and a connection URL all pass through unredacted. Not currently reachable — every evidence value is built in code from a closed set of constants, digests and validated names, and no adapter output reaches it — so this is latent risk for a future operation kind. | Low now, High if adapter output is ever admitted | Proposed: no | Sprint 8 |
| `RR-027` | Three security-invariant clauses are neither enforced nor previously recorded as exceptions: the runner sets no isolated working directory (`cwd` is unset on both subprocess sites), no workspace zeroization exists, and the acknowledged non-loopback bind path returns silently rather than warning. | Medium | Proposed: no | Sprint 8 |
| `RR-029` | The signature block's own `role` and `trust_level` fields sit outside the signed payload. Anchor-based verification makes a mismatch unusable, but the fields remain unauthenticated claims. | Low | No | Sprint 5 |

**`RR-001` and `RR-003` rationale.** Both are genuine weaknesses in security controls, and
both are scored low *only because of what this release actually permits*. The runner
touches one network-isolated, never-started fixture container on the local machine,
through an explicitly acknowledged target profile. An attacker who can delete a file from
your local mailbox, or steer your local Docker daemon, already has your filesystem —
including the private keys in `~/.oak/trust`. Neither weakness is an escalation in that
configuration. Both become P0 the moment a runner is not on the operator's own machine,
which is why they are recorded here rather than closed.

### Policy, extensions and the compiler

| ID | Risk | Severity | Blocks release | Source |
|---|---|---|---|---|
| `RR-004` | **Policy decisions are recorded but gate no state transition**, and activating a component-manifest or architecture-pattern extension does not feed the compiler's catalogue. Wiring either changes the catalogue snapshot every compiled artifact is digest-bound to, so it needs a deliberate migration. | Medium — a reader may assume policy is enforcing | Proposed: no | Sprint 6 |
| `RR-011` | `src/oak/compiler/planning.py` emits a `not_signed` marker whose reason text says signing is not implemented. It is stale — signing exists — but it is canonical, digest-bound content, so correcting it shifts every bundle digest. | Low (accuracy) | Proposed: no | Sprint 6 |
| `RR-025` | **No signature, provenance or SBOM gate on catalogue component manifests.** Eligibility checks status, availability, evidence freshness, known vulnerabilities and licence review — not the authenticity of the manifest itself (TM-02). | Medium | Proposed: no | Sprint 8 |
| `RR-020` | `jsonschema` runs without a format checker, so `format: date-time` is documentation rather than validation. Timestamps fail closed through explicit checks instead. | Low | No | Sprint 6 |
| `RR-022` | The PostgreSQL `approvals` and `schema_metadata` tables are created but unused. Deliberate. | Informational | No | Sprint 6 |

### Interfaces

| ID | Risk | Severity | Blocks release | Source |
|---|---|---|---|---|
| `RR-007` | **Remote CLI integrity depends on trusting the control plane.** The document check compares a returned document against a case reference from the *same* response, so it detects a corrupted or version-skewed server, not a fully malicious one. | Medium | Proposed: no | Sprint 7 |
| `RR-008` | `oak validate bundle` binds only the digest edges that exist in a detached bundle. `assurance-plan.json` and `semantic-manifest.json` carry no edge into the spine, so a detached directory could pair a genuine spine with a substituted assurance plan. A review bundle is not a security artifact; the signed runner envelope is. | Medium | Proposed: no | Sprint 7 |
| `RR-009` | The webhook envelope is an export and verification contract only. Nothing dispatches webhooks; delivery-side replay protection is a documented consumer obligation, unenforced by OAK. | Low | No | Sprint 7 |
| `RR-010` | The MCP server serves one stdio client per process with no concurrent-session model. | Low | No | Sprint 7 |
| `RR-024` | **No per-job budget, tenant quota or rate limiter exists** (TM-14). Frame, argument and body sizes are bounded and operations have retry and lease bounds, but nothing caps aggregate work. | Medium | Proposed: no | Sprint 8 |
| `RR-026` | **The local tenant is not multi-tenant evidence.** Tenant scoping is enforced and tested, but Community has one local tenant, no authentication, and no isolation controls of the kind a multi-tenant claim would require. | Informational — but a misreading would be serious | No | Invariants |

### Release, supply chain and operations

| ID | Risk | Severity | Blocks release | Source |
|---|---|---|---|---|
| `RR-005` | **Release artifacts are unsigned.** Checksums prove the bytes match the manifest; they do not prove who produced them. An attacker controlling the distribution channel can replace the artifacts and the manifest together. No maintainer signing key exists, and this release does not invent one. | Medium | Proposed: no — nothing is published | Sprint 8 |
| `RR-006` | **Container image builds are not byte-reproducible.** `useradd` writes a date-stamped shadow entry, bytecode compilation is enabled, and nothing sets `SOURCE_DATE_EPOCH` or rewrites layer timestamps. Two builds of the same commit differ. Python artifacts *are* reproducible and this is verified on every `make release`. | Medium | Proposed: no | Sprint 8 |
| `RR-014` | **CI proves one platform: `ubuntu-latest` x86_64.** No macOS job, no arm64 job, and the `check` job builds no container image. The macOS rows in [platforms.md](../platforms.md) are verified by local rehearsal, not automation. | Medium | Proposed: no | Sprint 8 |
| `RR-015` | **There is no application logging and no metrics.** `oak-api` runs uvicorn with `access_log=False` and nothing configures a logger. Observability is four endpoints and the database. | Medium (supportability) | Proposed: no | Sprint 8 |
| `RR-016` | **`/readyz` does not check the schema revision.** Nothing stops a new binary starting against an old database, or the reverse; readiness goes green either way and failures surface later as opaque query errors. | Medium | Proposed: no | Sprint 8 |
| `RR-017` | **There is no file-workspace format migration.** A manifest carrying an unknown `schema_version` is refused on every command including `export`, so a workspace cannot be rescued after the fact. The documented rule is to export before upgrading. `0.7.0` moves no `schema_version`, so nothing is affected today — but [compatibility.md](../compatibility.md) requires a tested upgrade path for a future bump, and the mechanism to provide one does not exist yet. | Medium | Proposed: no | Sprint 8 |
| `RR-018` | `oak keys show` creates the trust directory and three private keys as a side effect of a read-looking command, so it recreates exactly what an uninstall just deleted. | Low | No | Sprint 8 |
| `RR-019` | **The PostgreSQL-gated integration suites skip silently** unless `OAK_TEST_DATABASE_URL` is set, and CI never sets it. A green CI run is not evidence that the database, tenant-isolation or interface-conformance suites ran. They are run locally for each release and the result recorded in [release/0.7.0/](../release/0.7.0/). | Medium | Proposed: no | Cross-cutting |
| `RR-030` | **Workspace read cost grows with history and nothing reclaims it.** The file workspace revalidates its whole audit lineage on every manifest read. Measured: 3.6 ms at 0 indexed artifacts, **263.9 ms at 43** — one complete reference journey. Two points cannot distinguish linear from super-linear growth, and there is no compaction, pruning or archival mechanism. A long-lived workspace gets slower and never gets faster. | Medium | Proposed: no | Sprint 8 |
| `RR-031` | **Runner soak hazards are unbounded**: the consumed-nonces file is rewritten in full per dispatch, processed dispatch directories are never cleaned, the journal is re-read on every append, and `OperationWorker.run_once` never heartbeats against its hard-coded 60-second lease, so a job approaching 60 s risks being re-claimed while still running. None matters at the scale this release is used at; none is bounded. | Medium | Proposed: no | Sprint 8 |
| `RR-021` | The web workspace has no unit tests, and `make check` excludes `make web-e2e`. Browser and accessibility coverage runs only when someone runs it. | Medium | Proposed: no | Cross-cutting |
| `RR-028` | **No external security review was commissioned for this release.** All security work recorded here and in [threat-coverage.md](threat-coverage.md) was performed by the project itself. Nothing in this release should be read as third-party assurance. <!-- assurance-claim-reviewed: this sentence denies the claim --> | Informational — but material to any reader | No | Sprint 8 |

## What is deliberately not here

Fixed during Sprint 8 rather than accepted, and therefore not residual: the payload echo
in canonical and MCP validation diagnostics, bound statement parameters reaching uvicorn's
error log, unhandled tracebacks from `oak-runner` and `oak-db-migrate`, the GPL-3.0
transitive in the runtime closure, and a developer cache directory shipping inside the
sdist. Each has a test pinning the fix; see `CHANGELOG.md`.
