<!-- SPDX-License-Identifier: Apache-2.0 -->

# Changelog

All notable changes to OAK Community are recorded here.

## Unreleased

Nothing yet.

## 0.7.0 — 2026-08-21

The first OAK Community release. A **local-first developer release**: no production or
customer readiness claim, and no external security review was commissioned for it.

### Versioning

- **The release is `0.7.0`, not `0.1.0`.** The sprint backlog named the first release
  `0.1.0`, but the repository had reached `0.6.0.dev6` and PEP 440 sorts `0.1.0` *below*
  that, so a resolver accepting pre-releases would have preferred a development build over
  the release. Recorded in [ADR-0002](docs/adr/0002-release-versioning.md);
  `docs/compatibility.md` moves its deprecation threshold from `0.1.0` to `0.7.0`. The
  `0.<sprint>.0.dev<n>` development scheme is retired.
- `VERSION`, `pyproject.toml`, `package.json`, `web/package.json`, `STATUS.md` and the
  generated OpenAPI `info.version` are now bound together by `make toolchain-check`.
  `package.json` had silently sat at `0.5.0-dev.5` while the distribution was `0.6.0.dev6`.
- **No canonical digest changed.** `minimum_oak_version` and `generator_version` are
  hardcoded literals rather than the repository version; byte-stability of the reference
  case was verified directly against the previous mainline.

### Added

- **Release engineering.** `make release` builds the sdist and wheel twice and fails if the
  digests differ, installs the wheel into a clean environment holding only the locked runtime
  closure, and runs it from outside the checkout to prove the packaged schemas, catalogue and
  policy packs resolve. It emits an SBOM of the *released* runtime closure bound to the
  artifact digests, a generated third-party licence inventory, and `SHA256SUMS`.
  `make verify-release` is a dependency-free consumer-side verifier.
- **`.github/workflows/release.yml`**, triggered by tag or manual dispatch, running
  `make check` before `make release` and separately building the API and web images. The
  `check` job in `ci.yml` is untouched.
- **Operator documentation**: [operations.md](docs/operations.md) (install through
  uninstall), [platforms.md](docs/platforms.md) (supported matrix with architecture and
  glibc floors read from the lockfile), [configuration.md](docs/configuration.md) (every
  `OAK_*` variable, pinned to the source by a contract test), and
  [error-codes.md](docs/error-codes.md) (generated; 245 of 267 codes were previously
  undocumented).
- **Container image scanning** (`make scan-images`), pinned to `aquasec/trivy:0.74.0`,
  failing the build on any *fixable* CRITICAL or HIGH and reporting unfixable findings
  without failing. The first run found 6 CRITICAL and 72 HIGH in the API image and 3 and 33
  in the web image; see
  [release/0.7.0/container-scan.md](docs/release/0.7.0/container-scan.md).
- **Security record**: [SECURITY.md](SECURITY.md),
  [threat-coverage.md](docs/security/threat-coverage.md) mapping all nineteen threat ids to
  the tests that exercise them, and [residual-risk.md](docs/security/residual-risk.md) with
  35 stable-id entries. A build gate now rejects unqualified assurance vocabulary.
- **Measurements**: [performance.md](docs/performance.md) and a provenance-stamped
  `scripts/benchmark.py`. Reference compiler 8.75 s median against a 120 s requirement;
  interactive read p95 32 ms against 500 ms; workspace manifest reads grow from 4.0 ms at
  zero artifacts to 281.2 ms at 43, with no compaction anywhere (`RR-030`).
- **Operator tooling**: `scripts/verify_deployment.py` re-verifies every indexed artifact
  against the artifact store so a restore is measured rather than declared, and
  `scripts/check_clean_machine.py` makes uninstall verifiable.
- **Contributor documentation**: [CONTRIBUTING.md](CONTRIBUTING.md), a documentation index,
  and the six architecture ADRs that shipped documents cite are now mirrored into
  `docs/adr/architecture/` so their citations resolve for a reader outside the governance
  repository.
- `make clean-all`, which removes what `make clean` never did.

### Fixed

- **Diagnostics no longer echo the value that failed validation.** `jsonschema` interpolates
  the offending value into most of its messages, so `ContractValidationError` — whose own
  docstring called it payload-safe — and the MCP tool-argument error both returned it to the
  caller, where an MCP frame lands in an agent transcript. The REST layer already dropped it,
  so the two transports disagreed on what a refusal discloses.
- **Bound statement parameters no longer reach the logs.** Canonical documents, including
  brief text, are SQLAlchemy statement parameters, and the default `hide_parameters=False`
  put them into `StatementError` messages that uvicorn's error logger writes to stderr —
  the container log under Compose. `access_log=False` does not suppress `uvicorn.error`.
  The concrete TM-10 log-leak path.
- **`oak-runner` and `oak-db-migrate` answer misconfiguration with a stable code**, not a
  traceback disclosing absolute paths, profile fragments or the database host and user.
- **A malformed `If-Match` header is `OAK-PRECONDITION-INVALID`, not
  `OAK-EXPECTED-VERSION`.** The latter maps to HTTP 409 and CLI exit 4, both of which tell
  automation to re-read and retry — and a client that sent a weak entity tag never succeeds
  by retrying, so a retry loop keyed on that signal spins forever.
- **An artifact lookup miss is `OAK-ARTIFACT-NOT-FOUND`, not `OAK-WORKSPACE-NOT-FOUND`.**
  Both still map to 404, but REST and MCP opaque the message for not-found codes, so the
  code was the operator's only signal and it pointed at a storage failure that had not
  happened.
- Three of four copies of the idempotency-key and correlation-id messages stated an exact
  length for what is a minimum check.
- A stray `-.uv-cache/` directory, matched by neither `.gitignore` nor `.dockerignore`,
  shipped inside the `0.6.0.dev6` sdist and entered the image build context. Sdist contents
  are now an explicit exclude list rather than inherited ignore rules, and
  `reproducible = true` is declared rather than inherited from a build-backend default.
- `scripts/validate_repository.py` uses `sys.executable` rather than a bare `python`, which
  does not exist on a clean Debian or Ubuntu host.

### Changed

- **The API image is multi-stage and no longer ships `uv`.** The build tool built the
  virtual environment and then stayed in the delivered image, carrying three HIGH
  advisories in its vendored Rust dependencies. The runtime stage now copies only the
  virtual environment; the image dropped from 428 MB to 373 MB.
- **Both images apply their distribution's security updates at build time.** The pinned
  base digests were verified against the registry and found *current for their tags* — the
  upstream images simply lag their distributions, so re-pinning would have fixed nothing,
  including a CRITICAL OpenSSL flaw fixed in both Debian and Alpine. This costs build-time
  determinism, which OAK does not claim for images (`RR-006`), and is the better trade
  against shipping a known-fixed CRITICAL. The web image is now free of CRITICAL, HIGH,
  MEDIUM and LOW findings; the API image has 3 CRITICAL and 14 HIGH with no vendor fix
  available (`RR-036`), all in packages inherited from the Python base image.

- **`jsonschema[format]` is now plain `jsonschema`.** Nothing constructs a `FormatChecker`,
  so the extra changed no behaviour — but it placed `rfc3987` 1.3.8 (**GPL-3.0-or-later**)
  in the runtime dependency closure of this Apache-2.0 distribution, unrecorded in the
  dependency inventory, which listed jsonschema as "MIT". The runtime closure drops from 45
  packages to 37. `format-nongpl` was rejected: it keeps eight unused packages to preserve a
  capability nothing enables. Recorded in `docs/dependencies.md`.
- The documentation gate that forbids naming the other distributions now exempts
  `docs/adr/architecture/`, which holds verbatim governance mirrors — ADR-0012's subject is
  the boundary between those distributions, so it necessarily names them. The prohibition
  stands in every reader-facing document, pinned by a test.

### Known limitations

Published in [security/residual-risk.md](docs/security/residual-risk.md) — 35 entries,
including unsigned release artifacts (`RR-005`), non-reproducible container images
(`RR-006`), no application logging or metrics (`RR-015`), `/readyz` not checking the schema
revision (`RR-016`), no file-workspace format migration (`RR-017`), PostgreSQL suites that
skip silently in CI (`RR-019`), and unbounded workspace read growth (`RR-030`).

### Everything below shipped in this release too

Sprints 0 to 7 were developed under `## Unreleased` because no release had been
cut. `0.7.0` is the first, so all of it ships here — it is not pending work.

### Added

- Sprint 7 MCP, portal, and interface parity for `OAK-S7-001` through `OAK-S7-008`: a bounded
  typed MCP server (`oak-mcp`, `oak mcp serve`) exposing the ten interface-contract tools plus
  a read-only `oak_operation_get` progress query over newline-delimited JSON-RPC 2.0 stdio,
  with closed schemas mirroring the REST bounds and no generic command, file, secret, policy,
  approval, signing, or runner-dispatch tool; a remote CLI mode (`--server`/`OAK_SERVER`)
  mapping the design journey onto REST with stable output and exit semantics; a public
  compatibility policy (`docs/compatibility.md`) for schemas, REST/OpenAPI, CLI, MCP, and the
  runner protocol; a four-interface conformance suite; Backstage and generic-portal starters;
  a signed webhook example with a headless `oak validate export|bundle|webhook` checker; and
  an interface/permission/capability reference (`docs/interfaces.md`).
- Canonical `webhook-envelope` schema wrapping one audit event with a detached
  Ed25519 signature for portal and CI consumers, verified against a pinned publisher key.
- Root CLI `--server` option, `--case` selectors on `evaluate`/`select`/`assure`/`plan`, and
  the `oak validate` and `oak mcp serve` commands; the Sprint 0 `oak-mcp` placeholder is
  replaced by the real server and the dead worker/runner placeholder siblings are removed.
- Sprint 6 policy and adapter SDK for `OAK-S6-001` through `OAK-S6-008`: versioned extension
  interfaces for the five extension classes with deterministic capability discovery, a policy
  port with a fail-closed built-in rule engine and an optional OPA adapter that must agree
  with the built-in reference engine or fail closed, a second deterministic Helm/Kubernetes deployment renderer
  behind a renderer port, and a governed extension supply chain with quarantine and explicit
  activation.
- Canonical `policy-pack`, `policy-decision`, `extension-manifest`, and `extension-activation`
  schemas; `policy_pack` and `policy_decision` workspace artifact kinds; an additive
  `policy_evaluated` audit event whose canonical decision is engine-neutral; and an additive
  `extension-steward` signing role.
- `oak policy evaluate/packs` evaluating effective-dated, scoped, signed, tested policy packs
  into engine-neutral decisions; `oak render` rendering the compiled bundle through a chosen
  deployment adapter read-only; and `oak extensions install/verify/activate/deactivate/list/
  sign/capabilities` quarantining every extension until digest, compatibility, licence,
  pinned-anchor steward signature, and embedded tests pass and an explicit local actor
  activates it.
- A reusable extension contract test kit (`tests/extension_kit`), schema-valid templates for
  every extension class, and a developer guide (`docs/extension-sdk.md`).
- Sprint 5 signed typed runner and GitOps boundary for `OAK-S5-001` through `OAK-S5-011`:
  local Ed25519 signing with per-role development keys, immutable plan-signature binding,
  digest/target/action/expiry-bound signed approvals with revocation, outbound-only mailbox
  dispatch with signed lease envelopes, and canonical `plan-signature`, `approval`,
  `runner-envelope`, and `runner-message` schemas.
- A separate `oak-runner` trust domain that independently verifies protocol, digests,
  signatures, trust anchors, target fingerprint, lease and nonce, separation of duties,
  adapter and parameter-schema allowlists, and approvals before any target access, then
  executes typed operations with a hash-chained journal, crash resume, cooperative
  cancellation, `manual_recovery_required` states, and bounded redacted evidence.
- Bounded inventory and isolated container fixture adapters building fixed allowlisted
  argument vectors with no shell, target-profile `0.2.0` gating mutation behind an explicit
  acknowledgement, typed apply/rollback/destroy operations, `oak keys`/`sign`/`approve`/
  `revoke-approval`/`dispatch`/`ingest`/`gitops` commands, and deterministic GitOps output
  that promotes nothing automatically.
- Sprint 4 architecture web workspace for `OAK-S4-001` through `OAK-S4-009`: routed case
  list/create/open screens, server-status-driven actions, durable operation polling with
  cancellation, audit timeline, and stale-version conflict recovery, backed by additive
  tenant-scoped design-case list and audit trail REST resources and `/v1` forwarding in
  the nginx and Vite proxies.
- Brief/inference review with fact, inference, domain-default, reviewer-correction, and
  unknown provenance classes; ranked-question confirmation with confirm/correct/reject/
  accept-risk decisions; candidate comparison with objective ranges, Pareto status, and
  visible rejection reasons; decision and assurance display; bundle review with explicit
  plan/approval/apply separation, digest-verified component lock, and semantic manifest
  diff; and a downloadable bounded canonical export.
- Playwright and axe-core browser suites (`make web-e2e`) covering the Compose-only
  reference journey, a denied stale-version transition, an interrupted cancelled
  operation, and automated accessibility checks on every core screen.
- Sprint 3 PostgreSQL control plane and `/v1` REST workflow for `OAK-S3-001` through `OAK-S3-009`.
- Forward-only Alembic baseline with tenant/environment/workspace-scoped immutable artifacts,
  DesignCase heads and versions, transitions, idempotency, outbox, operations, checkpoints,
  consumer receipts, and rebuildable projection positions.
- Shared file/PostgreSQL repository contract suite covering restart, concurrency, atomic
  rollback, tenant denial, digest lineage, and canonical export/restore.
- At-least-once outbox leases with stable event IDs, consumer deduplication, projection lag,
  and a real separately leased `oak-worker` process.
- Durable generate/evaluate/compile Operations with checkpoints, lease expiry, bounded retry,
  safe terminal failure, cooperative cancellation, and cancellation command provenance.
- DesignCase, candidate, Operation, artifact, export, and import REST resources with local
  actor/tenant binding, ETags, required idempotency keys, optimistic concurrency, safe problem
  details, deterministic opaque pagination, and bounded requests/artifacts.
- Generated OpenAPI 3.1 and typed TypeScript client for the persistent workflow, plus a breaking-change
  gate (`make openapi-compatibility`) that regenerates the document and rejects
  incompatible changes. The gate runs inside `make check`, which CI
  executes on every push and pull request; no dedicated `.github` step was needed.
- Sprint 2 offline compiler flow for `OAK-S2-001` through `OAK-S2-011`.
- Governed synthetic catalogue snapshots and provider-neutral baseline, minimum, balanced, and high-assurance pattern contracts.
- Deterministic hardware, deployment, security, licence, locality, and compatibility constraints with fail-closed unknown handling.
- Transparent cost, latency, quality, operability, and energy ranges with estimator/calibration metadata and Pareto sensitivity.
- Digest-linked fixture evaluation results, immutable selection decisions, assurance plans, and a stable `candidate-03` exit path.
- Canonical review bundle and draft typed runner plan with byte-stable normalized semantic manifests.
- Sprint 1 offline `DesignCase` workflow for `OAK-S1-001` through `OAK-S1-010`.
- Atomic file-backed workspace with immutable content-addressed artifacts, expected-version checks, idempotent mutations, append-only audit lineage, and digest-verified export/import.
- Bounded YAML, JSON, Markdown, and text intake with source quarantine and adversarial path, type, size, structure, and Unicode checks.
- Deterministic typed intent interpretation with complete scalar provenance, stable findings, and at most five ranked clarification questions.
- Provider-neutral optional interpretation proposals, resource limits, and a deterministic failure-injection adapter; no model provider is required.
- Confirmation successors for confirm, correct, reject, and accept-risk decisions, exposed through human, JSON, and YAML CLI commands.
- Complete Sprint 0 walking skeleton for `OAK-S0-001` through `OAK-S0-009`.
- Locked Python package with domain, compiler, application, port, adapter, interface, contract, and runner boundaries.
- Canonical schema registry and lossless public YAML/JSON runtime conformance suite.
- Shared application-service version/readiness queries exposed through the `oak` CLI and loopback-safe `oak-api` HTTP process.
- Generated OpenAPI 3.1 artifact, strict TypeScript client, and accessible local status shell.
- Local PostgreSQL/API/web Compose harness with health checks and loopback-only published ports.
- Stable Make entrypoints, CI, dependency audits, secret-pattern checks, and development SBOM generation.
- Repository hygiene rules that exclude agent state, secrets, build output, local runtime data, and editor files.
- Separate local-source compatibility from exact CI/container builder pins, with an executable drift check across toolchain files, package metadata, images, CI, and documentation.

### Fixed

- The API container image could not be built. Sprint 6 force-included `policy-packs` into
  the wheel but the image never copied that directory, so `uv sync --frozen` failed inside
  the build with `Forced include not found`. `make build` cannot catch this because it runs
  at the repository root where the directory exists, and CI does not build images. A
  contract test now asserts every wheel force-include is copied into the image.

### Security

- The MCP server and remote CLI are transports that add no authority: MCP frames are
  size-bounded during read (including newline-free floods), an adversarially deep frame is a
  clean parse error rather than a `RecursionError` crash, tool schemas are closed and mirror
  the REST bounds, the four execution-field names remain impossible in any canonical document,
  and the claimed actor/tenant are verified against the bound local identity with the same
  opaque cross-tenant denial as REST. Approval, signing, revocation, dispatch, secret
  resolution, policy override, and runner apply are absent from both new transports by
  construction and pinned out of the MCP tool registry by a capability-matrix contract test.
- Remote CLI mode checks every document it writes locally against the case references in the
  same response, so a control plane that returns a document inconsistent with the case it
  also reports (transport corruption or a buggy/version-skewed server) is refused with
  `OAK-REMOTE-DIGEST`; because that reference is itself server-supplied, the check detects an
  inconsistent server, not a fully malicious one, so remote mode still requires a trusted
  control plane. A malformed or wrong-shape server response is refused with a stable
  `OAK-REMOTE-PROTOCOL` code and exit 2 rather than a stack trace, remote mode sends no secret
  values and derives idempotency keys from content digests, and it fails closed with
  `OAK-REMOTE-UNSUPPORTED` for local-only signing/approval/dispatch/keys/extensions/policy
  commands rather than acting on local state.
- The signed webhook example is verified against a pinned committed publisher key, never the
  key embedded in the envelope; the signing private key was discarded and no private key is
  committed. `oak validate` is read-only, opens files with `O_NOFOLLOW`, parses untrusted YAML with the
  alias-free reader, and refuses any export object, bundle document, or webhook envelope
  carrying a `command`/`shell`/`executable`/`argv` field.
- `cryptography` was upgraded from 46.0.7 to 50.0.0 after `pip-audit` reported four
  advisories (`GHSA-537c-gmf6-5ccf`, `PYSEC-2026-3552`, `PYSEC-2026-3553`,
  `PYSEC-2026-3554`) in the locked version. None is reachable from OAK, which uses
  raw-bytes Ed25519 only and loads no X.509 chain, PKCS#7 structure, or serialized key; the
  advisories were removed rather than suppressed, Ed25519 signature bytes are unchanged so
  existing signed artifacts stay valid, and the pin `>=50,<51` keeps a future major behind
  an explicit review.
- Policy evaluation is fail-closed: an unresolved pointer or type mismatch is undecidable, the
  rule reports unknown, and the pack outcome becomes unknown, so a stale or ambiguous pack can
  never yield an automated allow. Stale, future, or unpublished packs refuse evaluation with
  stable codes.
- Extensions are quarantined by default and become usable only after schema, per-file and
  aggregate payload-digest, compatibility, licence, and embedded-test checks pass and the
  extension-steward signature verifies against a pinned local trust anchor; a key embedded in
  the manifest is a claim, never an anchor. Extension payloads are governed data with no
  dynamic import or downloaded code execution, and the on-disk directory name is the
  authoritative identity.
- The OPA adapter runs only the allowlisted `opa` binary through a fixed argument vector with
  `shell=False`, a sanitized environment, timeouts, and bounded output; pack content reaches
  Rego only as JSON-encoded literals. The built-in engine is the reference implementation and
  the external engine is never an independent oracle: any disagreement is refused with
  `OAK-POLICY-ENGINE-DIVERGED` rather than published as a canonical decision.
- Deployment renderers emit inert declarative files with digest-pinned images and deny-all
  egress defaults, contain no execution fields, write through an atomic path-safe writer, and
  cannot weaken runner verification, adapter allowlists, approval binding, or mutation gates.
- PostgreSQL uniqueness constraints and every repository, operation, outbox, artifact, and
  projection query include tenant/environment scope; cross-tenant REST requests return the
  same safe not-found shape as missing resources.
- API binding remains loopback-only unless explicitly acknowledged, dependency failures expose
  only coarse readiness, request/export sizes are bounded, and problems omit payloads, stack
  traces, provider output, credentials, and private reasoning.
- Worker requests reject command, shell, executable, and argument-vector fields and can invoke
  only deterministic candidate generation, evaluation, or draft bundle compilation. They have
  no approval, signing, runner, secret, target connection, subprocess, or mutation authority.
- Catalogue and target inputs are bounded, schema-validated, alias/symlink safe, and cannot select executable behavior.
- Target profiles are bound to command tenancy and checked for declared platform, capacity, and read-only planning capabilities before bundle publication.
- Immutable evaluation results cannot be overwritten by a second non-idempotent evaluation.
- Runner-plan parameter schemas recursively reject command, shell, executable, and argument-vector fields; Sprint 2 operations are non-mutating and never dispatched.
- Raw brief content remains an untrusted, separate artifact; text instructions cannot invoke tools or approve claims.
- Workspace publication uses a lock and atomic manifest replacement, while import rejects symlinks, corruption, digest mismatch, and artifact identity tampering.
- Idempotent lookup now follows actor/correlation and tenant-context validation.
- The initial harness is non-mutating and binds its API to loopback by default.
- Dependency build hooks are denied by default except for the explicitly reviewed, lockfile-pinned `esbuild` hook.
- Vite was upgraded to 7.3.6 after the initial dependency audit identified high-severity advisories in 7.1.4.
