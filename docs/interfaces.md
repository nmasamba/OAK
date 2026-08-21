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

Or the whole stack through Compose: `docker compose up -d postgres migrate api worker web`.

### Remote CLI

Point the same CLI at a running API. Every command that has a REST surface runs
over it; output and exit codes are unchanged:

```bash
oak --server http://127.0.0.1:8080 design ./brief.yaml
oak --server http://127.0.0.1:8080 questions design-case.public-manual-qa
oak --server http://127.0.0.1:8080 evaluate candidate-03 --case design-case.public-manual-qa
```

`OAK_SERVER` sets the server for a session. `OAK_REMOTE_TIMEOUT` bounds how long
an asynchronous command polls a durable operation (default 120 s). Remote mode
requires an explicit design-case identifier (positional, or `--case` on
`evaluate`/`select`/`assure`/`plan`).

### MCP server

The MCP server speaks newline-delimited JSON-RPC 2.0 over stdio and needs the
same configuration as the API (it constructs the same persistent control plane):

```bash
export OAK_DATABASE_URL=postgresql+psycopg://oak:oak-local-only@127.0.0.1:5432/oak
oak-mcp            # or: oak mcp serve
```

Configure an MCP client to launch `oak-mcp` as a stdio server. The handshake
accepts protocol revisions `2025-06-18` and `2025-03-26`; an unknown revision
negotiates down to the newest supported one. The server exposes `tools` only —
no resources, prompts, or sampling.

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
  (≥16 characters); case successors require an expected version
  (REST `If-Match`, MCP/CLI derive or pass it). Reusing a key with the same
  normalized input converges on one result; reusing it with different input is a
  conflict.
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
| List questions | ○ | ○ | ○ | ○ | ○ |
| Confirm claims | ● | ● | ● | ● | ● |
| Generate candidates | ● | ● | ● | ● | ● |
| List candidates | ● | ● | ○ | ○ | ○ |
| Evaluate candidate | ● | ● | ● | ● | ● |
| Select candidate | ● | ● | ● | — | ● |
| Create assurance plan | ● | ● | ● | ● | ● |
| Compile bundle | ● | ● | ● | ● | ● |
| Read operation progress | — | — | ○ | ○ | ○ |
| Cancel operation | — | — | ● | — | ● |
| Export / import case | ● | ● | ● | — | ○ |
| Read audit / artifacts | — | — | ○ | — | ○ |
| Render deployment artifacts | ● | ✕ | — | ✕ | — |
| Render GitOps files | ● | ✕ | — | ✕ | — |
| Validate export/bundle/webhook | ● | ✕ | — | — | — |
| Sign plan | ● | ✕ | — | ✕ | — |
| Approve / revoke approval | ● | ✕ | — | ✕ | — |
| Dispatch runner / ingest | ● | ✕ | — | ✕ | — |
| Manage keys / extensions / policy | ● | ✕ | — | ✕ | — |
| Resolve a secret | ✕ | ✕ | ✕ | ✕ | ✕ |
| Run a generic command / read a file | ✕ | ✕ | ✕ | ✕ | ✕ |
| Apply to a production target | ✕ | ✕ | ✕ | ✕ | ✕ |

Notes:

- The **local-only** commands are `init`, `serve`, `mcp serve`, `keys`, `sign`, `approve`, `revoke-approval`, `dispatch`, `ingest`, `gitops`, `policy`, `render`, `extensions` and `validate`.
  With `--server` set they fail closed with `OAK-REMOTE-UNSUPPORTED` rather than
  acting on local state, and none of them is reachable over REST or MCP.
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
  can download a canonical export but cannot import one.
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
  *references* only; the runner resolves them locally after verification.
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
