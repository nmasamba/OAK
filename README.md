<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK Community

OAK Community is a local-first, compiler-shaped control plane for designing, evaluating, and planning AI systems. The current harness provides canonical contract validation, an offline `DesignCase`-to-plan journey, shared application services, a command-line entrypoint, a loopback-safe HTTP API, a browser architecture workspace, local container orchestration, offline policy evaluation over governed packs, read-only deployment rendering, a governed extension supply chain, a bounded MCP server for authorized agents, a remote CLI mode over the same REST surface, and portal/CI integration through signed event envelopes and a server-free validator.

OAK does not proxy an installed application's inference traffic. The current harness is non-production and contains no hosted-provider requirement, customer credentials, or customer data. The only target mutation it can perform is against an explicitly acknowledged local fixture profile, through a separately signed and approved typed plan.

## Choose a run mode

The container path requires only Docker with Compose. Python, `uv`, Node.js, and `pnpm` are pinned inside the build images and do not need to be installed on the host:

```bash
docker compose up -d postgres api worker web
curl --fail http://127.0.0.1:8080/version
docker compose down
```

The worker is required for the asynchronous candidate-generation, evaluation, and
compilation stages; without it those operations stay queued. The web workspace serves at
`http://127.0.0.1:5173`.

Local source development uses the repository toolchains:

- `uv` 0.10.x; CI and the API container use exact builder version 0.10.8
- Python 3.13.12 from `.python-version`, which `uv` can provision when network access is available
- Node.js 24.18.0 from `.node-version` and `pnpm` 11.15.1 from `package.json`

These versions build OAK itself. They neither describe nor constrain the hardware or environment for a system that OAK will compile. Sprint 2 compilation receives target capabilities through an explicit validated target profile; the Sprint 5 runner additionally provides a bounded target-side inventory adapter that returns sanitized host capabilities as evidence and never selects or weakens compile-time constraints.

## Bootstrap and verify

```bash
make bootstrap
make check
```

After bootstrap, run the entrypoints through the locked environment:

```bash
uv run oak --version
uv run oak-api
curl --fail http://127.0.0.1:8080/version
```

The CLI can launch the same API application:

```bash
uv run oak serve
```

## Compile a local design case

The workflow is offline and uses deterministic interpretation, constraints, estimates, comparison, and fixture evaluation:

```bash
uv run oak init /tmp/oak-demo
cd /tmp/oak-demo
/path/to/OAKCommunity/.venv/bin/oak design \
  /path/to/OAKCommunity/examples/briefs/public-manual-qa.yaml --output yaml
/path/to/OAKCommunity/.venv/bin/oak questions --output json
/path/to/OAKCommunity/.venv/bin/oak confirm \
  --answers /path/to/OAKCommunity/examples/briefs/public-manual-qa-answers.yaml
/path/to/OAKCommunity/.venv/bin/oak candidates --output table
/path/to/OAKCommunity/.venv/bin/oak evaluate candidate-03 --output json
/path/to/OAKCommunity/.venv/bin/oak select candidate-03 \
  --rationale-file /path/to/decision.md
/path/to/OAKCommunity/.venv/bin/oak assure candidate-03 --output ./assurance
/path/to/OAKCommunity/.venv/bin/oak plan candidate-03 \
  --target /path/to/OAKCommunity/examples/targets/local-fixture.yaml \
  --output ./bundle
/path/to/OAKCommunity/.venv/bin/oak export --output ./case-export
```

## Govern policy and render deployments

A compiled case can be evaluated against a governed policy pack and rendered through a
choice of deployment backend, both offline:

```bash
/path/to/OAKCommunity/.venv/bin/oak policy packs
/path/to/OAKCommunity/.venv/bin/oak policy evaluate \
  --pack pack.community-baseline --output json
/path/to/OAKCommunity/.venv/bin/oak render \
  --adapter renderer.helm-kubernetes --output ./rendered
```

Policy evaluation is fail-closed: an undecidable rule makes the whole decision `unknown`,
so a stale or ambiguous pack never yields an automated allow. The built-in engine is the
offline reference; an optional OPA engine (`--engine opa`) must agree with it or the
evaluation is refused rather than published. A decision is a governed artifact recorded in
the case lineage; it gates no transition yet.

`oak render` writes declarative, digest-pinned files read-only and executes nothing —
Kubernetes is not required. Contributors add policy packs and deployment backends as
governed extensions, quarantined on install until digests, compatibility, licence, a pinned
steward signature, and the pack's own tests all verify:

```bash
/path/to/OAKCommunity/.venv/bin/oak extensions install ./my-pack
/path/to/OAKCommunity/.venv/bin/oak extensions verify extension.my-pack
/path/to/OAKCommunity/.venv/bin/oak extensions activate extension.my-pack
```

See [extension-sdk.md](docs/extension-sdk.md) for the extension classes, the contract test
kit, and templates for each.

`oak import` validates every indexed artifact and imports only into a new workspace. Repeating a mutation with the same normalized input and idempotency key returns its original result without adding a case version or audit event. See [local-design-case.md](docs/local-design-case.md) for storage and recovery, and [compiler-flow.md](docs/compiler-flow.md) for candidate, assurance, determinism, and plan safety.

## Review in the browser

With the Compose stack running, the workspace at `http://127.0.0.1:5173` completes the same
journey without the CLI: create a case from a pasted brief, review every interpreted value
with its provenance class (fact, inference, default, correction, unknown), answer the ranked
questions, compare candidates with objective ranges and visible infeasibility reasons,
record the selection and assurance plan, compile and review the bundle with its explicit
plan/approval/apply separation, follow the audit timeline, and download the canonical
export. The browser renders server-returned state and denials; lifecycle authority stays in
the shared application services.

## Use it from an agent, a remote CLI, or a portal

The same workflow is reachable through a bounded MCP server for authorized
engineering agents, through the CLI in remote mode against a running API, and
through developer portals over REST plus signed webhooks — none of which gains
deployment authority:

```bash
# Bounded MCP server on stdio (needs OAK_DATABASE_URL, like the API)
oak mcp serve

# The same CLI, driven against a remote control plane
oak --server http://127.0.0.1:8080 questions design-case.public-manual-qa

# Server-free validation for CI and portals
oak validate bundle ./bundle/
oak validate webhook examples/example-webhook-envelope.yaml \
  --public-key examples/portal/webhook-publisher.identity.json
```

See [interfaces.md](docs/interfaces.md) for setup, the permission model, the
capability matrix, and the operations deliberately unavailable in Community, and
[compatibility.md](docs/compatibility.md) for the versioning and deprecation
policy across every public surface. Backstage and generic-portal starters live
in [examples/backstage/](examples/backstage/README.md) and
[examples/portal/](examples/portal/README.md).

The canonical schemas and public synthetic examples live in `schemas/` and `examples/`. See [development.md](docs/development.md) for command details and [architecture.md](docs/architecture.md) for the enforced boundaries.

## Documentation

[docs/README.md](docs/README.md) is the index. The ones most people need first:

| | |
|---|---|
| [platforms.md](docs/platforms.md) | Where OAK is supported, and where it is not |
| [operations.md](docs/operations.md) | Install, observe, back up, restore, upgrade, troubleshoot, uninstall |
| [configuration.md](docs/configuration.md) | Every `OAK_*` environment variable |
| [error-codes.md](docs/error-codes.md) | Every `OAK-*` code, generated from the source |
| [performance.md](docs/performance.md) | Measured numbers, with the machine they came from |
| [security/residual-risk.md](docs/security/residual-risk.md) | What this release does not defend against |
| [release-process.md](docs/release-process.md) | What a release is, and how to verify one |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setting up, the test topology, the review policy |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |

## Verifying a release

Release artifacts ship with a `SHA256SUMS` manifest:

```bash
sha256sum -c SHA256SUMS
```

Checksums prove the bytes match the manifest. They do **not** prove who produced them:
OAK Community release artifacts are **unsigned**, because no maintainer signing key exists
and this release does not invent one. See
[release-process.md](docs/release-process.md#verifying-a-release).

## Current limits

OAK Community `0.7.0` is a local-first developer release. It carries no production or
customer readiness claim, and no external security review was commissioned for it — every
security statement in this repository records work the project did itself. The complete,
identified list of what is not defended is
[security/residual-risk.md](docs/security/residual-risk.md).

Signing, approval, and runner execution exist only in local development form: keys are labelled `development`, the runner reaches only an isolated non-production fixture target, and the sole permitted mutation is creating and removing one network-isolated, never-started container. Enterprise authentication, remote runner transport, production targets, real secret resolution, and Git provider promotion are not implemented. The local file workspace is a reference persistence adapter, not a production metadata store. Policy decisions are recorded but gate no state transition, and activating a component-manifest or architecture-pattern extension governs the payload without yet adding it to the compiler's catalogue. The bundled policy pack is a synthetic fixture, not legal advice. The MCP server serves one stdio client per process and exposes no approval, signing, dispatch, secret, policy-override, file, or command tool; remote CLI mode trusts the control plane it is pointed at and refuses the local-only signing and runner commands; and Community ships the signed webhook envelope contract and validator but no webhook dispatcher. Progress is tracked in [STATUS.md](STATUS.md).

## Licence

Licensed under the Apache License, Version 2.0. See `LICENSE`.
