<!-- SPDX-License-Identifier: Apache-2.0 -->

# Development guide

Local source development uses Python 3.13.12, Node.js 24.18.0, `uv` 0.10.x, and `pnpm` 11.15.1. Dependencies are locked in `uv.lock` and `pnpm-lock.yaml`; those lockfiles do not pin the `uv` executable itself. Contributors use `.python-version` and `.node-version`, while `package.json` pins `pnpm` and its `devEngines.runtime` entry makes pnpm download and run the pinned Node itself, so the host's own Node version never reaches a build. `make toolchain-check` fails if the running Python or the pnpm-provisioned Node differs from the pins, not only if two declarations disagree.

macOS contributors need an arm64 Python 3.13.12 interpreter. From `cryptography` 49.0.0 the project no longer publishes macOS x86_64 wheels, so an Intel or Rosetta interpreter falls through to the source distribution and cannot build it without a Rust toolchain.

CI and container builds are the reproducible builder boundary. They pin `uv` 0.10.8 and the exact Python and Node runtimes; container users need only Docker with Compose on the host. The source-development compatibility range exists for contributor convenience and is not a target-hardware contract. OAK compilation receives target capabilities through explicit invocation data, currently a bounded target profile. It never treats the control-plane host as the deployment target. A later target-side inventory adapter must preserve that boundary.

## Commands

| Command | Purpose |
|---|---|
| `make bootstrap` | Install locked Python and web dependencies |
| `make lock` | Re-resolve both lockfiles. Prefer `uv lock --upgrade-package <name>` for a single Python dependency; this target also rewrites `pnpm-lock.yaml` |
| `make toolchain-check` | Check local, CI, container, package, and documentation toolchain declarations for drift |
| `make validate` | Validate canonical schemas, examples, generated files and documentation policy, then run the web workspace's guards (`scripts/check_studio_ui.py`), the architecture report's guards (`scripts/check_report.py`) and the research guards (`scripts/check_research.py`) |
| `make format` | Apply deterministic Python and web formatting |
| `make format-check` | Check formatting without changes |
| `make lint` | Run Python lint, import boundaries, unsafe-execution checks, and repository hygiene checks |
| `make typecheck` | Run strict Python and TypeScript checking |
| `make test` | Run unit and contract tests |
| `make test-integration` | Run local API integration tests |
| `make test-e2e` | Run CLI/API user-visible smoke tests. When a Docker daemon answers, two runner journeys also install and remove the reference case's containers on it; otherwise they skip (see below) |
| `make openapi-compatibility` | Reproduce OpenAPI/client output and reject local breaking changes |
| `make web-build` | Build the production web bundle |
| `make web-e2e` | Run the Playwright browser journey and accessibility suite against the Compose stack |
| `make web-e2e-isolated` | Build the images from this tree as a Compose project of their own, run the browser suite on it, check its skips and remove the project (what CI runs; needs Docker and the Playwright browser) |
| `make build` | Build Python and web artifacts from bootstrapped dependencies without network |
| `make sbom` | Generate a development dependency SBOM under ignored `sbom/`. The *release* SBOM is different and comes from `make release` |
| `make audit` | Audit the Python and web dependency closures for known advisories. Needs network |
| `make scan-images` | Build and scan both container images, failing on any **fixable** CRITICAL or HIGH. Needs Docker and network; see [release-process.md](release-process.md) |
| `make check` | Run the repository gate. It changes nothing in the tree; when a Docker daemon answers, `make test-e2e` also creates and removes containers on it (see below) |
| `make release` | Build the release artifacts, SBOM, licence inventory and checksums; see [release-process.md](release-process.md) |
| `make verify-release` | Verify a signed release in `dist/release` against its `SHA256SUMS` and `SHA256SUMS.sig`; a build you just made is unsigned, so check it with `uv run python scripts/verify_release.py --checksums-only dist/release` |
| `make clean` | Empty the `uv` cache |
| `make clean-all` | Remove every build artifact, virtual environment and cache in the tree. It does **not** touch a `.oak` workspace — that is your data; see [operations.md](operations.md#uninstall) |

The bootstrap step may use the public package registries, and downloads the pinned Node.js runtime for pnpm on first use. After dependencies are installed, `make check` requires no hosted service, credentials, model provider, database, or public network: the runner journeys that drive a real Docker daemon use the pinned stand-in image `docker.io/rancher/mirrored-pause:3.10` only if it is already cached, and are skipped otherwise (`docker pull docker.io/rancher/mirrored-pause@sha256:ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a` once to run them; CI does this as a setup step). It does require `git`: `tools/check_repository.py` shells out to `git check-ignore`; and `ssh-keygen` (OpenSSH 8.2 or later), because the release-verification tests sign with throwaway keys.

**`make check` reports success wrongly when backgrounded.** Verify it by counting `make: ***` lines in its output rather than by its exit code.

**The PostgreSQL-gated integration suites skip silently.** Thirty tests need `OAK_TEST_DATABASE_URL` (29 integration tests and the installed-MCP handshake), and a skip is indistinguishable from a pass in the summary line; CI counts each job's skips against `tests/expected-skips.json` (see `CONTRIBUTING.md`). `compose.yaml` publishes no host port for PostgreSQL, so run them like this:

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

Migrate a fresh database first (`OAK_DATABASE_URL=$OAK_TEST_DATABASE_URL uv run oak-db-migrate`); an unmigrated one fails the gated suites as if the code had regressed. CI sets the variable: the `check` job in `.github/workflows/ci.yml` runs a PostgreSQL service on the image `compose.yaml` pins, migrates it and exports `OAK_TEST_DATABASE_URL`, so a green CI run includes these suites (`RR-019`, closed in [security/residual-risk.md](security/residual-risk.md)). The release workflow's gate does the same, and `make toolchain-check` refuses either workflow without it. A local run without it still skips them, and ends by saying how many it skipped; a sprint's closing `make check` must run them.

**The Docker-gated runner journeys skip silently too.** Two tests in `tests/e2e/test_runner_journey.py` install the reference case on a real Docker daemon:

- one creates and removes never-started containers against `examples/targets/local-mutation-fixture.yaml`;
- the other runs the whole install, smoke test, re-apply, observe and rollback journey against `examples/targets/local-started-fixture.yaml`.

They run only when `docker info` answers and the pinned stand-in image is already cached. A `docker` binary with no reachable daemon (Docker Desktop not running, say), or a daemon without the image, is a skip, and the summary line does not distinguish a skip from a pass. Each journey compiles in its own temporary workspace, and an installation's identity includes the workspace that compiled it, so the journeys never adopt or remove the containers of your own install of the reference case.

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
`init`, `serve`, `mcp serve`, `keys`, `models`, `sign`, `approve`, `revoke-approval`, `dispatch`, `ingest`, `observe`, `gitops`, `policy`, `render`, `extensions`, `validate` and `workspace` (`architecture` is not: it works over REST);
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
oak-runner identity > runner.identity.json          # once per runner, before the first ingest
oak keys enroll-runner --identity runner.identity.json
oak ingest --output json
```

See [the migration guide](../migrations/README.md) before a schema change. Stop writers and
take a database backup before future forward migrations. Supported recovery restores into a
clean database and then runs `oak-db-migrate`; `alembic downgrade` is intentionally not
an OAK recovery mechanism.

## Web workspace conventions

The workspace is drawn from design tokens in `web/src/tokens.css` and a small set of
primitives in `web/src/ui/` (`Keycap`, `Chip`, `Tile`, `Card`, `Led`, `RangeBar`,
`ProvenanceMark`, `CopyPlate`, `Icon`). `scripts/check_studio_ui.py`, which `make validate`
runs, holds the rules review established:

- **G1:** `web/src` renders no raw variant id outside `web/src/ui/variantLabel.ts`, no
  "enterprise" and no Google Fonts URL.
- **G2:** the generated client gains no non-GET call beyond its known mutations
  (`recordReport` from Sprint 13; `researchCatalogue` and `reviewResearchItem` from
  Sprint 14); no
  button is named for approving,
  signing, dispatching, installing or applying unless its name starts with "Copy"; the
  copy control imports no client and makes no request.
- **G3:** every `<svg>` is `aria-hidden` or `role="img"` with a name, and every icon-only
  button has an `aria-label`.
- **G4:** the bundle page keeps saying the web workspace holds no runner execution
  authority.
- **G5:** `styles.css` paints only tokens and sets no opacity between 0 and 1. An
  accessibility scan samples an element mid-fade and fails contrast at random, so motion
  moves position only.

Each guard was mutation-checked with a planted violation. A pinned accessible name or
visible text in `web/e2e` changes only with its spec, in the same commit.

The architecture report has its own guards in `scripts/check_report.py`, which composes
the reference report afresh at `candidate_selected`, `assurance_planned` and
`bundle_compiled` rather than reading the golden:

- **R1:** no assurance vocabulary, edition word or raw variant id in any string.
- **R2:** every number is a quantity with a real unit and a source; no figure from a
  fixture run is "measured" or "counted"; every `unknown` has a reason; template text has
  no bare number.
- **R3:** every picture has a table holding the same facts.
- **R4:** every text pair in the print palette reaches 4.5:1.
- **R5:** the researched acceptance case composes live too: appendix G last, every fixture
  figure a synthetic estimate, an evidence word and a pointer on every claim, and the one
  closed label suffix on a researched option.

`tests/contract/test_report_guards.py` plants a violation for each rule.

Research has its own guards in `scripts/check_research.py`, which normalises the recorded
fixtures live with the fixed clock rather than reading a committed output:

- **S1:** the research adapter's host allowlist is exactly the three hosts ADR-0018 names,
  the live transport is scoped to them, and the adapter builds no other address.
- **S2:** the derived terms hold only values from the closed vocabularies, over every
  committed brief's intent and the synthetic intents.
- **S3:** no researched manifest is `eligible` or `approved_for_context`.
- **S4:** every claim carries an evidence class from the closed enum.
- **S5:** no normalised string holds a control character, a forbidden word or a value
  outside its bounds, and no gap is a placeholder.

## Browser end-to-end

The Playwright suite drives the web workspace at `http://127.0.0.1:5173` and expects the
full Compose stack (`postgres`, `api`, `worker`, `web`) to be healthy. Install the pinned
browser once after bootstrap:

```bash
pnpm --dir web exec playwright install chromium
docker compose up -d postgres api worker web
make web-e2e
```

`e2e/research.spec.ts` needs the stack to answer research from the recorded fixtures, and
fails on a stack that would call the three live hosts. Give `api` and `worker`, in your
override (below), `OAK_RESEARCH_FIXTURES: /fixtures/research` and the read-only volume
`./tests/fixtures/research/e2e:/fixtures/research:ro`: both, because the API computes the
plan the consent card shows and the worker re-checks it before the first request. Never
set it on a stack that holds real cases (`RR-052`).

The suite covers the complete reference journey with automated axe accessibility checks on
every core screen, a denied stale-version transition with its recovery path, and an
interrupted operation that is cancelled cooperatively; that last scenario stops and
restarts the Compose `worker` service, so it requires Docker control and is skipped unless
`OAK_E2E_DOCKER=1` (which `make web-e2e` sets). `e2e/models.spec.ts` covers the Models
screen and the Deterministic / Online AI / Local AI chips end to end;
`e2e/downloads.spec.ts` saves a candidate through the **Take it** sheet and checks that
the file on disk hashes to the digest the server named; `e2e/hardening.spec.ts` checks
the containers run unprivileged with an owner-only model-state volume; and
`e2e/compose-target.spec.ts` covers the Compose target check without Docker.
`e2e/manual-screens.spec.ts` re-captures the user manual's screenshots; it is collected
by every run but skips unless `OAK_MANUAL_SCREENS=1` (see `docs/manual/README.md`).
Browser binaries download from the Playwright CDN, and the model-settings spec makes the
`api` container ask `huggingface.co` once about the synthetic token it stores (one free
request that generates nothing); everything else runs locally.

`make web-e2e-isolated` is the way to run it beside a stack you use, and it is what CI's
`web-e2e` job and the release gate run (`scripts/run_browser_suite.py`). It builds the
images from the working tree as the Compose project `oak-e2e-local` on `127.0.0.1:28080`
(API) and `127.0.0.1:25173` (web), with the research fixture on `api` and `worker` and the
commit baked into the API image, checks that `/version` names that commit, runs the suite,
and removes the project with its volumes and images afterwards (`--keep` leaves it up;
`--project`, `--api-port` and `--web-port` move it). It refuses a project name that does
not start `oak-e2e-` and the ports 5173, 8080 and 15432. It fails unless every test passed
and the tests that skipped are exactly the two manual captures, so a skip that appears, or
a capture that stops skipping, needs a reviewed change to `EXPECTED_SKIPS` in the script.
It uploads nothing: Playwright's report and any trace stay in the ignored
`web/test-results/`, because a failed page can show a brief or a model-key field.

The Compose-backed specs act on whichever stack `docker compose` reaches from the
repository root. They stop and restart its `worker`, clear its Hugging Face and Local AI
model selections, and remove its Hugging Face credential setting, including any stored
token and its verification record. With nothing overridden, that is the default
`oak-community` project serving `http://127.0.0.1:5173` and `http://127.0.0.1:8080`, so
point the suite at a stack whose model settings you can lose. To run it against a
throwaway project beside that one, give the throwaway its own name and ports. The
override needs `!override` (Docker Compose 2.24.4 or later), because otherwise Compose
adds to the port list and still binds 8080 and 5173:

```yaml
# e2e-ports.yaml, kept out of the repository
services:
  api:
    ports: !override
      - "127.0.0.1:28080:8080"
    environment:
      OAK_RESEARCH_FIXTURES: /fixtures/research
    volumes:
      - ./tests/fixtures/research/e2e:/fixtures/research:ro
  worker:
    environment:
      OAK_RESEARCH_FIXTURES: /fixtures/research
    volumes:
      - ./tests/fixtures/research/e2e:/fixtures/research:ro
  web:
    ports: !override
      - "127.0.0.1:25173:8080"
```

Then set `OAK_WEB_BASE_URL` and `OAK_API_BASE_URL` to its origins and
`COMPOSE_PROJECT_NAME` to its project name, and remove it afterwards:

```bash
docker compose -p oak-e2e -f compose.yaml -f /path/to/e2e-ports.yaml up -d --build --wait
OAK_WEB_BASE_URL=http://127.0.0.1:25173 OAK_API_BASE_URL=http://127.0.0.1:28080 \
  COMPOSE_PROJECT_NAME=oak-e2e make web-e2e
docker compose -p oak-e2e -f compose.yaml -f /path/to/e2e-ports.yaml down -v --rmi local
```

Before the first `docker compose` command, `web/e2e/support.ts` checks where Compose will
land. It refuses without calling Docker at all in two cases: either origin is overridden
without an exported `COMPOSE_PROJECT_NAME`, or an origin's host is not `127.x.x.x` or
`[::1]`. Write `127.0.0.1` rather than `localhost`, which can resolve to either family.
Otherwise it asks Compose, with the read-only `docker compose port`, where the project
publishes `api` and `web`. It refuses unless each is on its origin's port and address, or
on that address family's wildcard (`0.0.0.0` or `[::]`). The check trusts the Docker
engine the shell is configured for (`DOCKER_HOST`, the current `docker context`), and it
assumes that engine runs on this machine. `compose()` also refuses a command that starts
with a global flag such as `-p` or `--file`, which would choose the project after the
check. `e2e/compose-target.spec.ts` covers these decisions without Docker. A spec that
needs Docker must call `compose()` from `web/e2e/support.ts` rather than run its own
`execSync`. `tests/contract/test_browser_suite_compose_scope.py` fails if any other script
under `web/e2e` mentions `child_process`.
