<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release-candidate rehearsal — OAK Community 0.8.0

Run on 2026-09-23, at the owner's request, because the `0.8.0` decision record was signed
with this row reading **inherited from `0.7.0`** rather than re-run. It is no longer
inherited. What follows is what was actually run, on what, and what it produced. Where a
step found a defect, the defect is recorded here rather than quietly fixed and forgotten.

The `0.7.0` rehearsal is at [../0.7.0/clean-room.md](../0.7.0/clean-room.md); this one
repeats its six steps so the two are comparable.

## Machine

| | |
|---|---|
| Host | macOS 26.3.1, arm64 (Apple silicon), 10 CPUs, 64 GiB RAM |
| Python | CPython 3.13.12 (`macosx-11.0-arm64`) |
| Node / pnpm | 22.17.1 / 11.15.1 — **the same drift `0.7.0` recorded; see below** |
| Docker | 29.3.1, arm64 daemon, buildx 0.32.1 |
| PostgreSQL | `postgres:17.6-alpine`, digest-pinned by `compose.yaml` |
| Tree | `98ce70f`, clean (`source_tree_dirty: false`) |

## Network posture

Dependencies were resolved from the lockfile with the network refused, and the gate and the
release build were both run that way:

- `UV_OFFLINE=1 uv sync --frozen --offline` — and note what it did: it **removed the
  optional `keychain` extra**, because a plain sync installs the base closure only. Every
  step below therefore ran with `keyring` absent, which is what a first-time installer has.
- `UV_OFFLINE=1 make check` and `UV_OFFLINE=1 make release` both completed.

Three things genuinely need the network and are recorded as such rather than claimed
offline: `make audit` (advisory databases), the first acquisition of dependencies and base
images, and — new since `0.7.0` — **the web image build**, whose
`pnpm install --frozen-lockfile` runs inside the container and reaches the registry even
when the host's pnpm store is warm. During this rehearsal the npm registry was degraded
(socket errors, sub-50 KiB/s tarballs, retries on `playwright`, `esbuild` and `react-dom`);
pnpm recovered on its own, but an image rebuild is not an offline operation.

## Steps and results

### 1. Full gate, offline

`make check` with `OAK_TEST_DATABASE_URL` against the pinned PostgreSQL 17.6. Green,
verified by **counting `make: ***` lines: 0** — not by the exit code, which the wrapper
reports as success even when the gate failed.

- 665 unit and contract tests
- 276 integration tests, 4 skipped, **including** the PostgreSQL-gated suites that CI
  silently skips (`RR-019`)
- 42 end-to-end tests
- validate, format, lint, boundaries, hygiene, toolchain, strict mypy over **138** source
  files, generated-OpenAPI compatibility, web build

**The counts are identical with `keyring` absent.** No gate test requires the optional
keychain backend to be installed; the real backend is exercised by hand, not by the gate.

### 2. Browser journey and accessibility

`make web-e2e` against the rebuilt Compose stack. **This step failed, and the failure was
real** — see "Defects the rehearsal found". After the fix: **10 passed, 1 skipped** (the
gated screenshot capture) in 42 seconds, re-run against the same live database that had
just made it fail. Zero axe violations.

### 3. Release build, offline

`UV_OFFLINE=1 make release`:

- Built twice into separate directories; digests compared and identical
  (`reproducible_rebuild_verified: true`). The build refuses to finish otherwise.
- Installed the built wheel into a throwaway environment holding only the locked runtime
  closure (`clean_environment_install_verified: true`).
- Ran the installed console script from outside the checkout and confirmed the canonical
  schemas, community catalogue and policy packs resolve from inside the installed package.
- Emitted the release SBOM, the licence inventory and `SHA256SUMS`.

```
37951c871733de598cb251265852d55e3ef5bc7aa8ce744f783014fb833907a7  THIRD-PARTY-LICENCES.md
e3b628e5da1c830a74926c1439cb1998d6a2e270b4ca82676d7c694bc68aec9b  oak-community-0.8.0.cdx.json
40d108c6354bd679b2617acac171b8d1d62fb2514a06de3dafe84436680b00d3  oak_community-0.8.0-py3-none-any.whl
7a869dd3d32e6442b76114d26d4fed1480201b109620526a811fa2e3769a1057  oak_community-0.8.0.tar.gz
```

**The wheel is byte-identical to the build the decision record cites, taken at a different
commit; the sdist and the SBOM are not.** That is not a reproducibility failure and the
distinction is worth stating: the sdist carries 75 documentation files and 103 tests, so
every documentation commit moves its digest, while the wheel carries neither. "Reproducible"
means a given tree builds to the same bytes twice, not that the sdist is stable across
commits.

### 4. Verification, including the refusal paths

`make verify-release` → all four artifacts `OK`, and `build-provenance.json` correctly
reported as present-but-unlisted.

Both documented refusal codes were exercised rather than assumed:

| Case | Result |
|---|---|
| One appended byte on the wheel | `FAILED … expected sha256:40d108c6…, got sha256:a0bb0b6f…`, `1 artifact(s) do not match SHA256SUMS. Do not install them.`, **exit 2** |
| A listed artifact deleted | **exit 3** |

### 5. Linux x86_64, inside the released image

`docker buildx build --platform linux/amd64`, then the documented journey inside it:

```
arch: x86_64
libc: ldd (Debian GLIBC 2.41-12+deb13u4) 2.41
user: oak uid=10001
0.8.0
candidates: 4
journey-ok
```

Four candidates, matching `0.7.0`. The base has moved from `deb13u2` to `deb13u4`, which is
the `apt-get upgrade` layer doing its job. This is the evidence behind the Linux x86_64
"CLI only — Verified" row in [platforms.md](../../platforms.md).

The journey needs the brief **mounted in**: the runtime image carries the packaged canonical
schemas, community catalogue and policy packs, but no `examples/`. A reader who tries
`/app/examples/...` inside the image finds nothing there.

### 6. Compose control plane, backup and restore

The stack rebuilt from source with `--build`, then the procedure in
[operations.md](../../operations.md) run **verbatim**.

- `/version` direct and web-proxied: `0.8.0` before and after. API container `aarch64`,
  user `oak`, glibc 2.41.
- 44 design cases and 8,389 `artifact_versions` rows before the backup.
- `pg_dump -Fc` (5.5 MB) and a `tar` of the artifact volume (626 KB, 981 objects), taken
  with `api` and `worker` stopped.
- **All three volumes destroyed**, including `oak-model-state`, which the runbook says is
  re-entered rather than restored.
- Database and artifact store restored into clean volumes; `migrate` re-run as a no-op.
- 44 cases readable afterwards at the same versions and statuses; 8,389 rows restored.
- **Model state is empty after the restore, by design.** The pinned Local AI model set
  before the backup is gone and the volume holds only a regenerated `credentials/api-token`.
  This is new since `0.7.0` and is the behaviour `RR-040` asks for.

`scripts/verify_deployment.py` against a **wrong** artifact root: exit 2,
`8389 of 8389 indexed artifact(s) … could not be verified`. Against the **real** restored
root it also exits 2, reporting 5,766 unverifiable — which is a false alarm about this
deployment and a true statement about its database. See the defects below.

## Defects the rehearsal found

Recorded because the point of a rehearsal is what it catches.

| Found | Consequence | Resolution |
|---|---|---|
| `make web-e2e` is **not re-runnable** against a Compose stack whose database already holds its cases. `web/e2e/models.spec.ts` filled a constant brief file name, `brief.md`, and the case id derives from it, so the second run collided with the first run's `design-case.brief` | The create was refused with `409 OAK-EXPECTED-VERSION`, the page stayed on the case list, and the next step timed out after **two minutes** on a missing button. The real cause appeared nowhere in the failure output | The test now timestamps its slug, as every other spec in that directory already did. Re-run against the same live database: 5.9 seconds, green. **The workspace itself was right**: it surfaced `OAK-EXPECTED-VERSION` with a correlation id in an alert |
| `scripts/verify_deployment.py` cannot return 0 on a development deployment whose database has been shared with the PostgreSQL-gated test suites | Those suites write `artifact_versions` rows into the shared database while storing the bytes in per-test temporary directories that then vanish. 137 of 1,118 referenced digests were already missing **before** the backup, accounting for 5,766 rows — `workspace.public-manual-qa` alone holds 5,890, and 186 of 232 workspaces are test-made. An operator following the runbook after a perfectly good restore reads "the metadata and the artifact bytes are not from the same backup, or one of them is damaged" and has no way to tell test detritus from real damage | The runbook now says so, and says how to tell the difference. The tool is not changed: failing closed on an index it cannot satisfy is the correct behaviour |
| The runtime image ships no `examples/` | A journey run inside the image cannot use the documented brief path; the brief must be mounted in | Recorded here and in step 5. Not changed: shipping examples in a runtime image is not obviously right |
| The backup procedure writes `oak-metadata.dump` and `oak-artifacts.tar.gz` **into the repository root**, and neither was ignored | Step 6 followed the runbook verbatim, and the next `git add -A` staged a 5.5 MB dump of a live control-plane database. It was caught and removed before it left this machine, but an operator following the same instructions in a checkout would commit their own deployment's data, and a contributor would then have it | Both filenames are now in `.gitignore`, with the reason written next to them |

## Known deviations from a true clean room

Stated rather than glossed.

- **Not a fresh machine.** The rehearsal ran on the development host with warm `uv` and
  Docker layer caches. Offline mode proves the *lockfiles* are sufficient; it does not prove
  a first-ever acquisition on an empty machine.
- **Node.js drift, unchanged since `0.7.0`.** The host runs **22.17.1** while
  `.node-version`, `package.json` and `pnpm-workspace.yaml` all pin **24.18.0**. Every web
  gate passed anyway, and the toolchain contract still compares declarations against each
  other rather than against the running binary. The web artifacts in this rehearsal were
  built on an unpinned interpreter; CI builds on the pinned one.
- **The web image build is not offline.** See "Network posture".
- **One architecture for the control plane.** The Compose stack ran as linux/arm64. The
  linux/amd64 evidence covers the CLI path only, which is why the x86_64 control-plane row
  in [platforms.md](../../platforms.md) says Expected rather than Verified.
- **Images are not byte-reproducible** (`RR-006`), so no image digest here is something to
  reproduce. It is a record of what one build produced.
