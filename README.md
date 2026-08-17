<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK Community

OAK Community is a local-first, compiler-shaped control plane for designing, evaluating, and planning AI systems. The current harness provides canonical contract validation, an offline `DesignCase`-to-plan journey, shared application services, a command-line entrypoint, a loopback-safe HTTP API, a minimal web status view, and local container orchestration.

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

These versions build OAK itself. They neither describe nor constrain the hardware or environment for a system that OAK will compile. Sprint 2 compilation receives target capabilities through an explicit validated target profile; later runner work may add a target-side inventory adapter.

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

`oak import` validates every indexed artifact and imports only into a new workspace. Repeating a mutation with the same normalized input and idempotency key returns its original result without adding a case version or audit event. See [local-design-case.md](docs/local-design-case.md) for storage and recovery, and [compiler-flow.md](docs/compiler-flow.md) for candidate, assurance, determinism, and plan safety.

The canonical schemas and public synthetic examples live in `schemas/` and `examples/`. See [development.md](docs/development.md) for command details and [architecture.md](docs/architecture.md) for the enforced boundaries.

## Current limits

Signing, deployment approval, runner dispatch, and target execution are not implemented. The generated runner plan is deliberately unsigned, unapproved, non-mutating, and non-executing. The local file workspace is a reference persistence adapter, not a production metadata store. Progress is tracked in [STATUS.md](STATUS.md).

## Licence

Licensed under the Apache License, Version 2.0. See `LICENSE`.
