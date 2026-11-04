<!-- SPDX-License-Identifier: Apache-2.0 -->

# Supported platforms

This is the authoritative statement of where OAK Community `0.9.0` is supported, what
"supported" means for each row, and what is deliberately out of scope. Prerequisites that
used to be scattered across [README.md](../README.md), [development.md](development.md) and
[dependencies.md](dependencies.md) are consolidated here.

Nothing in this document is a production-readiness claim. OAK Community is a local-first
developer release; see [README.md](../README.md) and
[security/residual-risk.md](security/residual-risk.md).

## Install paths

OAK has four install paths with genuinely different requirements. Choose the row you need
before reading the platform table.

| Path | What it gives you | Needs |
|---|---|---|
| **CLI only** | The whole `init → design → questions → confirm → candidates → evaluate → select → assure → plan → export` journey, plus `architecture`, `report`, `research`, `models`, `render`, `policy`, `extensions` and `validate`, against a file workspace | Python 3.13 and `uv`. No database, no Docker, and no network after install — unless you configure a model provider with `oak models` or consent to a research run (`oak research --consent`, anonymous requests to three public hosts); both are optional and off by default |
| **Control plane** | `oak-api`, `oak-worker`, `oak-db-migrate`, `oak mcp serve`, the REST surface and the web workspace | The CLI row, plus PostgreSQL 17. There is no SQLite fallback. `oak-worker`, `oak-db-migrate` and `oak-mcp` refuse to start without `OAK_DATABASE_URL`; `oak-api` starts, warns, reports `/readyz` as not ready and refuses every request that needs the database with `503 OAK-DATABASE-UNCONFIGURED` |
| **Signed runner** | `oak dispatch`, `oak-runner`, `oak ingest` and `oak observe` against the shipped fixture profiles, including installing one container per node of the selected candidate, starting and smoke-testing them where the profile allows it, and removing them | The CLI row, plus a Docker daemon reachable on its default socket that can pull the pinned placeholder image anonymously from Docker Hub on the first install |
| **Native install** | The same commands against a profile that acknowledges `native-non-production-user-consented` (ADR-0019): each component installed outside Docker, as you, checked once and stopped; `oak approve native_consent` first | The CLI row on macOS on Apple silicon or Linux on x86_64 or aarch64, and no Docker. OAK's stand-in profile downloads nothing; a profile with a real harness needs HTTPS access to the hosts it names |

The Compose profile is the packaged form of the control-plane row: it supplies PostgreSQL,
the API, the worker and the web bundle, and it pins Python, `uv`, Node.js and `pnpm` inside
the build images so the host needs none of them.

## Platform matrix

"Verified" means the path was actually exercised on that platform during a release
rehearsal. The current evidence is the `0.9.0` rehearsal
([release/0.9.0/clean-room.md](release/0.9.0/clean-room.md)), which re-ran both verified
paths: the CLI journey inside a linux/amd64 image, and the Compose control plane on macOS
arm64 through a full backup-and-restore. The `0.8.0` and `0.7.0` rehearsals
([release/0.8.0/clean-room.md](release/0.8.0/clean-room.md),
[release/0.7.0/clean-room.md](release/0.7.0/clean-room.md)) are kept as earlier records.
"Verified in CI" means a CI job runs that path's tests on that platform on every push; the
notes name the job, and its skips are counted by reason against
[`tests/expected-skips.json`](../tests/expected-skips.json), so a skip that widens fails the
job rather than passing quietly. "Expected" means every dependency publishes a wheel or image
for the platform but nobody ran it end to end; treat it as unsupported until someone does and
records it. A row is downgraded
to "Expected" rather than argued up — the Linux x86_64 control-plane row is Expected because
CI starts the Compose stack only as the browser suite's throwaway fixture, never as an
installation an operator runs, and runs the PostgreSQL-gated suites against a database
service, in process.

| OS | Architecture | CLI only | Control plane | Signed runner | Notes |
|---|---|---|---|---|---|
| macOS 11+ | arm64 (Apple silicon) | Verified in CI | Verified | Verified | The development and rehearsal platform. CI's `check-macos-arm64` job runs `make check` on `macos-15` in a virtual environment it asserts is `macosx-11.0-arm64`. GitHub's macOS runners have no Docker and no service containers, so that job skips the PostgreSQL-gated suites and the real-daemon runner journeys (30 and 2 tests, counted): the control-plane and signed-runner paths are verified by the release rehearsal, not CI |
| macOS | x86_64 (Intel) | **Not supported** | **Not supported** | **Not supported** | `cryptography` ≥ 49 publishes no macOS x86_64 wheel and there is no vendored Rust toolchain, so dependency installation fails outright. This includes a Rosetta interpreter on Apple silicon |
| Linux (glibc) | x86_64 | Verified in CI | Expected | Verified in CI | **glibc ≥ 2.27**, set by `Pillow` (`manylinux_2_27_x86_64`), which ReportLab requires for the architecture report (Sprint 13); before that the floor was 2.24, set by `greenlet`, and `cryptography` and `psycopg-binary` would allow 2.17. CI's `check` job runs `make check` on `ubuntu-latest`, in a virtual environment it asserts is `linux-x86_64`, the real-daemon runner journeys included (the signed read-only dispatch, signed apply and rollback of the fixture container, and the install-test-observe-remove demonstration, through the installed `oak` and `oak-runner`), and the rehearsal ran the reference CLI journey inside the `linux/amd64` image (Debian 13, glibc 2.41). The control-plane row is *not* verified here: CI runs the PostgreSQL-gated suites against a database service, and its `web-e2e` job drives the browser against a Compose stack built from the commit, but that stack is a test fixture, not an installation an operator runs |
| Linux (glibc) | aarch64 | Verified in CI | Verified | Verified in CI | **glibc ≥ 2.27**, set by `psycopg-binary` and `Pillow` (both `manylinux_2_27_aarch64`); `greenlet` allows 2.24. The Compose stack — API, worker, migrations, web — runs as Linux aarch64 containers on the rehearsal machine and was exercised end to end, including a backup and restore of both state stores. The control-plane row therefore has a higher glibc floor than x86_64. CI's `check-linux-arm64` job runs `make check` on `ubuntu-24.04-arm` in a `linux-aarch64` virtual environment, the PostgreSQL-gated suites and the real-daemon runner journeys included, and builds both images natively for arm64; the control-plane row stays verified by rehearsal, because CI starts no Compose installation there |
| Linux (musl, e.g. Alpine) | x86_64, aarch64 | Expected | Expected | Expected | musl 1.2 wheels exist for every native dependency, `Pillow` included |
| Linux (glibc) | armv7l (32-bit ARM) | **Not supported** | **Not supported** | **Not supported** | `cryptography` publishes a `manylinux_2_31_armv7l` wheel but `psycopg-binary` publishes no armv7l wheel **and no sdist**, so there is no server path at any build cost. Since Sprint 13 `Pillow`, which ReportLab requires, publishes no armv7l wheel either. It does ship an sdist, so the CLI and the runner may build with a C toolchain and the image libraries, but that is unsupported |
| Windows | any | **Not supported** | **Not supported** | **Not supported** | `src/oak/adapters/persistence/file_workspace.py` imports `fcntl` at module scope for workspace locking. The import fails on Windows before anything else runs. WSL2 is Linux and follows the Linux rows |

The glibc floors above are not guesses: they are read from the wheel tags in `uv.lock`,
which is the file that actually decides what installs. They are **wheel-availability**
floors — the point below which a supported install stops being a download.

Three of the native dependencies behave very differently below their floor:

- `greenlet` 3.5.5 ships an sdist, so an older glibc can still work if you have a C
  toolchain. Slow, unsupported, but possible.
- `psycopg-binary` 3.3.4 ships **no source distribution at all**. Below its floor, or on
  an architecture it does not publish for, there is no server path at any build cost.
  That is why 32-bit ARM has no control-plane row rather than a slow one.
- `Pillow` 13.0.0 ships an sdist, so below its floor, or on 32-bit ARM, it builds with a C
  toolchain and the development headers for zlib and libjpeg. That is unsupported. OAK never
  hands it an image; it is installed only because ReportLab requires it.

## Prerequisites

### CLI only

- **Python 3.13.12**, the version pinned in `.python-version`. `uv` can provision it when the
  network is reachable.
- **`uv` 0.10.x**; CI and the API container use exact builder version 0.10.8.
- **`git`.** Not obvious and not previously documented: `make check` runs
  `tools/check_repository.py`, which shells out to `git check-ignore`, so the gate needs a real
  working tree. Using the released sdist outside a checkout is fine for *running* OAK; it is
  not enough for running the repository gates.
- **`ssh-keygen`** (OpenSSH 8.2 or later) for the gate too: the release-verification tests
  sign with throwaway keys. macOS and most Linux systems include it; a slim container may
  need `openssh-client`.

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
- **A Docker daemon on its default socket.** As a hardening measure, the runner's subprocess
  executor gives its Docker child only `PATH` and an empty Docker configuration directory
  that the runner owns under its home. `HOME`, `DOCKER_HOST`, `XDG_RUNTIME_DIR` and `TMPDIR`
  are never passed, and your `~/.docker/config.json` (registry credentials, credential
  helpers and CLI contexts) is never read. A daemon that is only reachable through those
  variables or a CLI context — rootless Docker, Colima, and Podman socket shims are the
  common cases — is therefore **not** reachable. This is a known limitation, not an
  oversight; it is recorded as `RR-013` in
  [security/residual-risk.md](security/residual-risk.md).
- **Anonymous access to Docker Hub for the first install.** The shipped mutation profiles
  pin `docker.io/rancher/mirrored-pause` by digest, and Docker pulls it, without your
  registry credentials, the first time `apply` creates a container, unless the daemon
  already has it.

### Native install

- Everything from the CLI row, on macOS on Apple silicon or Linux on x86_64 or aarch64. The
  runner refuses any other platform (`OAK-NATIVE-PLATFORM`).
- **No Docker.** Each component runs as you, outside any container, only while the runner
  checks it; the consent text that `oak approve native_consent` shows lists what that
  relaxes.
- **The runner home holds the installations**, one directory each under `native/`, readable
  by you only. Removing one with `oak approve destroy` and `oak dispatch destroy` removes
  that directory and nothing else.
- **Network access only to the profile's download hosts**, for a profile that downloads a
  real harness or model; `examples/targets/local-native-stand-in.yaml` downloads nothing.
  The runner takes no proxy from your environment, so a network that needs a proxy cannot
  download today.

### Browser end-to-end (`make web-e2e`)

- Playwright's Chromium build. On a clean Linux host, `playwright install chromium` is not
  sufficient on its own — the browser also needs its system libraries:

```bash
pnpm --dir web exec playwright install --with-deps chromium
```

`make web-e2e` is not part of `make check`. CI's `web-e2e` job runs it on `ubuntu-latest`
(x86_64) on every push, and the release workflow's on every release run, through the script behind
`make web-e2e-isolated` ([development.md](development.md#browser-end-to-end)).

## Kubernetes

**OAK Community `0.9.0` ships no Kubernetes profile, and this is a decision rather than an
omission.** `OAK-S8-001` asks for "a documented lightweight Kubernetes profile where
feasible"; it is not feasible for this release, for four specific reasons:

1. **There are no images to pull.** Every Compose service builds from a local context. A
   cluster cannot build from a local context, so a Kubernetes profile presupposes published
   images — which no Community release publishes, `0.9.0` included (see
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

### Hardware scan (`oak scan` and the runner's `inventory`)

| Path | How it is proven |
|---|---|
| macOS (`sysctl`, `system_profiler`) | Verified in CI: `check-macos-arm64` runs the real scan (`tests/integration/test_hardware_scan_host.py`) |
| Linux without a GPU (`lscpu`) | Verified in CI on `check` (x86_64) and `check-linux-arm64` |
| NVIDIA GPUs (`nvidia-smi`) | Verified by fixture only (`tests/fixtures/hardware/`): no CI runner has one |
| AMD GPUs (`rocm-smi`) | Verified by fixture only, likewise |

A GPU is seen only through its vendor's tool, so on Linux without `nvidia-smi` and
`rocm-smi` the GPUs are reported as unknown, and an Intel GPU on Linux is never seen.

### Native installation (ADR-0019)

| Path | How it is proven |
|---|---|
| macOS on Apple silicon, OAK's stand-in | Verified in CI: `check-macos-arm64` runs the native journey through the installed `oak` and `oak-runner` (`tests/e2e/test_runner_journey.py`), the integration journey with its canary uninstall (`tests/integration/test_native_install.py`) and the adapter's refusals |
| Linux x86_64, OAK's stand-in | Verified in CI on `check`, the same tests |
| Linux aarch64, OAK's stand-in | Verified in CI on `check-linux-arm64`, the same tests |
| llama.cpp's `llama-server` with a model (`llama_cpp_server`), macOS on Apple silicon | Verified by hand on 2026-11-03, and again with the installation's key on 2026-11-04: `examples/targets/local-native-llama-cpp.yaml` through the installed `oak` and `oak-runner` on an M1 Max with 64 GiB under macOS 26.3.1, the owner having approved each download both times. Build `b11721` with Qwen2.5-0.5B-Instruct Q4_K_M only |
| `llama_cpp_server` on Linux | Not verified: the Linux archives the example's notes name have never been installed |

The stand-in is OAK's own small server, copied from inside OAK and verified by digest like a
download, so CI proves every step of the native path — the consent, the checks, the start,
the probe, the stop and the uninstall — without a network or a downloaded binary. Whether a
downloaded harness runs at all on macOS is decided by Gatekeeper and its code signing, which
only a rehearsal can show.

What the rehearsal showed, for that build and model on that machine:

- **The downloads** matched the profile: the archive at 12,292,671 bytes and
  `sha256:2ace55512ee1ab4e2703f80c135c2a92d40d3367a5b3a98d21b103ffa7f0eb82`, the model at
  491,400,032 bytes and
  `sha256:74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`, measured again
  with `shasum` after the runner had checked them.
- **macOS ran the binary.** The build is ad-hoc signed and not notarised, and `spctl --assess`
  rejects it, but a file the runner downloads carries no quarantine attribute, so Gatekeeper
  is not asked. An archive unpacked from a browser's download would be a different case.
- **The check.** `/health` answered 200 after 19.8 seconds on the first start and the process
  exited 0 when stopped, with nothing left on its port. The install took 224 seconds in all,
  nearly all of it the download.
- **`START.txt` works as written.** Started by hand, the server was ready in under a second,
  listened on 127.0.0.1 only, answered a chat request correctly and exited 0 on Ctrl-C.
- **The uninstall** took about a second: it removed the installation's folder, and a file
  placed beside that folder stayed. `oak observe` then reads `removed`.
- **Its log warned** that it had no API key and that CORS allowed all origins. The next
  rehearsal measured that, and what the installation's key does about it.

What the second rehearsal showed, on 2026-11-04, with the same build, model and machine:

- **The install's check proved the key.** `/health` answered 200, a request without the key
  answered 401, and the server's log held neither the warning nor the key. A second `apply`
  took 8 seconds, downloaded nothing and kept the key. The uninstall took a second and removed
  the key with the folder. Across everything both applies wrote, every journal, message, record
  and log, the key was only in `api-key.txt`.
- **Without the key,** `/health`, `/v1/health` and the server's own web page answered, and
  `/v1/models`, `/models`, `/props`, `/slots`, `/metrics` and `/v1/chat/completions` answered
  401, as did a wrong key. That web page loads, says "Access denied" and offers Enter API Key.
- **With the key,** `START.txt`'s commands worked as written, and a question sent with
  `Authorization: Bearer <key>` or with `X-Api-Key: <key>` was answered.
- **From a web page in a browser** (the desktop app's own pane, Chromium 152), served from
  another origin on the same computer. Against a control started with no key, the page read
  `/v1/models` and got an answer from the model: the gap was real. A `text/plain` request whose
  answer the page could not read ran the model too, so restricting CORS alone would not have
  stopped it. Against the server with the key, the same page got `/health`, 401 for the rest,
  and no generation started.
- **A public page was stopped by the browser.** From `https://example.com`, that browser blocked
  every request before it left (`ERR_BLOCKED_BY_CLIENT`, local network access `denied`), so
  neither server saw one. That is one browser in one configuration, not a guarantee: another
  may ask, or allow it.
- **`ps`** showed the key file's path and never the key while the server ran. A client that puts
  the key on its own command line does show it while it runs, which `curl -H` with `$(cat ...)`
  did, so `START.txt`'s example hands it to `curl` on its input instead, and that showed nothing.

## What is not tested where

`make toolchain-check` fails if the running Python or the pnpm-provisioned Node differs
from the pins, not only if two declarations disagree, and `package.json`'s
`devEngines.runtime` makes pnpm download and run the pinned Node itself, so the host's
Node never reaches a build. That closes the defect `RR-034` recorded: the `0.7.0`
rehearsal built on Node 22.17.1 against a 24.18.0 pin with every declaration-only gate
green.

CI (`.github/workflows/ci.yml`) runs `make check` on three platforms: `ubuntu-latest` x86_64
(`check`), `macos-15` on Apple silicon (`check-macos-arm64`) and `ubuntu-24.04-arm`
(`check-linux-arm64`), which also builds both container images natively for arm64; the
`web-e2e` job builds them for x86_64 and drives the browser suite. Each `check` job fails
unless its skips, by reason and count, are the ones `tests/expected-skips.json` lists for it.
The macOS job cannot run the PostgreSQL suites or the Docker journeys, because GitHub's macOS
runners have neither Docker nor service containers, so the macOS control-plane and
signed-runner rows stay verified by the release rehearsal; the native install path needs
neither, so all three jobs run it with OAK's stand-in
([release/0.9.0/](release/0.9.0/clean-room.md)). `RR-014` records what closed.
