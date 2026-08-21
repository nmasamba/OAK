<!-- SPDX-License-Identifier: Apache-2.0 -->

# Backstage starter for OAK Community

These files show a developer portal displaying OAK design-case and gate state
using only documented API behavior and links. No Backstage type appears in the
OAK core, and the portal never gains authority: it can create a draft case and
read state, and everything consequential — confirmation, selection, assurance,
compilation, signing, approval — stays inside OAK's own interfaces.

## Files

| File | Purpose |
|---|---|
| `catalog-info.yaml` | An `API` entity over the committed OpenAPI contract and a `Component` whose card reads case/gate state through documented `GET` paths |
| `template.yaml` | A Software Template creating a draft design case through `POST /v1/design-cases` with an explicit idempotency key |
| `app-config.oak.yaml` | The proxy fragment that forwards only the documented command headers to a loopback OAK API |

## Wiring

1. Run the OAK stack locally (`docker compose up -d postgres migrate api worker web`
   or `uv run oak-api` with a migrated database).
2. Merge `app-config.oak.yaml` into your Backstage app config.
3. Register `catalog-info.yaml` and `template.yaml` in the catalogue.
4. The template step uses the community `http:backstage:request` scaffolder
   action; install that optional backend module or replace the step with your
   own HTTP action.

## What a portal card may read

- `GET /v1/design-cases` — the tenant's case list (opaque cursor pagination);
- `GET /v1/design-cases/{case_id}` — status, allowed references, and `ETag`;
- `GET /v1/design-cases/{case_id}/audit` — the append-only gate/event timeline;
- `GET /v1/design-cases/{case_id}/artifacts` — the artifact index for links;
- `GET /v1/operations/{operation_id}` — durable operation progress.

Signed webhook envelopes (see `../portal/`) carry the same audit events for
push-style portals; verify them against the pinned publisher key with
`oak validate webhook <file> --public-key <identity.json>` before trusting one.

## What a portal cannot do

There is no approval, policy-override, secret, signing, or runner path on this
API surface, so no portal integration can create an approved state — the same
prohibition the interface contract places on every OAK transport. Mutating
calls the portal does make require an `Idempotency-Key` and, for case
successors, an `If-Match` version, exactly like every other client.
