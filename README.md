<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK Community

OAK Community is a local-first, compiler-shaped control plane for designing, evaluating, and planning AI systems. This repository currently provides the Sprint 0 walking skeleton: canonical contract validation, shared application queries, a command-line entrypoint, a loopback-safe HTTP API, a minimal web status view, and local container orchestration.

OAK does not proxy an installed application's inference traffic. The current harness is non-production and contains no target mutation path, hosted-provider requirement, customer credentials, or customer data.

## Choose a run mode

The container path requires only Docker with Compose. Python, `uv`, Node.js, and `pnpm` are pinned inside the build images and do not need to be installed on the host:

```bash
docker compose up -d postgres api web
curl --fail http://127.0.0.1:8080/version
docker compose down
```

Local source development uses the repository toolchains:

- `uv` 0.10.x; CI and the API container use exact builder version 0.10.8
- Python 3.13.12 from `.python-version`, which `uv` can provision when network access is available
- Node.js 24.18.0 from `.node-version` and `pnpm` 11.15.1 from `package.json`

These versions build OAK itself. They neither describe nor constrain the hardware or environment for a system that OAK will compile. Target capabilities enter through an explicit target profile or a target-side inventory adapter when those compiler stages are implemented.

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

The canonical schemas and public synthetic examples live in `schemas/` and `examples/`. See [development.md](docs/development.md) for command details and [architecture.md](docs/architecture.md) for the enforced boundaries.

## Current limits

This sprint intentionally does not implement case intake, candidate evaluation, plan compilation, a persistent metadata store, or target execution. Unsupported commands are not presented as successful behavior. Progress is tracked in [STATUS.md](STATUS.md).

## Licence

Licensed under the Apache License, Version 2.0. See `LICENSE`.
