<!-- SPDX-License-Identifier: Apache-2.0 -->

# Contributing to OAK Community

## Why contribute

OAK is trying to make one thing normal: decisions about AI systems that are written down,
checkable and repeatable, instead of argued over in chat and then forgotten. If that
matters to you, there is plenty to do. The project is set up so that a newcomer's change
gets a careful, specific review, not a rubber stamp.

It's also a good place to learn. One codebase holds a small compiler with byte-stable
output, a typed state machine with an audit trail, and a security boundary between two
programs that don't trust each other's say-so (the control plane and the runner). It also
has reproducible release builds and an optional AI integration that treats model output
as untrusted. Each part is small, and each has tests that show you what "correct" means.

The gaps are public, too. The [residual-risk register](docs/security/residual-risk.md),
the threat-coverage [named gaps](docs/security/threat-coverage.md#named-gaps) and the map
under [Where you could help](#where-you-could-help) are the project's own list of what
isn't done yet, each with an id you can cite in a pull request.

## Before anything else

Two things about this project will surprise you if nobody says them out loud.

**Compiled artifacts are byte-stable, and that is a contract.** Canonical documents are
digest-addressed. A change that alters the canonical bytes of an unchanged document is a
breaking change even when the JSON "looks the same" — a reformat, a key reordering, a
default that starts being emitted. Byte-stability is verified directly against the previous
mainline before every merge, not inferred from a passing test suite.

**Fail closed, everywhere.** An unknown tool, kind, adapter, schema or version is refused,
never skipped. A check that cannot be performed is a refusal, not a pass. If you find
yourself writing `if not X: return` in a verification path, that is almost certainly the
wrong shape.

Read [architecture.md](docs/architecture.md) and, if you are near anything privileged,
[security/residual-risk.md](docs/security/residual-risk.md) so you do not re-report a
known gap as a discovery.

## Get set up

```bash
make bootstrap
make check
```

You need Python 3.13.12, `uv` 0.10.x, Node.js 24.18.0, `pnpm` 11.15.1 — and `git`, which
is not obvious: `make check` shells out to `git check-ignore`. [platforms.md](docs/platforms.md)
has the full matrix, including the macOS arm64 requirement that will otherwise waste an hour.

**`make check` reports success wrongly when backgrounded.** Verify it by counting `make: ***`
lines in the output, not by the exit code.

## A first change

The highest-value first contribution is usually a test that pins behaviour nobody pinned.
[security/threat-coverage.md](docs/security/threat-coverage.md) has a "Named gaps" table —
each row is a real, scoped, self-contained piece of work with a clear definition of done.

Otherwise: fix something in [security/residual-risk.md](docs/security/residual-risk.md)
that is marked Low, or improve an error message you found confusing. A change that makes a
refusal easier to act on is worth more here than a new capability.

## Where you could help

This map is grouped by what you might enjoy. An item marked **discuss first** changes a
trust boundary or a public contract. Open an issue and agree the shape before writing code,
because it often needs an ADR (see [Governance](#governance)).

**Your first afternoon**

- Run the [guided tour](docs/tour.md) on a fresh machine and report anything that confused
  you or didn't match. A document that is wrong for a newcomer is a bug.
- Make an error message easier to act on. Every `OAK-*` code is listed in
  [error-codes.md](docs/error-codes.md) with the place it is raised.
- Write an example brief for a different kind of system, such as support-ticket triage, a
  study helper, or search over another document set. Then see how far the deterministic
  reader and the bundled synthetic catalogue get with it. Where they fall short is exactly
  what the project needs to learn, and it makes a good issue. Keep examples synthetic
  ([examples/README.md](examples/README.md)).

**Tests that pin behaviour nobody has pinned**

- The [named gaps](docs/security/threat-coverage.md#named-gaps) are scoped pieces of work.
  Several are tests nobody has written yet: nothing tampers with an objective weight
  (`TM-05`), asserts that the runner holds no control-plane credential (`TM-07`), or checks
  that a rendered system contains no runtime reference to OAK (`TM-19`). Others, such as
  `TM-02` and `TM-14`, are missing controls, which belong under "Bigger directions" below.
- The web workspace has no unit tests at all (`RR-021`).

**The web workspace**

- Show the trade-offs between candidates as a chart as well as a table. Keep the table,
  because it's the accessible representation.
- Plain-language copy, and keyboard, focus and contrast passes. The browser end-to-end
  suite (`make web-e2e`) is where a flow gets pinned.

**Deployment backends, serving profiles and packs**

Two renderers ship today (`renderer.local-manifests` and `renderer.helm-kubernetes`). The
backlog includes OpenTofu or Terraform modules, Crossplane compositions and Kratix Promises,
Ansible for appliance and edge targets, OPEA or DIAL application definitions, pipeline
definitions, model-serving profiles such as vLLM and llama.cpp, and policy, domain,
evaluation and evidence packs. All of them go through the governed extension path and its
templates, described in [extension-sdk.md](docs/extension-sdk.md). Each backend stays
replaceable and owned by its own project. OAK compiles *to* them; it doesn't absorb them.

**Where OAK runs**

- Record the first rehearsal of the Linux x86_64 control plane. That row of
  [platforms.md](docs/platforms.md) is still "Expected" because nobody has run it.
- Add CI jobs for macOS and arm64 (`RR-014`), and CI that provisions PostgreSQL so the
  gated suites actually run there (`RR-019`).
- Native Windows support starts with replacing the Unix-only `fcntl` workspace lock.
- Let the runner reach rootless Docker, Colima or Podman (`RR-013`). **Discuss first**,
  because it touches the runner's hardening.

**Operations and supply chain**

- Logging and metrics that leak nothing (`RR-015`). **Discuss first**, because of the data
  boundary.
- A readiness check that notices an un-migrated database (`RR-016`), and a file-workspace
  format migration before the format ever changes (`RR-017`).
- Byte-reproducible container images (`RR-006`), and bounding how workspace reads grow
  with history (`RR-030`).
- Release signing (`RR-005`) needs a named key holder, which is a maintainer decision. The
  tooling around it can still be prepared.

**Bigger directions (discuss first)**

- Let policy decisions gate state transitions, not just record them (`RR-004`).
- A signature and provenance gate for catalogue component manifests (`RR-025`), and real
  manifests backed by evidence.
- Budgets and rate limits, including for model spend (`RR-024`, `RR-041`).
- Comparing predicted cost, latency and quality against observed outcomes, the evidence
  loop OAK is designed to close.
- A fuller developer-portal plugin, building on the starter in
  [examples/backstage/](examples/backstage/README.md).

Some things are out of scope for Community by design: real authentication, multi-tenant
isolation, production targets and a live webhook dispatcher. They are listed under
"Explicitly unavailable in Community" in [interfaces.md](docs/interfaces.md). A proposal
there is a product decision, not a pull request.

## The test topology

| Directory | What lives there | Marker |
|---|---|---|
| `tests/unit` | Pure functions and single classes. Fast, no I/O beyond `tmp_path` | none |
| `tests/contract` | Agreements that must not drift: schemas against runtime models, the toolchain, the MCP registry, generated documents | none |
| `tests/integration` | Real adapters wired together — file workspaces, live loopback servers, real MCP frames | `integration` |
| `tests/e2e` | The installed entrypoints, as a subprocess | `e2e` |
| `tests/live` | Real requests to whatever model provider this machine is configured for. **Spends real credit.** Skipped unless `OAK_LIVE_MODEL_TESTS=1`, and never collected by `make check` or CI | `live` |

Only `integration`, `e2e` and `live` are registered, and `--strict-markers` is on, so an
invented marker fails collection. Shared harnesses are `tests/runner_support.py`
(`build_compiled_case` drives the whole reference journey) and `tests/mcp_support.py`
(file-backed control plane, in-memory operation store, `MCPClient`).

**The PostgreSQL suites skip silently.** Roughly twenty tests — all but one under `tests/integration`, plus the installed-MCP handshake in `tests/e2e/test_mcp_interface.py` — are gated on
`OAK_TEST_DATABASE_URL`, and a skip looks exactly like a pass in the summary line. CI never
sets it. To actually run them:

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
make test-e2e          # the MCP handshake test is gated too
```

`compose.yaml` publishes no host port for PostgreSQL, which is why the override is needed.
This is recorded as `RR-019`.

## Conventions that will otherwise cost you time

- Every source file starts `# SPDX-License-Identifier: Apache-2.0`.
- Ruff line length is 100. Strict mypy covers `src`, `tools` and `scripts` — not `tests`.
- Assert on `OAKError.code`, never on message text. **Never assert on Rich-rendered
  `--help` output**: it wraps differently on a CI runner and has already broken a test that
  way. Assert behaviour.
- A new schema needs four things: the file in `schemas/`, an example in `examples/`, an
  entry in `EXAMPLE_BY_SCHEMA` in `scripts/validate_repository.py`, **and** a row in
  `schemas/README.md`.
- A new artifact kind needs registering in three places: `KIND_SCHEMA` and
  `JSON_MEDIA_KIND` in `src/oak/adapters/persistence/file_workspace.py`, and the `kind`
  enum in `schemas/workspace-manifest.schema.json`.
- A canonical document committed to a workspace needs both an `id` and a `version`.
- `CommandContext.idempotency_key` must be at least 16 characters, `correlation_id` at
  least 8.
- A new Python dependency needs a review entry in [dependencies.md](docs/dependencies.md)
  plus `uv lock`. Prefer `uv lock --upgrade-package <name>` over `make lock`, which also
  rewrites `pnpm-lock.yaml`.
- If you add a directory to the wheel's `force-include`, add it to
  `deploy/images/api.Dockerfile` too. A contract test enforces this, because omitting it
  once left the API image unbuildable for a whole sprint with no gate noticing.
- A REST change requires regenerating `openapi/oak.openapi.json`; the compatibility gate
  runs inside `make check`.
- A new `OAK-*` code requires regenerating `docs/error-codes.md`.

## The module boundary

`tools/check_boundaries.py` enforces the import graph, and it is not advisory:

- `oak.contracts` and `oak.domain` are **leaf** packages. They import nothing internal.
- `oak.runner` may import only `oak.contracts`, `oak.domain`, and itself. It is a separate
  trust domain, and that separation is the point — see
  [adr/architecture/0015](docs/adr/architecture/0015-typed-runner-operations.md).
- `oak.interfaces` may import `application`, `bootstrap`, `contracts` and `domain` — **not**
  `adapters`. An interface that needs an adapter needs an application service instead.
- A new package under `src/oak/` is import-locked to nothing until it is added to
  `INTERNAL_ALLOWED`.
- `oak.adapters` may import `contracts`, `domain` and `ports`.

It also enforces which **third-party** packages each layer may touch, which is the rule
people trip over first:

- `oak.domain` may not import `fastapi`, `pydantic`, `sqlalchemy`, `typer` or `uvicorn`.
- `oak.compiler`, `oak.ports`, `oak.application` and `oak.runner` may not import
  `fastapi`, `sqlalchemy`, `typer` or `uvicorn`.
- None of those five layers may import an HTTP client, a model-provider SDK or the
  operating-system credential store: `anthropic`, `google`, `httpcore`, `httpx`,
  `huggingface_hub`, `keyring`, `openai` or `urllib3`. Reaching a provider or a keychain is
  an adapter's job, and `src/oak/adapters/models/transport.py` is the only module in the
  package that opens a connection to one.

The point is that a framework choice stays replaceable: anything that would make the
domain depend on how it is served does not belong in the domain.

## Review policy

A change is reviewed against four questions, in this order:

1. **Does it fail closed?** Every new refusal path needs a test proving the refusal
   happens *before* any side effect, and that no state changed.
2. **Does it move authority?** Adding a capability to an interface, a tool to MCP, or a
   path to the runner is a trust-boundary change. The MCP prohibition list in
   [compatibility.md](docs/compatibility.md) is permanent: no command executor, arbitrary
   file read, secret resolver, policy override, approval, impersonation or runner-apply
   tool, under any version.
3. **Is a public surface affected?** Canonical schemas, REST/OpenAPI, the CLI, the MCP tool
   set and the runner protocol are governed by [compatibility.md](docs/compatibility.md).
   Additive is fine; anything else needs a changelog migration note.
4. **Does any claim exceed the evidence?** A documentation gate rejects unqualified
   assurance vocabulary, but it cannot catch a subtler overstatement. "Verified" means a
   test asserts it.

A change touching signing, approval, the runner, tenancy or input parsing gets the security
review recipe applied: name the misuse case, trace untrusted input to every side effect,
and add an adversarial test that a reviewer can reproduce.

## Governance

Decisions that change what OAK *is* — a contract, a trust boundary, a distribution
boundary — are recorded as ADRs before the code lands. See [adr/README.md](docs/adr/README.md);
the alternatives section, with the reason each was rejected, is the part that matters later.

Work is planned as ExecPlans under `docs/exec-plans/`. Completed ones stay as historical
engineering records — they contain candid defect post-mortems and are not current product
documentation. Reading the most recent one is the fastest way to understand how a sprint
actually goes.

Releases follow [release-process.md](docs/release-process.md). Release approval requires
named human sign-off and is never self-approved by whoever ran the build.

## Reporting a vulnerability

Not through a pull request or a public issue. See [SECURITY.md](SECURITY.md).

## Licence

Contributions are accepted under Apache-2.0, matching [LICENSE](LICENSE).
