<!-- SPDX-License-Identifier: Apache-2.0 -->

# Interfaces: setup, permission model, and capability matrix

OAK Community exposes one bounded design-and-planning workflow through five
transports: the local CLI, the persistent REST API, the web workspace, remote
CLI mode, and a bounded MCP server. Every transport maps onto the same
application services and the same `DesignCase` aggregate (ADR-0014), so
canonical meaning, transition outcomes, and audit lineage are identical across
them. `interface_origin` is recorded for audit and never grants authority.

This document covers setup, the permission model, the per-interface capability
matrix, and the operations that are deliberately unavailable in Community.
Compatibility guarantees for every surface here are in
[docs/compatibility.md](compatibility.md).

## Setup

### Local CLI (file mode, offline)

The default. Operates on a local workspace with no server:

```bash
oak init /tmp/oak-demo && cd /tmp/oak-demo
oak design /path/to/examples/briefs/public-manual-qa.yaml --output yaml
oak questions --output json
oak confirm --answers /path/to/examples/briefs/public-manual-qa-answers.yaml
oak candidates
oak evaluate candidate-03
oak select candidate-03 --rationale-file decision.md
oak assure candidate-03 --output ./assurance/
oak plan candidate-03 --target /path/to/examples/targets/local-fixture.yaml --output ./bundle/
oak export --output ./case-export/
```

### REST API and web workspace

The persistent control plane needs PostgreSQL and a worker:

```bash
export OAK_DATABASE_URL=postgresql+psycopg://oak:oak-local-only@127.0.0.1:5432/oak
uv run oak-db-migrate
uv run oak-api        # http://127.0.0.1:8080
uv run oak-worker     # drains durable operations
```

Or the whole stack through Compose:

```bash
docker compose up -d --build postgres migrate api worker web
curl --fail http://127.0.0.1:8080/version   # --build is not optional; see operations.md#install
```

The committed contract is [openapi/oak.openapi.json](../openapi/oak.openapi.json), and a
running `oak-api` also serves it live at `/openapi.json`. That route is **not** part of the
`/v1` contract and is not covered by the compatibility policy — it is a debugging
affordance that comes with the framework, and it binds to the same address as everything
else, so on a non-loopback bind it is exposed too. FastAPI's interactive `/docs` and
`/redoc` pages are switched off: they load scripts from a public CDN into the API's origin.

### Remote CLI

Point the same CLI at a running API. Every command that has a REST surface runs
over it; output and exit codes are unchanged:

```bash
oak --server http://127.0.0.1:8080 design ./brief.yaml
oak --server http://127.0.0.1:8080 questions design-case.public-manual-qa
oak --server http://127.0.0.1:8080 evaluate candidate-03 --case design-case.public-manual-qa
```

`OAK_SERVER` sets the server for a session; the URL may end in `/v1` or not.
`OAK_REMOTE_TIMEOUT` bounds how long an asynchronous command polls a durable operation
(default 120 s). Remote mode requires an explicit design-case identifier (positional, or
`--case` on `evaluate`/`select`/`assure`/`plan`/`architecture`/`report`/`research`/`research
review`); a case the server does not hold is reported as `OAK-CASE-NOT-FOUND`, naming it, as
the local CLI does, where REST and MCP answer `OAK-WORKSPACE-NOT-FOUND`.

### MCP server

The MCP server speaks newline-delimited JSON-RPC 2.0 over stdio and needs the
same configuration as the API (it constructs the same persistent control plane):

```bash
export OAK_DATABASE_URL=postgresql+psycopg://oak:oak-local-only@127.0.0.1:5432/oak
oak-mcp            # or: oak mcp serve
```

Under Compose, PostgreSQL is not published on the host, so run the server inside the
`api` container instead. It inherits that service's database, artifact store, actor and
tenant:

```bash
docker compose exec -T api oak-mcp
```

Configure an MCP client to launch `oak-mcp` as a stdio server — under Compose, the
command `docker` with the arguments
`compose -f /full/path/to/compose.yaml exec -T api oak-mcp`. The handshake
accepts protocol revisions `2025-06-18` and `2025-03-26`; an unknown revision
negotiates down to the newest supported one. The server exposes `tools` only —
no resources, prompts, or sampling. [tour.md](tour.md) drives the candidate,
evaluation, assurance, compile and progress tools from a shell, with the real requests
and replies.

## Permission model

- **Actor and tenant.** Community runs a single documented local actor
  (`OAK_LOCAL_ACTOR`, default `local-user`) and tenant (`OAK_LOCAL_TENANT`,
  default `local`). REST binds them from `X-OAK-Actor`/`X-OAK-Tenant` headers;
  MCP binds them from `actor`/`tenant_id` tool arguments, which are optional on
  every tool except `oak_claims_confirm`, where a named `actor` is required; the local CLI
  reads `OAK_ACTOR`. A request that names a different tenant receives an opaque
  not-found denial (no existence leak); a request that names a different actor
  receives `OAK-ACTOR-DENIED`. `interface_origin` is set by the transport
  (`cli`, `api`, `mcp`, `web`, `portal`, `import`) and is audit metadata only.
- **Idempotency and versions.** Mutations require an idempotency key
  (16 to 240 characters); case successors require an expected version
  (REST `If-Match`, MCP/CLI derive or pass it). Reusing a key with the same
  normalized input converges on one result; reusing it with different input is a
  conflict. A key is scoped to the case it acts on, and creating or importing a case
  names that case in its body: the same key sent with a different brief or a different
  export creates or imports a different case rather than conflicting, so a client that
  retries must resend the same body.
- **Separation of duties.** Proposal, confirmation, selection, compilation,
  signing, approval, and target mutation are distinct steps and no single call
  collapses them (build security invariants, ADR-0015). This is why candidate
  *selection* — a material decision — is not an MCP tool.
- **Community is not multi-tenant-secure.** The local tenant is a convenience,
  not evidence of tenant isolation controls; see ADR-0012.

## Capability matrix

Legend: ● available · ○ read-only · — not on this interface · ✕ never (permanent
prohibition).

| Capability | Local CLI | Remote CLI | REST | MCP | Web |
|---|---|---|---|---|---|
| Create design case | ● | ● | ● | ● | ● |
| Read case / intent | ○ | ○ | ○ | ○ | ○ |
| Interpret brief | ● | ● | ● | ● | ● |
| Interpret brief with Online AI or Local AI | ● | ● | ● | ● (explicit `interpreter`; default deterministic) | ● |
| List questions | ○ | ○ | ○ | ○ | ○ |
| Confirm claims | ● | ● | ● | ● | ● |
| Generate candidates | ● | ● | ● | ● | ● |
| List candidates | ● | ● | ○ | ○ | ○ |
| Evaluate candidate | ● | ● | ● | ● | ● |
| Select candidate | ● | ● | ● | — | ● |
| Create assurance plan | ● | ● | ● | ● | ● |
| Compile bundle | ● | ● | ● | ● | ● |
| Read the chosen architecture (`oak architecture`; `GET …/architecture`) | ○ | ○ | ○ | — | ○ |
| Record the architecture report (`oak report --record`; `POST …:record-report`) | ● | ● | ● | — | ● |
| Read the research plan (`oak research --plan`; `GET …/research-plan`) | ○ | ○ | ○ | — | ○ |
| Run research (`oak research --consent <digest>`; `POST …:research`, with `X-OAK-Model-Token`) | ● | ● | ● | — | ● |
| Review a research item (`oak research review`; `POST …:review-research-item`) | ● | ● | ● | — | ● |
| Read the recorded report, as JSON or PDF (`oak report`; the artifact read) | ○ | ○ | ○ | — | ○ |
| Read operation progress | — | — | ○ | ○ | ○ |
| Cancel operation | — | — | ● | — | ● |
| Export / import case | ● | ● | ● | — | ○ |
| Read audit / artifacts | — | — | ○ | — | ○ |
| List design cases | — | — | ○ | — | ○ |
| Render deployment artifacts | ● | ✕ | — | ✕ | — |
| Render GitOps files | ● | ✕ | — | ✕ | — |
| Validate export/bundle/webhook | ● | ✕ | — | — | — |
| Sign plan | ● | ✕ | — | ✕ | — |
| Approve (`dry_run`, `architecture`, `apply`, `rollback`, `destroy`) / revoke approval | ● | ✕ | — | ✕ | — |
| Dispatch runner / ingest / record an observation (`oak observe`) | ● | ✕ | — | ✕ | — |
| Manage keys / extensions / policy | ● | ✕ | — | ✕ | — |
| Store, verify or remove the Hugging Face token | ● | ✕ | ● | ✕ | ● |
| Read the catalogue and see the pairs a token can call | ● | ✕ | ● | ✕ | ● |
| Pin the Online AI pair or the Local AI model | ● | ✕ | ● | ✕ | ● |
| Resolve a secret | ✕ | ✕ | ✕ | ✕ | ✕ |
| Run a generic command / read a file | ✕ | ✕ | ✕ | ✕ | ✕ |
| Apply to a production target | ✕ | ✕ | ✕ | ✕ | ✕ |

Notes:

- The **local-only** commands are `init`, `serve`, `mcp serve`, `keys`, `models`, `sign`, `approve` (every action, including `approve architecture`), `revoke-approval`, `dispatch`, `ingest`, `observe`, `gitops`, `policy`, `render`, `extensions` and `validate`.
  With `--server` set they fail closed with `OAK-REMOTE-UNSUPPORTED` rather than
  acting on local state. None of them is reachable over MCP, and none but `models` over
  REST: the model configuration also has loopback `/v1/models` routes guarded by the
  per-process capability token (ADR-0016).
- `oak architecture` is not local-only. In remote mode it is composed from the
  existing case and artifact reads, and it writes nothing. Since Sprint 12 REST
  also serves the same document read-only at
  `GET /v1/design-cases/{case_id}/architecture?candidate_id=&format=json|yaml`,
  composed at request time with `Content-Disposition: attachment`, so the web
  workspace can hand it over as one file; it has no stable digest of its own and
  its parts carry theirs.
- `oak report` is not local-only. `--record` records the architecture report, which
  REST exposes as `POST /v1/design-cases/{case_id}:record-report` (Sprint 13). It
  stores the report document and its PDF as artifacts, revises the case at its own
  status, appends `report_recorded` and authorizes nothing. Without `--record` it
  reads the latest recorded report through the artifact read and writes `--output`
  only after checking the bytes against the digest the case names. A model mode
  (`--narrative online|local`, `?narrative=`) adds one labelled note per main slide
  and needs the capability token like a model-mode interpretation. MCP has no report
  tool (kickoff decision K6).
- The MCP tool set is exactly the ten interface-contract tools plus the
  read-only `oak_operation_get` progress query. A contract test pins this set;
  a new tool cannot appear without failing it.
- The CLI has no separate candidate-list command: `oak candidates` generates and
  displays them, converging on the existing set when retried with the same
  idempotency key, so that cell is marked available rather than read-only. REST,
  MCP, and the web workspace each expose a distinct read.
- Questions have no REST path of their own. Every interface derives them from the
  `unresolved_questions` field of the case read, which is why the question set is
  identical across all four interfaces in the conformance suite.
- Durable operations exist only in the persistent (PostgreSQL) control plane. Local
  CLI file mode runs the compiler stages synchronously and has no operation to read
  or cancel; remote CLI polls the operation internally for its asynchronous commands
  and exposes no standalone operation command.
- The CLI reads audit events and artifacts through `oak export`, which emits the full
  canonical set; there is no separate audit or artifact command. The web workspace
  downloads the canonical export, each stored artifact (saved only when its SHA-256
  matches `X-OAK-Artifact-Digest`) and the architecture document, but cannot import an
  export.
- A server keeps one workspace per case, named from the case, while a local workspace is
  named from its directory. An export from a local workspace therefore carries an identity
  the server refuses (`oak --server import` answers `OAK-IMPORT-SCOPE`); an export taken
  from a server imports into a local workspace. To move a local case onto a server, create
  it there from the same brief and confirm the same answers.
- `oak validate` is a server-free read-only checker (export, bundle, webhook)
  intended for CI and portals. It checks schema validity, digest integrity, and
  the execution-field ban across all three kinds. For a compiled bundle it
  verifies the digest edges that exist in a detached directory
  (runner-plan → deployment-bundle → architecture-decision) and that the runner
  plan is an inert draft; it does not bind `assurance-plan.json` or
  `semantic-manifest.json`, which carry no digest edge into the bundle spine, and
  it does not re-run compilation. The authoritative integrity binding for a plan
  is the separately signed runner envelope and approval, not a review bundle.
  `oak validate webhook` verifies the signature against the pinned publisher key
  only, never the key embedded in the envelope.

## Explicitly unavailable in Community

These are deliberately absent; their presence would be a different product
(see ADR-0012 and the Sprint backlog), not a Community feature:

- Real authentication, SSO/OIDC, or multi-tenant isolation controls.
- Any production or customer target, and any `oak apply` to one. The compiled
  runner plan is inert until it is separately signed, approved, and
  independently verified by the runner against an isolated non-production
  fixture.
- Secret resolution through any interface. Canonical documents carry secret
  *references* only; the runner resolves them locally after verification. This is a
  different thing from storing the user's own model-provider key, which the local CLI,
  the loopback REST routes and the web workspace do support: that key is machine-local
  configuration, never enters a canonical document, and is never returned by any
  interface. It is permanently absent from MCP and from remote CLI mode.
- Runner apply, approval, signing, or dispatch over REST, MCP, remote CLI, web,
  or portal. Runner apply is intentionally absent from the MCP surface entirely.
- A generic command executor, arbitrary file reader, or policy-override tool on
  any interface.
- A live webhook dispatcher. Community ships the signed
  [webhook envelope contract](../examples/portal/README.md) and a validator, not
  a delivery service.

## Portals

Developer portals use REST plus signed webhook examples; see
[examples/backstage/](../examples/backstage/README.md) and
[examples/portal/](../examples/portal/README.md). A portal integration is a thin
adapter over documented API behavior; it cannot create an approved state or
reach any capability marked ✕ above.
