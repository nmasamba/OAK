<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release-candidate rehearsal — OAK Community 0.7.0

`OAK-S8-008`. What was actually run, on what, and what it produced. Where a step found a
defect, the defect is recorded here rather than quietly fixed and forgotten.

## Machine

| | |
|---|---|
| Host | macOS 26.3.1, arm64 (Apple silicon), 10 CPUs, 64 GiB RAM |
| Python | CPython 3.13.12 (`macosx-11.0-arm64`) |
| Node / pnpm | 22.17.1 / 11.15.1 — **note the drift below** |
| Docker | Docker Desktop, arm64 daemon, buildx available |
| PostgreSQL | `postgres:17.6-alpine`, digest-pinned by `compose.yaml` |

## Network posture

Dependencies and base images were acquired first, then every build and verification step
was re-run offline against the caches:

- `UV_OFFLINE=1 uv sync --frozen --offline` → `Audited 91 packages`, no network.
- `UV_OFFLINE=1 python scripts/build_release.py` → completed, including the second build
  used for the reproducibility comparison and the clean-environment install.

Two things genuinely need the network and are recorded as such rather than claimed
offline: `make audit` (`pip-audit` and `pnpm audit` query advisory databases) and the
first acquisition of dependencies and base images.

## Steps and results

### 1. Full gate

`make check` with `OAK_TEST_DATABASE_URL` set against the pinned PostgreSQL 17.6.
Green, verified by **counting `make: ***` lines: 0** — not by the exit code, which the
wrapper reports as success even when the gate failed.

- 376 unit and contract tests
- 165 integration tests, 4 skipped (file-only parameter cases), **including** the
  PostgreSQL-gated suites that CI silently skips (`RR-019`)
- 27 end-to-end tests
- validate, format, lint, boundaries, hygiene, toolchain, strict mypy over 120 files,
  generated-OpenAPI compatibility, web build

### 2. Browser journey and accessibility

`make web-e2e` against the Compose stack: **3 passed** — the full brief-to-compiled-bundle
reviewer journey, a denied stale action with visible recovery, and an interrupted operation
cancelled cooperatively across a worker restart. Zero axe violations.

### 3. Release build, offline

`make release`:

- Built twice into separate directories; digests compared and identical. The build refuses
  to finish otherwise.
- Installed the built wheel into a throwaway environment holding only the locked runtime
  closure, with hashes verified.
- Ran the installed console script from a directory outside the checkout and confirmed
  canonical schemas, the community catalogue and the policy packs all resolve *from inside
  the installed package* — the branch every other end-to-end test misses, because `.venv`
  is an editable install.
- Emitted the release SBOM (34 components, subject stamped with the wheel and sdist
  digests), the generated licence inventory, and `SHA256SUMS`.

### 4. Verification, including the refusal path

`make verify-release` → all four artifacts `OK`, exit 0, and `build-provenance.json`
correctly reported as present-but-unlisted.

Tampered copy — one appended byte to the wheel:

```
FAILED   oak_community-0.7.0-py3-none-any.whl: expected sha256:2784b77d…, got sha256:d8ac4b2b…
1 artifact(s) do not match SHA256SUMS. Do not install them.
exit=2
```

### 5. Linux x86_64, inside the released image

`docker buildx build --platform linux/amd64` then the reference CLI journey inside it:

```
arch: x86_64
libc: ldd (Debian GLIBC 2.41-12+deb13u2) 2.41
0.7.0
candidates: 4
journey-ok
```

Running as uid `oak`, non-root. This is the evidence behind the Linux x86_64 "CLI only —
Verified" row in [platforms.md](../../platforms.md).

### 6. Compose control plane, backup and restore

The stack rebuilt from source, then the backup and restore procedure in
[operations.md](../../operations.md) run **verbatim**:

- `/version` direct and web-proxied: `0.7.0`; API container `aarch64`, user `oak`,
  Debian glibc 2.41.
- A real design case created through `POST /v1/design-cases`.
- `pg_dump -Fc` (34 KB) and a `tar` of the artifact volume (1.8 KB), taken with writers
  stopped.
- Both volumes destroyed; database and artifact store restored into clean volumes.
- The case is readable after restore, at the same version and status.
- `scripts/verify_deployment.py` against a **wrong** artifact root: `4 of 4 indexed
  artifact(s) … could not be verified`. Against the real restored root: `verified 4
  indexed artifact(s): every object present, correctly sized, and digest-matching`.

## Defects the rehearsal found

Recorded because the point of a rehearsal is what it catches.

| Found | Consequence | Resolution |
|---|---|---|
| `docker compose up -d` served **`0.5.0.dev5`** from a three-day-old cached image | The README's own quickstart silently runs whatever you built last. Nothing warns you; `/version` is the only thing that reveals it | README and operations runbook now use `--build` and tell the reader to check `/version`, with the incident as the reason |
| The restore-verification step could not be run against a Compose deployment | `OAK_DATABASE_URL` and `OAK_ARTIFACT_ROOT` name `postgres:5432` and a path *inside* the containers, so the documented command cannot work from the operator's shell | The runbook now carries the port-publish and volume-copy sequence this rehearsal actually used |
| `oak` was not on `PATH` under `sh -lc` | A login shell resets `PATH` and loses the image's virtualenv | Rehearsal uses `sh -c`; noted here because it will bite anyone scripting against the image |

## Known deviations from a true clean room

Stated rather than glossed:

- **Not a fresh machine.** The rehearsal ran on the development host with warm `uv`,
  `pnpm` and Docker layer caches. Offline mode proves the *lockfiles* are sufficient; it
  does not prove a first-ever acquisition on an empty machine.
- **Node.js drift.** The host runs **22.17.1** while `.node-version`, `package.json` and
  `pnpm-workspace.yaml` all pin **24.18.0**. Every web gate passed anyway, and `pnpm`'s
  `engineStrict` did not catch it: the toolchain contract compares declarations against
  each other, never against the running binary. So the web artifacts in this rehearsal
  were built on an unpinned interpreter. CI builds on the pinned one.
- **One architecture for the control plane.** The Compose stack ran as linux/arm64. The
  linux/amd64 evidence covers the CLI path only, which is why the x86_64 control-plane
  row in [platforms.md](../../platforms.md) says Expected rather than Verified.
- **Images are not byte-reproducible** (`RR-006`), so no image digest here is something to
  reproduce. It is a record of what one build produced.
