<!-- SPDX-License-Identifier: Apache-2.0 -->

# Contributing to OAK Community

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

## The test topology

| Directory | What lives there | Marker |
|---|---|---|
| `tests/unit` | Pure functions and single classes. Fast, no I/O beyond `tmp_path` | none |
| `tests/contract` | Agreements that must not drift: schemas against runtime models, the toolchain, the MCP registry, generated documents | none |
| `tests/integration` | Real adapters wired together — file workspaces, live loopback servers, real MCP frames | `integration` |
| `tests/e2e` | The installed entrypoints, as a subprocess | `e2e` |

Only `integration` and `e2e` are registered, and `--strict-markers` is on, so an invented
marker fails collection. Shared harnesses are `tests/runner_support.py`
(`build_compiled_case` drives the whole reference journey) and `tests/mcp_support.py`
(file-backed control plane, in-memory operation store, `MCPClient`).

**The PostgreSQL suites skip silently.** Roughly twenty integration tests are gated on
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
