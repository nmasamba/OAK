<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release-candidate rehearsal — OAK Community 0.9.0

Run on 2026-09-30, while `0.9.0` was being cut and before anyone signed its decision
record. The `0.8.0` rehearsal was run only after that release had been signed, so its
decision record had to say "inherited" and then add an addendum; this one is evidence the
signers can read first. What follows is what was actually run, on what, and what it
produced. Where a step found a defect, it is recorded here.

It repeats the six steps of the [`0.8.0` rehearsal](../0.8.0/clean-room.md), so the two are
comparable. Two checks are new for `0.9.0`:
- `oak architecture` inside the image, after the CLI journey;
- a second browser-suite run against the same database, to prove the re-runnability fix
  from `0.8.0`.

## Machine

| | |
|---|---|
| Host | macOS 26.3.1, arm64 (Apple silicon), 10 CPUs, 64 GiB RAM |
| Python | CPython 3.13.12 |
| Node / pnpm | pnpm 11.15.1 provisions the pinned Node 24.18.0 for every web step (`devEngines.runtime`); the shell's own Node is 22.17.1 and is not used |
| Docker | 29.3.1 for the image scan, then **29.8.1**: Docker Desktop updated itself at 12:45 UTC, mid-rehearsal (see step 1); buildx 0.37.1 |
| PostgreSQL | `postgres:17.6-alpine`, digest-pinned by `compose.yaml` |
| Tree | `d5717de` on `release-0.9.0`, in a separate worktree, clean (`source_tree_dirty: false` in both the release and benchmark provenance); the image scan ran at `c067aad` |

## Network posture

Dependencies were synced from the lockfile offline (`UV_OFFLINE=1 uv sync --frozen
--offline`). As at `0.8.0`, that leaves out the optional `keychain` extra, so every step
below ran without `keyring`, which is what a first-time installer has. `make check` and
`make release` both ran with `UV_OFFLINE=1`.

The same three things need the network and are recorded as such:
- `make audit`, which reads advisory databases;
- the first acquisition of dependencies and base images;
- the image builds. Both images were built `--no-cache --pull` for the scan, and the web
  image's `pnpm install` runs inside the container.

## Steps and results

### 1. Full gate, offline

`make check` with `OAK_TEST_DATABASE_URL` against a throwaway PostgreSQL 17.6 on
`127.0.0.1:15433` (not the default stack's database). The gate was green, verified by
**counting `make: ***` lines: 0**:

- 751 unit and contract tests, 1 skipped
- 313 integration tests, 4 skipped, **including** the PostgreSQL-gated suites that CI
  skips (`RR-019`)
- 43 end-to-end tests, including the real-daemon install-test-observe journey and the MCP
  handshake
- validate, format, lint, boundaries, hygiene, toolchain, strict mypy over **140** source
  files, generated-OpenAPI compatibility, web build

**The first run did not pass, and the cause was the machine.** Docker Desktop updated
itself from 29.3.1 to 29.8.1 at 12:45:54 UTC, two minutes before the gate started. The
restart stopped the throwaway database container, which had no restart policy. The first
run therefore failed ten PostgreSQL tests and errored ten. Fifteen reported
`connection refused` on `15433`, and five failed on the `500 OAK-INTERNAL` responses that
the refused connection caused behind the API. After `docker start`, the twenty affected tests passed on their own, and the
whole gate was re-run from the start with the counts above. Nothing in the tree changed
between the two runs.

### 2. Browser journey and accessibility

`make web-e2e` against a throwaway Compose stack (`oak-rel090`), rebuilt from the release
tree. The suite reached it with `COMPOSE_PROJECT_NAME` exported, and the `compose()` guard
in `web/e2e/support.ts` confirmed the target before every Docker call. `/version`
reported `0.9.0` both direct and through the web proxy. The API container is `aarch64`,
runs as user `oak`, and uses glibc 2.41 (`deb13u4`).

- **First run: 23 passed, 1 skipped** (the gated screenshot capture) in 43.5 seconds, with
  zero axe violations on every screen the suite checks.
- **Second run, against the same database: 23 passed, 1 skipped** in 42.0 seconds. At
  `0.8.0` a second run collided with the first run's case and failed on a two-minute
  timeout. That fix holds.
- **The manual's screenshots were re-captured** with `OAK_MANUAL_SCREENS=1`, because the
  masthead in every one shows the version the stack reports. The first capture came after
  two suite runs, and the case list pushed the brief form out of frame. After step 6, the
  stack was therefore recreated empty, the suite run once, and the screenshots captured
  again. That
  run also passed: 23 passed, 1 skipped. The PDF was rebuilt from the result.

### 3. Release build, offline

`UV_OFFLINE=1 make release` at `d5717de`:

- Built twice into separate directories; digests compared and identical
  (`reproducible_rebuild_verified: true`).
- Installed the built wheel into a throwaway environment holding only the locked runtime
  closure (`clean_environment_install_verified: true`).
- Ran the installed console script from outside the checkout. The canonical schemas,
  community catalogue and policy packs resolved from inside the installed package.
- Emitted the release SBOM, the licence inventory and `SHA256SUMS`.

```
68eaac2c6932ec5c2fd67acfcf5d4f5e2f800dc63123a47ab4da1c09841c67bd  THIRD-PARTY-LICENCES.md
dc0c649a8f5838358b3f840f894c218e2a2628e91202e072c6b10d08e48ce9dc  oak-community-0.9.0.cdx.json
ba26e6385dca6f74d6fcf46478fb02b0ef17ae2867b808ec6321c912c08a11e9  oak_community-0.9.0-py3-none-any.whl
7aa7b51c69c52dc80697b426cdb44abce2d18628f8551e4147016b65f2da6e1a  oak_community-0.9.0.tar.gz
```

These are the digests the decision record cites. The licence inventory's digest differs
from `0.8.0`'s although no dependency changed, because its title names the version.

### 4. Verification, including the refusal paths

`make verify-release`: all four artifacts `OK`, and `build-provenance.json` correctly
reported as present-but-unlisted.

Both documented refusal codes were exercised on copies of the release directory:

| Case | Result |
|---|---|
| One appended byte on the wheel | `FAILED … expected sha256:ba26e638…, got sha256:0e3ae1d5…`, `1 artifact(s) do not match SHA256SUMS. Do not install them.`, **exit 2** |
| The sdist deleted | `MISSING oak_community-0.9.0.tar.gz`, **exit 3** |

### 5. Linux x86_64, inside the released image

The API image the scan built for `linux/amd64` at 12:40 UTC, then the documented CLI
journey inside it, ending with the new `oak architecture`:

```
arch: x86_64
libc: ldd (Debian GLIBC 2.41-12+deb13u4) 2.41
user: oak uid=10001
0.9.0
candidates: 4
candidate-03 (balanced_enterprise) in design-case.public-manual-qa — selected by local-user

Nodes:
  node.retrieval           Deterministic cited passage retrieval -> component.fixture-lexical-search@1.0.0
  node.generation          Bounded cited-answer drafting -> component.fixture-local-model@1.0.0
architecture yaml: 298 lines
journey-ok
```

It found four candidates, matching `0.8.0`, on the same Debian base (`deb13u4`). The
brief was mounted in, as before, because the runtime image carries no `examples/`. The
install half of Sprint 11 is **not** exercised here: it needs a Docker daemon, and giving
one to a container is not something the image is for. That half ran against the host's
daemon in step 1.

### 6. Compose control plane, backup and restore

The procedure in [operations.md](../../operations.md), run as written apart from the
project name (see the deviations below). It ran against the stack as step 2's two suite
runs and first screenshot capture had left it (9 cases). The recreation and final capture
that step 2 describes came after this step.

- **Before the backup:** 9 design cases, 213 `artifact_versions` rows and 176 distinct
  digests.
- **The backup:** `pg_dump -Fc` (195 KiB) and a `tar` of the artifact volume (109 KiB,
  176 objects), taken with `api` and `worker` stopped. The two files were written into the
  worktree root, as the runbook says, and **`git status` did not list either**. The
  ignore rules added after the `0.8.0` rehearsal hold.
- **All three volumes destroyed**, including `oak-model-state`, which the runbook says is
  re-entered and not restored.
- **The restore:** database and artifact store restored into clean volumes, and
  `migrate` re-run as a no-op. `/version` reported `0.9.0` afterwards.
- **After the restore:** 9 cases, 213 rows and 176 digests, identical to before. Model
  state held only a regenerated `credentials/api-token`, by design (`RR-040`).
- **`scripts/verify_deployment.py`** against the restored root: **exit 0**, with
  `verified 213 indexed artifact(s) … every object present, correctly sized, and
  digest-matching`. Against a wrong, empty root: **exit 2**, with `213 of 213 … could not
  be verified`.

**Unlike the `0.8.0` rehearsal, this one saw that tool return 0**, as the `0.7.0` one
did, and the reason is worth stating. The `0.8.0` rehearsal ran against a database the PostgreSQL-gated suites had
written into, so it could only ever report orphans. This stack's database never met those
suites. That is the distinction `operations.md` asks an operator to draw, and it bears
the explanation out.

## Defects the rehearsal found

None in the product. Two things are worth recording:

| Found | Consequence | Resolution |
|---|---|---|
| **Docker Desktop updates itself without being asked, and an update restarts the daemon.** It went from 29.3.1 to 29.8.1 at 12:45:54 UTC, while this rehearsal was running | Every container without a restart policy stopped, including the throwaway test database. The first gate run, started after the update, then failed ten PostgreSQL tests and errored ten, fifteen of them with `connection refused`. Those failures described the machine, but the output did not say so | The database was restarted and the gate re-run from the start. Anyone running the PostgreSQL-gated suites on Docker Desktop should know an update can end them part-way |
| **The screenshot capture frames whatever the stack already holds.** After two suite runs, the case list was tall enough to push the brief form out of the first screenshot, which the manual's caption describes | A caption that no longer matched its figure | The capture was repeated on an empty stack after one suite run. `docs/manual/README.md` does not say how full the stack should be; nothing is changed for that here |

## Known deviations from a true clean room

Stated rather than glossed.

- **Not a fresh machine.** The rehearsal ran on the development host with warm `uv`,
  pnpm and Docker layer caches. Offline mode proves the *lockfiles* are sufficient; it does
  not prove a first acquisition on an empty machine.
- **A separate worktree, not a separate clone.** The worktree shares the repository's
  object store, but it has its own virtual environment, `node_modules` and build output.
- **The Compose project was renamed and its ports moved.** Step 6 ran under the project
  name `oak-rel090`, with the API on `18080`, the web on `15174` and PostgreSQL published
  on `15434`, so the default `oak-community` stack and its volumes could not be touched.
  The runbook's commands were run as written, except that `oak-community_` in the three
  volume names became `oak-rel090_`.
- **Docker changed version mid-rehearsal.** The image scan ran on Docker 29.3.1, and
  everything from step 1 onwards on 29.8.1.
- **One architecture for the control plane.** The Compose stack ran as linux/arm64. The
  linux/amd64 evidence covers the CLI path only, which is why the x86_64 control-plane row
  in [platforms.md](../../platforms.md) still says Expected rather than Verified.
- **Images are not byte-reproducible** (`RR-006`), so no image digest here is something to
  reproduce. It is a record of what one build produced.
