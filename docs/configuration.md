<!-- SPDX-License-Identifier: Apache-2.0 -->

# Configuration reference

Every environment variable OAK Community reads. There is no configuration file: the
environment is the whole surface.

A contract test (`tests/contract/test_configuration_reference.py`) fails if a variable is
read by the source and missing from this table, or listed here and read nowhere — so this
document cannot drift from the code.

**Safety-relevant** marks a variable whose value changes a security property, not merely a
path or a label. Read [security/residual-risk.md](security/residual-risk.md) before
changing one.

## Control plane (`oak-api`, `oak-worker`, `oak-db-migrate`, `oak mcp serve`)

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_DATABASE_URL` | *(none — required)* | SQLAlchemy URL of the control-plane metadata database. Every server entrypoint refuses to start without it; there is no SQLite fallback. **Carries a password in the Compose default**, so treat it as a secret | Yes |
| `OAK_ARTIFACT_ROOT` | `.oak/server-artifacts` | Directory holding content-addressed artifact bytes. **Relative by default**, so it resolves against the process working directory — see the warning below | Yes |
| `OAK_HOST` | `127.0.0.1` | Bind address for `oak-api` | Yes |
| `OAK_PORT` | `8080` | Bind port for `oak-api` | No |
| `OAK_ALLOW_NON_LOOPBACK` | `false` | Permits a non-loopback bind. The API refuses one otherwise. Accepted true values are `1`, `true`, `yes` (case-insensitive). **Setting this exposes a service with no authentication** — the actor and tenant are headers, not credentials | Yes |
| `OAK_LOCAL_ACTOR` | `local-user` | Identity the API and MCP server bind requests to. This is a local development identity, not an authenticated principal | Yes |
| `OAK_LOCAL_TENANT` | `local` | Tenant the API, MCP server and worker operate within | Yes |
| `OAK_ENVIRONMENT_ID` | `local` | Environment scope recorded on stored rows. Two deployments sharing a database must not share this | Yes |
| `OAK_COMMIT` | `unknown` | Source revision reported by `/version`. Informational | No |
| `OAK_WORKER_ID` | `oak-worker-local` | Lease holder identity for `oak-worker`. 1–160 characters. Two workers sharing an id will fight over leases | Yes |
| `OAK_WORKER_ONCE` | `false` | Run one worker cycle and exit instead of looping. Intended for tests and one-shot drains | No |

> **`OAK_ARTIFACT_ROOT` defaults to a relative path.** Running `uv run oak-api` from the
> repository root silently creates a server artifact store *inside the source checkout*,
> in the same `.oak` directory name the CLI uses for file workspaces. Set it to an
> absolute path in any deployment you intend to back up — a backup procedure that says
> "copy the artifact root" needs the artifact root to be somewhere you can name.

## Command-line interface

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_SERVER` | *(none)* | Base URL for remote mode; equivalent to `--server`. When set, design-journey commands run against a control plane and local-only commands refuse with `OAK-REMOTE-UNSUPPORTED` | Yes |
| `OAK_ACTOR` | `local-user` | Actor the CLI claims, sent as `X-OAK-Actor` in remote mode | Yes |
| `OAK_REMOTE_TIMEOUT` | *(built-in default)* | Seconds to wait for a remote request and for bounded operation polling | No |

## Packaged data locations

Each of these overrides where OAK looks for data that normally ships inside the wheel.
Pointing one at a directory you do not control hands OAK a different set of canonical
schemas, catalogue entries or policy packs.

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_SCHEMA_DIRECTORY` | packaged `oak/canonical_schemas`, then the source `schemas/` | Canonical JSON Schema directory | Yes |
| `OAK_CATALOGUE_DIRECTORY` | packaged `oak/community_catalogue`, then the source `catalogue/` | Component catalogue snapshot directory | Yes |
| `OAK_POLICY_PACK_DIRECTORY` | packaged `oak/community_policy_packs`, then the source `policy-packs/` | Governed policy-pack directory | Yes |
| `OAK_EXTENSIONS_DIRECTORY` | `~/.oak/extensions` | Extension quarantine and activation store | Yes |

## Signing, approval and dispatch

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_TRUST_DIRECTORY` | `~/.oak/trust` | Holds the control plane's Ed25519 **private keys** and the public identity files used as trust anchors. Back it up separately and protect it like a credential store | Yes |
| `OAK_DISPATCH_MAILBOX` | `~/.oak/mailbox` | Outbound-only mailbox that dispatched leases are written into | Yes |

## Runner (`oak-runner`)

The runner is a separate trust domain and reads its own variables. It never reads the
control plane's.

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_RUNNER_MAILBOX` | *(none — required)* | Mailbox directory the runner reads dispatched leases from | Yes |
| `OAK_RUNNER_HOME` | `~/.oak/runner` | Runner state: journal, consumed nonces, processed dispatches | Yes |
| `OAK_RUNNER_TRUST_ANCHORS` | *(none — required)* | Directory of pinned public identities the runner verifies signatures against. **Never** a key carried inside the document being checked | Yes |
| `OAK_RUNNER_TARGET_PROFILE` | *(none — required)* | Path to the target profile the runner is permitted to act against | Yes |
| `OAK_RUNNER_ID` | `runner.local-fixture-runner` | Runner identity recorded in leases and evidence | Yes |

> `OAK_RUNNER_TRUST_ANCHORS` defaults in the documented single-host walkthrough to the
> same directory as `OAK_TRUST_DIRECTORY`, which also holds the control plane's *private*
> keys. That is acceptable only while both live on one developer machine. Copy just the
> `*.identity.json` files to a separate anchor directory as soon as the runner is
> anywhere else. Recorded as `RR-012` in
> [security/residual-risk.md](security/residual-risk.md).

## Test-only

| Variable | Default | Meaning | Safety-relevant |
|---|---|---|---|
| `OAK_TEST_DATABASE_URL` | *(none)* | Enables the PostgreSQL-gated integration suites. **Unset, those suites skip silently and a green run is not evidence they ran.** See [CONTRIBUTING.md](../CONTRIBUTING.md) | No |
| `OAK_E2E_DOCKER` | *(none)* | Set by `make web-e2e` to enable the Compose-backed browser journey | No |
