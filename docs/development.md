<!-- SPDX-License-Identifier: Apache-2.0 -->

# Development guide

Local source development uses Python 3.13.12, Node.js 24.18.0, `uv` 0.10.x, and `pnpm` 11.15.1. Dependencies are locked in `uv.lock` and `pnpm-lock.yaml`; those lockfiles do not pin the `uv` executable itself. Contributors use `.python-version` and `.node-version`, while `package.json` pins `pnpm`.

CI and container builds are the reproducible builder boundary. They pin `uv` 0.10.8 and the exact Python and Node runtimes; container users need only Docker with Compose on the host. The source-development compatibility range exists for contributor convenience and is not a target-hardware contract. A future OAK compilation receives target capabilities through its invocation data or a target-side inventory adapter, never by treating the control-plane host as the deployment target.

## Commands

| Command | Purpose |
|---|---|
| `make bootstrap` | Install locked Python and web dependencies |
| `make toolchain-check` | Check local, CI, container, package, and documentation toolchain declarations for drift |
| `make validate` | Validate canonical schemas, examples, generated files, and documentation policy |
| `make format` | Apply deterministic Python and web formatting |
| `make format-check` | Check formatting without changes |
| `make lint` | Run Python lint, import boundaries, unsafe-execution checks, and repository hygiene checks |
| `make typecheck` | Run strict Python and TypeScript checking |
| `make test` | Run unit and contract tests |
| `make test-integration` | Run local API integration tests |
| `make test-e2e` | Run CLI/API user-visible smoke tests |
| `make build` | Build Python and web artifacts from bootstrapped dependencies without network |
| `make sbom` | Generate a development dependency SBOM under ignored `sbom/` |
| `make check` | Run the non-destructive repository gate |

The bootstrap step may use the public package registries. After dependencies are installed, `make check` requires no hosted service, credentials, model provider, database, or public network.

## Local API

```bash
uv run oak-api
```

The default address is `http://127.0.0.1:8080`. Use `OAK_HOST` and `OAK_PORT` for local process configuration. A non-loopback host is rejected unless `OAK_ALLOW_NON_LOOPBACK=true` is also set.

## Compose

```bash
docker compose up -d postgres api web
docker compose ps
docker compose down
```

Compose publishes API and web ports on loopback and keeps PostgreSQL on the project network. The default project does not start a runner or external model service. Use `docker compose down --volumes` only when intentionally deleting local database state.
