<!-- SPDX-License-Identifier: Apache-2.0 -->

# Supported platforms

This is the authoritative statement of where OAK Community `0.7.0` is supported, what
"supported" means for each row, and what is deliberately out of scope. Prerequisites that
used to be scattered across [README.md](../README.md), [development.md](development.md) and
[dependencies.md](dependencies.md) are consolidated here.

Nothing in this document is a production-readiness claim. OAK Community is a local-first
developer release; see [README.md](../README.md) and
[security/residual-risk.md](security/residual-risk.md).

## Install paths

OAK has three install paths with genuinely different requirements. Choose the row you need
before reading the platform table.

| Path | What it gives you | Needs |
|---|---|---|
| **CLI only** | The whole offline `init → design → questions → confirm → candidates → evaluate → select → assure → plan → export` journey, plus `render`, `policy`, `extensions` and `validate`, against a file workspace | Python 3.13 and `uv`. No database, no Docker, no network after install |
| **Control plane** | `oak-api`, `oak-worker`, `oak-db-migrate`, `oak mcp serve`, the REST surface and the web workspace | The CLI row, plus PostgreSQL 17. There is no SQLite fallback: every server entrypoint refuses to start without `OAK_DATABASE_URL` |
| **Signed runner** | `oak dispatch`/`oak-runner` against the local fixture profile, including the container apply/rollback cycle | The CLI row, plus a Docker daemon reachable on its default socket |

The Compose profile is the packaged form of the control-plane row: it supplies PostgreSQL,
the API, the worker and the web bundle, and it pins Python, `uv`, Node.js and `pnpm` inside
the build images so the host needs none of them.

## Platform matrix

"Verified" means the path was exercised on that platform during Sprint 8 release hardening and
the evidence is in [release/0.7.0/](release/0.7.0/). "Expected" means every dependency
publishes a wheel or image for the platform but nobody ran it; treat it as unsupported until
someone does and records it.

| OS | Architecture | CLI only | Control plane | Signed runner | Notes |
|---|---|---|---|---|---|
| macOS 11+ | arm64 (Apple silicon) | Verified | Verified | Verified | The development and rehearsal platform |
| macOS | x86_64 (Intel) | **Not supported** | **Not supported** | **Not supported** | `cryptography` ≥ 49 publishes no macOS x86_64 wheel and there is no vendored Rust toolchain, so dependency installation fails outright. This includes a Rosetta interpreter on Apple silicon |
| Linux (glibc) | x86_64 | Verified | Verified | Expected | glibc ≥ 2.17. CI runs this row on `ubuntu-latest` |
| Linux (glibc) | aarch64 | Expected | Expected | Expected | glibc ≥ 2.28. `psycopg-binary` publishes `manylinux_2_27`/`manylinux_2_28` aarch64 wheels only, so the control-plane row has a higher floor than x86_64 |
| Linux (musl, e.g. Alpine) | x86_64, aarch64 | Expected | Expected | Expected | musl 1.2 wheels exist for both native dependencies |
| Linux (glibc) | armv7l (32-bit ARM) | Expected | **Not supported** | Expected | `cryptography` publishes a `manylinux_2_31_armv7l` wheel but `psycopg-binary` publishes no armv7l wheel **and no sdist**, so there is no server path at any build cost |
| Windows | any | **Not supported** | **Not supported** | **Not supported** | `src/oak/adapters/persistence/file_workspace.py` imports `fcntl` at module scope for workspace locking. The import fails on Windows before anything else runs. WSL2 is Linux and follows the Linux rows |

The glibc floors above are not guesses: they are read from the wheel tags in `uv.lock`, which
is the file that actually decides what installs. `psycopg-binary` 3.3.4 ships **no source
distribution**, so an unlisted platform is a hard cliff rather than a slow source build.

## Prerequisites

### CLI only

- **Python 3.13.12**, the version pinned in `.python-version`. `uv` can provision it when the
  network is reachable.
- **`uv` 0.10.x**; CI and the API container use exact builder version 0.10.8.
- **`git`.** Not obvious and not previously documented: `make check` runs
  `tools/check_repository.py`, which shells out to `git check-ignore`, so the gate needs a real
  working tree. Using the released sdist outside a checkout is fine for *running* OAK; it is
  not enough for running the repository gates.

On macOS, confirm the interpreter is arm64 before anything else — an Intel or Rosetta
interpreter cannot install the dependency set at all:

```bash
uv run python -c "import sysconfig; print(sysconfig.get_platform())"
```

It must print `macosx-11.0-arm64`. If it does not, recreate the environment with
`uv venv --python cpython-3.13.12-macos-aarch64-none .venv`.

### Control plane

- Everything from the CLI row.
- **PostgreSQL 17.** The Compose profile pins `postgres:17.6-alpine` by digest.
- **Node.js 24.18.0** and **`pnpm` 11.15.1** for building the web workspace from source. Not
  needed if you use the container path.

### Signed runner

- Everything from the CLI row.
- **A Docker daemon on its default socket.** The runner's subprocess executor deliberately
  strips `HOME`, `DOCKER_HOST`, `XDG_RUNTIME_DIR` and `TMPDIR` from the child environment as a
  hardening measure, which means a daemon that is only reachable through those variables —
  rootless Docker, Colima, and Podman socket shims are the common cases — is **not** reachable.
  This is a known limitation, not an oversight; it is recorded as `RR-013` in
  [security/residual-risk.md](security/residual-risk.md).

### Browser end-to-end (`make web-e2e`)

- Playwright's Chromium build. On a clean Linux host, `playwright install chromium` is not
  sufficient on its own — the browser also needs its system libraries:

```bash
pnpm --dir web exec playwright install --with-deps chromium
```

`make web-e2e` is not part of `make check`.

## Kubernetes

**OAK Community `0.7.0` ships no Kubernetes profile, and this is a decision rather than an
omission.** `OAK-S8-001` asks for "a documented lightweight Kubernetes profile where
feasible"; it is not feasible for this release, for four specific reasons:

1. **There are no images to pull.** Every Compose service builds from a local context. A
   cluster cannot build from a local context, so a Kubernetes profile presupposes published
   images — which `0.7.0` deliberately does not publish (see
   [release-process.md](release-process.md)).
2. **The API and worker share a filesystem artifact store.** Artifact bytes are
   content-addressed files under `OAK_ARTIFACT_ROOT`; the PostgreSQL JSONB copy is never read
   back. Two pods therefore need `ReadWriteMany` storage or forced co-scheduling, neither of
   which is a "lightweight" profile.
3. **The database password is an inline literal** in `compose.yaml` with no Secret concept
   anywhere in the repository.
4. **Cluster exposure contradicts the documented trust boundary.** The control plane binds
   loopback unless `OAK_ALLOW_NON_LOOPBACK` is set, and the actor/tenant model is header-based
   local identity that [interfaces.md](interfaces.md) already describes as isolation controls
   rather than authentication. Publishing a manifest that sets `OAK_ALLOW_NON_LOOPBACK=true`
   inside a cluster would ship a configuration the threat model says is unsafe.

Items 1 and 2 are mechanical. Items 3 and 4 are a trust-boundary change that Community does
not own: ADR-0012 assigns control-plane-on-Kubernetes, real identity and tenancy to Enterprise.

One clarification, because the naming invites the opposite conclusion: the
`renderer.helm-kubernetes` deployment renderer emits a Helm chart describing the **compiled
target workload** — the system OAK designed for you. It is read-only, it executes nothing, and
it has no relationship to deploying OAK itself.

## What is not tested where

CI (`.github/workflows/ci.yml`) runs `ubuntu-latest` x86_64 only. It has no macOS job, no
arm64 job, and it builds no container image. The macOS arm64 rows in the table above are
verified by local rehearsal, recorded in [release/0.7.0/](release/0.7.0/), not by automation —
so a dependency bump that breaks macOS will not be caught until someone runs it. This is
recorded as `RR-014`.
