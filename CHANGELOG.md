<!-- SPDX-License-Identifier: Apache-2.0 -->

# Changelog

All notable changes to OAK Community are recorded here.

## Unreleased

Sprint 9 — optional model provider and natural-language intake (`OAK-S9-001`–`009`), in
progress. Every entry below holds the four reference digests byte-stable unless it says
otherwise.

### Added

- `tests/integration/test_reference_digests.py` pins the four reference digests recorded at
  `0.7.1` and the canonical bytes of the deterministic intent for the structured brief and a
  new prose brief (`examples/briefs/public-manual-qa-prose.md`), so a change to the
  no-model path cannot pass unnoticed (`OAK-S9-001`).
- `tests/conftest.py` points every test at throwaway model-state directories so no test can
  read or leave behind a developer's provider credential (`OAK-S9-001`).
- `tests/contract/test_secret_shapes.py` proves the secret scan recognises model-provider key
  shapes and that no committed file contains one (`OAK-S9-001`).

- The API refuses requests a same-machine web page or a rebound DNS name could forge
  (`OAK-S9-002`): the `Host` must be a loopback name or an exact `OAK_ALLOWED_HOSTS` entry
  (`OAK-HOST-DENIED`, 400), an `Origin` or `Sec-Fetch-Site` from another site is refused
  (`OAK-ORIGIN-DENIED`, 403), health probes are exempt from the host rule, and the
  model-configuration routes require a loopback host and a same-origin browser. The checks
  are middleware and add nothing to the OpenAPI contract; `tests/integration/
  test_loopback_hardening.py` pins them.
- `oak-api` and `oak serve` mint a per-process capability token into
  `$OAK_CREDENTIALS_DIRECTORY/api-token` (owner-only) at start; `X-OAK-Model-Token` is
  verified with a constant-time comparison (`OAK-MODEL-TOKEN-REQUIRED`, 403) on the model
  routes that later milestones add (`OAK-S9-002`).
- `OAK_ALLOWED_HOSTS`, `OAK_CREDENTIALS_DIRECTORY` and `OAK_MODELS_DIRECTORY` are documented
  in `docs/configuration.md`; the first two join the safety-relevant tuple the contract test
  pins (`OAK-S9-002`).
- The web image's nginx sends `X-Frame-Options: DENY` and a `frame-ancestors 'none'`
  content-security policy, so the workspace cannot be framed (`OAK-S9-002`).

- `oak models` (local-only): `families`, `status`, `set-key <family> [--store auto|keychain|file|env] [--stdin]`, `remove-key`, `select <family> <model_id> [--acknowledge-data-use]`, `clear`, `token`. A key is read from a hidden prompt or standard input and is never accepted as an argument or printed; status shows a salted fingerprint and the backend only (`OAK-S9-003`).
- Credential backends behind `CredentialStorePort`: the operating-system keychain through the optional extra `oak-community[keychain]` (`keyring`, MIT; `keyrings.alt` plaintext backends refused, a missing backend reported and never silently downgraded), an owner-only file store (`0700` directory, `0600` file, atomic rename, owner and mode checked on every read), and documented environment references `OAK_MODEL_KEY_<FAMILY>` that store nothing (`OAK-S9-003`).
- New canonical schema `model-configuration.schema.json` with `examples/example-model-configuration.yaml`: the user's family, model, provider route, default interpreter and discovery snapshot, written owner-only under `OAK_MODELS_DIRECTORY`; it can hold no credential by construction and a test proves the schema has no such property (`OAK-S9-003`).
- `SecretValue` in `oak.domain`: every rendering is `<redacted>`, equality is constant-time, pickling and hashing are refused (`OAK-S9-003`).
- Register `RR-040` (a stored provider key is readable by same-user processes and usable by any local principal that reaches the loopback port and reads the token; backups that include the credential directory contain the key) — count 38 → 39, narrated in `docs/release/0.7.1/release-decision.md` under "The register count, made legible" (`OAK-S9-003`).

### Changed

- The release SBOM and licence inventory export the `keychain` extra so they describe everything the wheel can install; `docs/dependencies.md` carries the Sprint 9 review and records that no runtime HTTP dependency was added (`OAK-S9-003`).
- `models` joins the local-only command list in every document that states it and in the remote-CLI refusal test (`OAK-S9-003`).
- An acknowledged non-loopback bind now prints a warning naming the `Host` allowlist instead
  of returning silently; `RR-027` and `SECURITY.md` describe the browser boundary
  (`OAK-S9-002`).
- `docs/error-codes.md` gains the families "Model provider and interpretation proposals"
  and "Request host and origin guard"; the five existing `OAK-INTERPRETER-*` codes move out
  of "Everything else" (`OAK-S9-002`).
- `tools/check_repository.py` scans for OpenAI, Anthropic, Google, Hugging Face and xAI key
  shapes in addition to private keys, AWS access keys and GitHub tokens (`OAK-S9-001`).
- `tools/check_boundaries.py` forbids the domain, compiler, ports, application and runner
  packages from importing HTTP clients, model-provider SDKs or the OS credential store, with a
  fixture proving the rule fires (`OAK-S9-001`).
- `tests/integration/test_offline_boundary.py` treats `ssl`, HTTP transports and provider
  SDKs as network clients, so a provider adapter cannot reach the network by another name
  (`OAK-S9-001`).

## 0.7.1 — approved 2026-08-27, published 2026-09-03

Pre-launch hardening of the approved-but-never-published `0.7.0`. `0.7.0` was approved on
2026-08-22 as a local-first developer release and never published — no PyPI upload, no
image push, no tag, no GitHub release. This re-cut closes residual risks that `0.7.0`
deliberately recorded rather than fixed. Published as a GitHub Release on 2026-09-03 —
the first published artifact, from which the compatibility promises in
[compatibility.md](docs/compatibility.md) now bind.

### Published

- **GitHub Release `v0.7.1`** (<https://github.com/nmasamba/OAK/releases/tag/v0.7.1>),
  2026-09-03: wheel, sdist, CycloneDX SBOM, licence inventory, `SHA256SUMS` and build
  provenance from the `v0.7.1` run of `release.yml`, verified against `SHA256SUMS` before
  attachment and again anonymously afterwards. Wheel `sha256:d75526f8…`, sdist
  `sha256:b68fe34f…`. Not on PyPI and not in a container registry — each a separate
  decision. The tag was re-cut from `4754c85` to `c614414` with the owner's approval to
  pick up two image-tooling fixes (`scripts/scan_images.py`: the SBOM stamp survives a
  root-owned file; scans build without cache) and a clean-tree rescan; the wheel, sdist
  and all four canonical reference digests are identical across the two.

### Versioning

- **The release is re-cut as `0.7.1` with a fresh approval.** The `RR-032` migration
  changes canonical digests, so the signed `0.7.0` release record would otherwise describe
  a build whose digests no longer match. `0.7.0` stays in the record as approved but
  unpublished; nothing that was approved is republished under its name. The decision
  record is [release/0.7.1/release-decision.md](docs/release/0.7.1/release-decision.md).
- **Canonical digests changed — deliberately, once.** The compiled verification policy is
  now a function of the target profile instead of a hard-coded read-only constant, the
  `not_signed` marker's reason no longer claims signing is unimplemented, and the
  bundle's `compatibility` block stops asserting read-only constraints for
  mutation-capable targets (`RR-032`, `RR-011`; `minimum_oak_version` moves to `0.7.1`).
  These fields are canonical bytes, so the reference-case digests shift, exactly as
  [compatibility.md](docs/compatibility.md) rule 4 requires this entry to say. At case
  `0.1.7`, `deployment_bundle` moved from `sha256:042313be…` to
  `sha256:570abb66ee53eb6433588b865fb4a77dc4d5d7133bc1275fbe433a9a37936596` and
  `runner_plan` from `sha256:5e0a65ba…` to
  `sha256:fad309590f1d09da0019f52dce9bd3d31da5b6285f5246d899657a8f161e18c4`;
  `selected_candidate` (`sha256:576b0ca6…`) and `semantic_manifest` (`sha256:2ef34758…`)
  were recompiled on both sides and are byte-identical. Stated fully: the corrected
  review artifacts themselves (the signature marker and the verification policy) change
  digest, as does the mutation-target semantic manifest whose `operation_kinds` is now
  target-derived; the two *spine* documents above are the ones the recorded reference
  baseline tracks, and the two untouched reference digests bound the blast radius. No schema shape changed, previously
  stored workspaces remain valid and importable, and nothing was ever published under the
  old digests. The runner now enforces the policy it is handed: a requested operation
  kind outside `allowed_operation_kinds`, a mutating kind under
  `mutation_allowed: false`, or a malformed clause denies the dispatch
  (`OAK-RUNNER-POLICY`) before any adapter is constructed.

### Security

- **Revocation notices are signed, inventoried, and the channel fails closed**
  (`RR-001`, closed — one of the two standing conditions on the `0.7.0` approval).
  `oak revoke-approval` publishes a notice signed in the `approver` role against the new
  `revocation.schema.json` **and a signed revocation manifest**
  (`revocation-manifest.schema.json`) inventorying the complete set by canonical digest
  with a strictly monotonic sequence. The runner verifies everything against pinned
  anchors and denies every pending dispatch (`OAK-RUNNER-REVOCATION`) on: a notice set
  that does not match the manifest, a sequence regressing below the high-water mark the
  runner records in its own home, a missing manifest on a dispatched mailbox, a missing
  directory, or any unreadable, oversized, malformed or unsigned entry. The manifest
  exists because the closing audit refuted the first fix: signing the notices alone
  still let deletion of one *valid* notice restore its approval. Every variant of the
  attack — single-notice deletion, whole-set deletion, set rollback — is a regression
  test.
- **The runner verifies what the container runtime actually resolved** (`RR-003`,
  closed — the other standing condition). After `docker create`, the adapter requires a
  `RepoDigests` entry carrying the approved digest and removes the container on
  mismatch, missing identity or inspect failure (`OAK-RUNNER-IMAGE`). A target profile
  may declare `execution.allowed_registries` (optional, additive), enforced during
  verification before any adapter exists (`OAK-RUNNER-REGISTRY`); the shipped mutation
  fixture allowlists `docker.io`. `TM-08` moves from partial to direct in
  [threat-coverage.md](docs/security/threat-coverage.md).
- **The web image runs unprivileged and Compose is hardened** (`RR-037`, closed). The
  runtime base is `nginxinc/nginx-unprivileged:1.29.1-alpine` (uid 101, verified in the
  running container by a docker-gated e2e test); every Compose service gets
  `cap_drop: [ALL]`, `no-new-privileges`, a read-only root filesystem where the image
  tolerates one, `tmpfs` mounts and memory/CPU ceilings, with postgres keeping exactly
  the six capabilities its entrypoint needs — proven against a fresh data volume.
- **The toolchain check now checks the running binaries** (`RR-034`, closed).
  `package.json`'s `devEngines.runtime` makes pnpm download and run the pinned Node
  itself — the `0.7.0` web artifacts were built on Node 22.17.1 against a 24.18.0 pin
  with every declaration-only gate green, partly because the deleted `nodeVersion`
  setting made `engineStrict` evaluate engines against the declared version.
  `make toolchain-check` now fatally compares the running Python and the
  pnpm-provisioned Node against the pins, and additionally guards the previously
  unchecked nginx-runtime, Compose PostgreSQL and API build-stage pins.
- **The container images carry SBOMs and provenance** (`RR-038`, closed).
  `make scan-images` and the release workflow's `images` job emit one CycloneDX SBOM
  per image — generated by the pinned socketless scanner from the exported tarball, so
  it describes the shipped final stage — plus an unsigned `image-provenance.json`.
  The `0.7.1` rescan after the web base change found **zero fixable findings**, with
  the web image clean at every severity; the API residue is unchanged (`RR-036`).

### Added

- **An illustrated user manual** at [docs/manual/](docs/manual/): the end-to-end journey
  from a clean machine through the CLI pipeline, the browser workspace (with screenshots
  captured from a live Compose stack), the signed runner including what each denial
  family means, artifact verification, troubleshooting, and complete uninstall. The
  authoritative source is `manual.html`; the committed PDF is a rendering of it, and
  the chapters 3 and 5 commands were verified by running those journeys end to end
  against the tree, and the expected-output excerpts are what those runs printed.
- **`scripts/generate_examples.py`** regenerates the signed protocol examples from a
  live fixed-clock compile-sign-approve-dispatch-revoke run, and a contract test now
  verifies every signed example cryptographically, so the examples' digests and
  signatures can no longer silently rot after a compiler change.
- **`schemas/revocation.schema.json` and `schemas/revocation-manifest.schema.json`**,
  with generated, really-signed `examples/example-revocation.yaml` and
  `examples/example-revocation-manifest.yaml`.

### Changed

- The verification policy's artifact id is now `verification-policy.<target id>` rather
  than a constant, and the semantic manifest's `operation_kinds` reflects the target's
  allowed operations — both part of the digest migration above.
- The signed protocol examples were regenerated with post-migration digests.
- `docs/compatibility.md` states explicitly that its promises bind external consumers
  from the first published artifact, and that no `0.7.x` artifact has been published.
- The completed exec plans' `Owner/agent:` lines describe the author neutrally
  ("owner-directed coding agent") instead of naming an AI vendor; historical branch-name
  identifiers inside the progress logs are repository facts and stay. The
  document-policy gate (`tools/check_repository.py`) now scans `.html` documents for
  assurance vocabulary and product references, and `.html`/`.mjs` files for secret
  patterns, so the user manual sits under the same honesty gates as the markdown corpus.

### Found and fixed by the closing adversarial audit

The plan's closing audit (eight finder lenses, one independent refute-by-default skeptic
per finding) raised 23 findings; the skeptics and a manual pass over the unjudged
remainder confirmed 15. Every confirmed finding is fixed below or recorded in the exec
plan's audit section; the most consequential:

- **The revocation manifest above** — the audit's highest-value finding refuted the
  first RR-001 fix's central claim.
- **The consumed-nonce replay ledger failed open and could erase itself.** A corrupt
  `consumed-nonces.json` read as an empty set, and the next consume rewrote the file
  from that read — permanently destroying every previously burned nonce. Both the read
  and the consume now refuse (`OAK-RUNNER-REPLAY`) until an operator intervenes, and the
  rewrite is atomic (`os.replace`).
- **A hung docker command could leak an unverified container and kill the runner.**
  `subprocess.TimeoutExpired`/`OSError` from any docker invocation now surfaces as
  `OAK-RUNNER-SUBPROCESS` (a typed denial the journal and failure actions handle) rather
  than a raw traceback, and *any* failure between `docker create` and a verified digest
  — including a timeout raised mid-inspection — removes the container before denying
  with `OAK-RUNNER-IMAGE`.
- **The image SBOMs never made it into version control.** `.gitignore`'s blanket
  `*.cdx.json` silently excluded the very evidence the committed release record cited;
  release evidence under `docs/release/` is now explicitly un-ignored and the SBOMs are
  committed.
- **The evidence's image identity is now the scanner's own config digest.**
  `docker image inspect {{.Id}}` is store-dependent (manifest digest under containerd)
  and contradicted the `ImageID` the scanner records inside the same SBOM; the
  `oak:image` stamp and the provenance now bind to the scanner's value, so the evidence
  set is mutually verifiable from the artifacts alone. Provenance also records
  `images_rebuilt`, and the dirty-tree computation excludes whatever directory the
  evidence is being written to, so a clean CI checkout no longer reports itself dirty.

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
  [error-codes.md](docs/error-codes.md) (generated; 245 codes were previously
  undocumented).
- **Container image scanning** (`make scan-images`), pinned to `aquasec/trivy:0.74.0`,
  failing the build on any *fixable* CRITICAL or HIGH and reporting unfixable findings
  without failing. The first run found 6 CRITICAL and 72 HIGH in the API image and 3 and 33
  in the web image; see
  [release/0.7.0/container-scan.md](docs/release/0.7.0/container-scan.md).
- **Security record**: [SECURITY.md](SECURITY.md),
  [threat-coverage.md](docs/security/threat-coverage.md) mapping all nineteen threat ids to
  the tests that exercise them, and [residual-risk.md](docs/security/residual-risk.md) with
  39 stable-id entries. A build gate now rejects unqualified assurance vocabulary.
- **Measurements**: [performance.md](docs/performance.md) and a provenance-stamped
  `scripts/benchmark.py`. Reference compiler 8.66 s median against a 120 s requirement;
  interactive read p95 30 ms against 500 ms; workspace manifest reads grow from 3.8 ms at
  zero artifacts to 283.3 ms at 43, with no compaction anywhere (`RR-030`).
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

Published in [security/residual-risk.md](docs/security/residual-risk.md) — 38 entries,
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
