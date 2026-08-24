<!-- SPDX-License-Identifier: Apache-2.0 -->

# Development guide

Local source development uses Python 3.13.12, Node.js 24.18.0, `uv` 0.10.x, and `pnpm` 11.15.1. Dependencies are locked in `uv.lock` and `pnpm-lock.yaml`; those lockfiles do not pin the `uv` executable itself. Contributors use `.python-version` and `.node-version`, while `package.json` pins `pnpm`.

macOS contributors need an arm64 Python 3.13.12 interpreter. From `cryptography` 49.0.0 the project no longer publishes macOS x86_64 wheels, so an Intel or Rosetta interpreter falls through to the source distribution and cannot build it without a Rust toolchain.

CI and container builds are the reproducible builder boundary. They pin `uv` 0.10.8 and the exact Python and Node runtimes; container users need only Docker with Compose on the host. The source-development compatibility range exists for contributor convenience and is not a target-hardware contract. OAK compilation receives target capabilities through explicit invocation data, currently a bounded target profile. It never treats the control-plane host as the deployment target. A later target-side inventory adapter must preserve that boundary.

## Commands

| Command | Purpose |
|---|---|
| `make bootstrap` | Install locked Python and web dependencies |
| `make lock` | Re-resolve both lockfiles. Prefer `uv lock --upgrade-package <name>` for a single Python dependency; this target also rewrites `pnpm-lock.yaml` |
| `make toolchain-check` | Check local, CI, container, package, and documentation toolchain declarations for drift |
| `make validate` | Validate canonical schemas, examples, generated files, and documentation policy |
| `make format` | Apply deterministic Python and web formatting |
| `make format-check` | Check formatting without changes |
| `make lint` | Run Python lint, import boundaries, unsafe-execution checks, and repository hygiene checks |
| `make typecheck` | Run strict Python and TypeScript checking |
| `make test` | Run unit and contract tests |
| `make test-integration` | Run local API integration tests |
| `make test-e2e` | Run CLI/API user-visible smoke tests |
| `make openapi-compatibility` | Reproduce OpenAPI/client output and reject local breaking changes |
| `make web-build` | Build the production web bundle |
| `make web-e2e` | Run the Playwright browser journey and accessibility suite against the Compose stack |
| `make build` | Build Python and web artifacts from bootstrapped dependencies without network |
| `make sbom` | Generate a development dependency SBOM under ignored `sbom/`. The *release* SBOM is different and comes from `make release` |
| `make audit` | Audit the Python and web dependency closures for known advisories. Needs network |
| `make scan-images` | Build and scan both container images, failing on any **fixable** CRITICAL or HIGH. Needs Docker and network; see [release-process.md](release-process.md) |
| `make check` | Run the non-destructive repository gate |
| `make release` | Build the release artifacts, SBOM, licence inventory and checksums; see [release-process.md](release-process.md) |
| `make verify-release` | Verify a release directory against its `SHA256SUMS` |
| `make clean` | Empty the `uv` cache |
| `make clean-all` | Remove every build artifact, virtual environment and cache in the tree. It does **not** touch a `.oak` workspace — that is your data; see [operations.md](operations.md#uninstall) |

The bootstrap step may use the public package registries. After dependencies are installed, `make check` requires no hosted service, credentials, model provider, database, or public network. It does require `git`: `tools/check_repository.py` shells out to `git check-ignore`.

**`make check` reports success wrongly when backgrounded.** Verify it by counting `make: ***` lines in its output rather than by its exit code.

**The PostgreSQL-gated integration suites skip silently.** Around twenty integration tests need `OAK_TEST_DATABASE_URL`, and a skip is indistinguishable from a pass in the summary line. `compose.yaml` publishes no host port for PostgreSQL, so run them like this:

```bash
cat > compose.override.yaml <<'YML'
services:
  postgres:
    ports:
      - "127.0.0.1:15432:5432"
YML
docker compose up -d postgres
export OAK_TEST_DATABASE_URL=postgresql+psycopg://oak:oak-local-only@127.0.0.1:15432/oak
make test-integration
```

CI never sets it, so a green CI run is not evidence those suites ran. Recorded as `RR-019` in [security/residual-risk.md](security/residual-risk.md).

## Local DesignCase workflow

Run the local workflow from the locked environment:

```bash
uv run oak init /tmp/oak-demo
cd /tmp/oak-demo
/path/to/OAKCommunity/.venv/bin/oak design /path/to/brief.yaml --output yaml
/path/to/OAKCommunity/.venv/bin/oak questions --output json
/path/to/OAKCommunity/.venv/bin/oak confirm --answers /path/to/answers.yaml
/path/to/OAKCommunity/.venv/bin/oak candidates --output table
/path/to/OAKCommunity/.venv/bin/oak evaluate candidate-03 --output json
/path/to/OAKCommunity/.venv/bin/oak select candidate-03 --rationale-file /path/to/decision.md
/path/to/OAKCommunity/.venv/bin/oak assure candidate-03 --output ./assurance
/path/to/OAKCommunity/.venv/bin/oak plan candidate-03 \
  --target /path/to/OAKCommunity/examples/targets/local-fixture.yaml \
  --output ./bundle
/path/to/OAKCommunity/.venv/bin/oak export --output ./case-export
```

`oak design` accepts bounded regular `.yaml`, `.yml`, `.json`, `.md`, `.markdown`, and `.txt` files. YAML aliases, duplicate keys, malformed/deep structures, non-UTF-8 content, Unicode control characters, symlinks, unsupported types, empty files, and files over 256 KiB are rejected before state is published. Confirmation files are bounded YAML or JSON and contain at most five decisions.

Commands discover the nearest parent workspace. Mutations use expected versions and normalized-input idempotency; pass `--idempotency-key` when a caller needs to control the retry key. Human output is the default, while `--output json` and `--output yaml` are stable machine-readable views. Diagnostics go to stderr and failures leave the prior manifest authoritative.

See [local-design-case.md](local-design-case.md) for workspace portability and recovery details, and [compiler-flow.md](compiler-flow.md) for catalogue, candidate, evaluation, assurance, and non-executing plan behavior.

## Local API

```bash
export OAK_DATABASE_URL=postgresql+psycopg://oak:oak-local-only@127.0.0.1:5432/oak
export OAK_ARTIFACT_ROOT="$PWD/.oak/server-artifacts"
uv run oak-db-migrate
uv run oak-api
# In another terminal, with the same environment:
uv run oak-worker
```

The default address is `http://127.0.0.1:8080`. Use `OAK_HOST` and `OAK_PORT` for local process configuration. A non-loopback host is rejected unless `OAK_ALLOW_NON_LOOPBACK=true` is also set.

Persistent mutations require `Idempotency-Key`; case successors additionally require
`If-Match` with the current ETag. Community local mode accepts only the configured
`OAK_LOCAL_ACTOR` and `OAK_LOCAL_TENANT` (defaults `local-user` and `local`). These headers are
local isolation controls, not enterprise authentication. The worker compiles/evaluates typed
artifacts only and cannot approve, dispatch, contact, or mutate a target.

## Compose

```bash
docker compose up -d postgres migrate api worker web
docker compose ps
docker compose down
```

Compose applies the forward baseline before starting API/worker, publishes API and web ports
on loopback, and keeps PostgreSQL on the project network. The named artifact and PostgreSQL
volumes survive normal teardown. Compose does not start a runner or external model service;
`oak-runner` is a separate outbound-only process an operator starts deliberately. Use `docker compose down --volumes` only when intentionally deleting local state.

## MCP, remote CLI, and portals

The bounded MCP server, the CLI's remote (`--server`) mode, and the portal/webhook
integrations share the same application services as everything above and are documented in
[interfaces.md](interfaces.md) (setup, permission model, capability matrix) and governed by
[compatibility.md](compatibility.md). Quick forms:

```bash
# Bounded MCP server on stdio (same OAK_DATABASE_URL configuration as oak-api)
oak mcp serve

# The design journey over REST from the same CLI
oak --server http://127.0.0.1:8080 design ./brief.yaml
oak --server http://127.0.0.1:8080 evaluate candidate-03 --case design-case.public-manual-qa

# Server-free validation for CI and portals
oak validate export ./case-export/
oak validate bundle ./bundle/
oak validate webhook examples/example-webhook-envelope.yaml \
  --public-key examples/portal/webhook-publisher.identity.json
```

The MCP surface is design/read only: it cannot approve, sign, dispatch, resolve a secret,
override policy, select a candidate, run a command, or read a file. Remote mode maps only
commands that have a REST surface. The local-only commands are
`init`, `serve`, `mcp serve`, `keys`, `sign`, `approve`, `revoke-approval`, `dispatch`, `ingest`, `gitops`, `policy`, `render`, `extensions` and `validate`;
with a server set they refuse with `OAK-REMOTE-UNSUPPORTED` rather than acting on local state.

## Signed runner

Signing, approval, dispatch, and the separate `oak-runner` process are documented in
[signed-runner.md](signed-runner.md). The short form from a compiled workspace:

```bash
oak keys init
oak sign
oak approve dry_run
oak dispatch inventory validate render plan verify
OAK_RUNNER_MAILBOX="$HOME/.oak/mailbox" \
  OAK_RUNNER_TRUST_ANCHORS="$HOME/.oak/trust" \
  OAK_RUNNER_TARGET_PROFILE=examples/targets/local-fixture.yaml \
  oak-runner run-once
oak ingest --output json
```

See [the migration guide](../migrations/README.md) before a schema change. Stop writers and
take a database backup before future forward migrations. Supported recovery restores into a
clean database and then runs `oak-db-migrate`; `alembic downgrade` is intentionally not
an OAK recovery mechanism.

## Browser end-to-end

The Playwright suite drives the web workspace at `http://127.0.0.1:5173` and expects the
full Compose stack (`postgres`, `api`, `worker`, `web`) to be healthy. Install the pinned
browser once after bootstrap:

```bash
pnpm --dir web exec playwright install chromium
docker compose up -d postgres api worker web
make web-e2e
```

The suite covers the complete reference journey with automated axe accessibility checks on
every core screen, a denied stale-version transition with its recovery path, and an
interrupted operation that is cancelled cooperatively; that last scenario stops and
restarts the Compose `worker` service, so it requires Docker control and is skipped unless
`OAK_E2E_DOCKER=1` (which `make web-e2e` sets). Override `OAK_WEB_BASE_URL` and
`OAK_API_BASE_URL` to target other local origins. Browser binaries download from the
Playwright CDN; everything else runs locally.
