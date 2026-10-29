<!-- SPDX-License-Identifier: Apache-2.0 -->

# Operations runbook

For the person running OAK Community `0.9.0`: install, configure, observe, back up,
restore, upgrade, troubleshoot, export and remove it.

**Scope.** OAK Community is a local-first developer release. It has no authentication,
no multi-tenant isolation, and no production readiness claim. Its actor and tenant are
headers, not credentials. Do not expose it beyond a machine you control; see
[Securing a local deployment](#securing-a-local-deployment) for what "beyond" means
precisely.

Companion documents: [platforms.md](platforms.md) for what is supported where,
[configuration.md](configuration.md) for every environment variable,
[error-codes.md](error-codes.md) for what a stable `OAK-*` code means, and
[security/residual-risk.md](security/residual-risk.md) for what this release does not
defend against.

---

## Install

Pick one of the three paths in [platforms.md](platforms.md#install-paths). The container
path is the shortest:

```bash
docker compose up -d --build postgres migrate api worker web
curl --fail http://127.0.0.1:8080/version
```

**Always pass `--build`, and always check `/version`.** `docker compose up -d` reuses an
existing image rather than rebuilding when the source changes. During the `0.7.0` rehearsal
the stack came up serving `0.5.0.dev5` from a three-day-old image without any warning;
`/version` is what caught it, and it is the only thing that would have.

The worker is not optional if you intend to use the API: candidate generation,
evaluation, compilation and a consented research run are durable operations, and without
a worker they stay queued forever with no error.

The API image takes Debian's security updates from a dated snapshot named in its
Dockerfile, and the web image's packages are its pinned base image's, so **rebuilding
reproduces the same image** (`RR-006`, closed by Tier 3's Batch A); a release moves the
snapshot date and re-pins the web base to take the patches published since, and
`make scan-images` reports what the Dockerfiles as they stand carry. As of `0.9.0` the web
image reports no findings at any severity and the API image has no CRITICAL findings and
44 HIGH with no vendor fix available — eight distinct advisories, most of them counted
once per package Debian builds from one source
([container-scan.md](release/0.9.0/container-scan.md)).

Verify the release artifacts you downloaded before installing them — see
[release-process.md](release-process.md#verifying-a-release). The verifier also checks the
maintainer's signature over the manifest; `0.7.1` and `0.9.0` are **unsigned**, so for
them checksums prove the bytes match the manifest, not who produced them.

---

## Configure

Every setting is an environment variable; there is no configuration file.
[configuration.md](configuration.md) is the complete list, and a contract test keeps it
that way.

The ones that change a trust boundary rather than a path:

| Variable | Why it matters |
|---|---|
| `OAK_ALLOW_NON_LOOPBACK` | Setting it exposes an unauthenticated service |
| `OAK_DATABASE_URL` | Carries a password in the Compose default |
| `OAK_TRUST_DIRECTORY` | Holds the Ed25519 **private** signing keys |
| `OAK_RUNNER_TRUST_ANCHORS` | Decides which signatures the runner will believe |
| `OAK_ALLOWED_HOSTS` | Widens the `Host` names the API will answer to, past the loopback names it accepts by default |
| `OAK_CREDENTIALS_DIRECTORY` | Holds user-supplied model-provider keys and the capability token. Never back it up |
| `OAK_MODEL_ENDPOINT_LOCAL` | Where the `local` model family sends briefs. Refused unless it is a loopback address, because plain `http` is permitted there |
| `OAK_RUNNER_TARGET_PROFILE` | Its `execution.mutation_acknowledgement` decides whether the runner only creates containers or also starts them, and its `execution.component_images` decides which images they run. On `isolated-non-production-hardened-start`, those are running processes on this machine (`RR-043`) |

One setting deserves attention before you have any data: **`OAK_ARTIFACT_ROOT` defaults
to the relative path `.oak/server-artifacts`**, resolved against whatever directory the
process was started in. Set it to an absolute path now. A backup procedure cannot copy a
directory whose location depends on where someone happened to be standing.

**Limits.** The API admits 1,200 requests a minute from one client address and 6,000 for
one tenant, a tenant may have 100 operations queued or running, and a case may record 100
billable model requests a day; past each, the answer is `429` with `Retry-After`
(`OAK-RATE-LIMIT-ADDRESS`, `OAK-RATE-LIMIT-TENANT`, `OAK-OPERATION-QUOTA`,
`OAK-MODEL-BUDGET`). The four `OAK_*` rows in [configuration.md](configuration.md) set
them, and `0` switches one off. The request limiter's state is the `oak-api` process's
own: two processes count apart, and a restart forgets. Everything on this machine, the
browser included, shares one client address as the API sees it, and the health probes are
never counted against it.

---

## Observe

Be realistic about what is available: OAK Community writes **application logs but no
metrics**. What you have is the logs, a handful of endpoints and the database.

### Logs

`oak-api`, `oak-worker` and `oak-mcp` write one JSON object per line to **stderr**
(`docker compose logs api worker`), at `INFO` unless `OAK_LOG_LEVEL` says otherwise.
Before its first line, `oak-api` may print up to three plain-text startup notices: the
non-loopback bind warning, a missing `OAK_DATABASE_URL`, and where the model-configuration
token was written. A refusal that comes before logging is set up is plain text too, exit
`1`: `CODE: message` for an unknown `OAK_LOG_LEVEL` (`OAK-LOG-CONFIG`), a non-loopback bind
without the acknowledgement (`OAK-SAFE-BIND`), or the worker's or MCP server's own
configuration (`OAK-WORKER-CONFIG`, `OAK-MCP-CONFIG`), and a bare message for a bad
`OAK_PORT` or `OAK_WORKER_ID`. Any other failure to start, a database URL that does not
parse included, ends with a `startup_failed` line naming the error's type and code, never
its message (and, from `oak-api`, the host and port), and exits `1`; a port already in use
is `OAK-SERVE-BIND`. A one-shot worker (`OAK_WORKER_ONCE=1`) whose
cycle fails ends the same way with `cycle_failed`. `oak-api` serves from one process and,
once the application is built and its socket listening, says where (`api_listening`, with
`host` and `port`); uvicorn's own start-up lines are not written. `OAK_HOST` is one address:
`localhost` listens on the IPv4 loopback address only.

`oak serve` writes the same lines, after a first plain-text line that prints the
model-configuration token itself, and its `#token=` link, for you to paste into the
browser; it is the interactive command, so treat its stderr as a terminal, not a log to
ship. Run `oak-api` (or Compose) where the log is kept: it prints only where the token was
written. A refusal there is `CODE: message`, exit `2`, or `OAK-SERVE-FAILED` and the
error's type, exit `1`, for one that is not OAK's.

`oak-api` writes one access line per request; `OAK_ACCESS_LOG=false` turns it off. The
health probes `/healthz` and `/readyz`, which Compose's healthcheck calls every two
seconds, are logged at `DEBUG`. A line, as written (keys in alphabetical order):

```json
{"code":"OAK-CASE-NOT-FOUND","component":"oak-api","duration_ms":1.1,"event":"request","level":"INFO","logger":"oak.api.access","method":"GET","request_id":"8d6cb6bece211744","route":"/v1/design-cases/{case_id}","status":404,"time":"2026-10-29T02:55:21.519Z"}
```

The `route` is the template the request matched, never the path it named, and `unmatched`
when it matched none. The `request_id` is minted per request and returned to the caller as
the `X-OAK-Request-ID` response header, a `500` included, so a user can quote it in a report
and you can find the line. The `code` is the error the response carried, a refusal by the
host, origin or size checks included, and `OAK-INTERNAL` for an error nothing handled, whose
type is the line's `error_type`. Such an error is also a `request_failed` line at `ERROR`
(route, request ID, type and code), written whatever `OAK_ACCESS_LOG` says and on the quiet
routes too. `oak-worker` writes `operation_cycle` (operation ID, kind,
outcome, attempt, duration and, on failure, the code) and `cycle_failed` (the error's code,
or `OAK-WORKER-CYCLE` for an error that is not OAK's, and its type). `oak-mcp` writes
`mcp_started` when it starts.

A line is built from an allowlist of fields (`src/oak/interfaces/logs.py`), never by
redacting free text, so a brief, an answer, a model key, a token, a header, a query string,
a request or response body, a research term, the tenant and the actor never appear. An
exception appears as its type and, for an OAK error, its code; its message and traceback
never do, because they can quote the request. A library's own record (uvicorn, SQLAlchemy)
appears as its logger and level only. `tests/integration/test_log_leakage.py` runs a whole
journey through the API and the worker with a sentinel in the brief (and the case id named
from it), the answers, the actor, a tenant, a model key, a wrong capability token, a bearer
token, a correlation ID, an idempotency key, a query string, a `Host` header, an exception
message and a failing worker cycle, and fails if one reaches a log line; research terms and
`oak-mcp` are not in that journey, and what keeps their words out is the allowlist itself,
which no field can carry text through (`tests/unit/test_logs.py`). To join a line to what
happened, read the case's audit trail, which records the actor, the tenant and the
correlation ID under its own controls. Lines carry no tenant or environment field: OAK
Community runs one local tenant, and a line holds nothing of a tenant's to scope; the
original spec repo's rule to scope logs by tenant and environment is for a multi-tenant
edition, which would add the scope with its own review. `oak-mcp` logs only to stderr: its
stdout is the JSON-RPC protocol.

This section is about observing the OAK services themselves. `oak observe` is a different
thing: it records what an installed architecture did, from signed runner evidence, in an
`observation_record` (see [Installed architectures](#installed-architectures)). It adds no
log or metric for OAK.

| Signal | Where | What it tells you |
|---|---|---|
| Liveness | `GET /healthz` | The process is accepting requests |
| Readiness | `GET /readyz` | The database answered **at the schema revision this release expects**, or 503 — when it did not answer, when `OAK_DATABASE_URL` is unset entirely (the case `oak-api` will otherwise start happily in), and when the database has not been migrated to this release or was migrated by a newer one — see [Upgrade](#upgrade) |
| Build identity | `GET /version` | Version and `OAK_COMMIT` |
| Projection lag | `GET /v1/system/outbox-lag` | Pending outbox events and sequence lag for the built-in projection; `latest_sequence` and `indexed_through` are summed over cases, so `sequence_lag` is the number of events not yet indexed across all of them |
| Work in flight | `GET /v1/operations/{id}` | Status, attempts and checkpoint of one durable operation |
| Contract | `GET /openapi.json` | The live OpenAPI document. Useful for debugging; **not** part of the `/v1` contract, not covered by the compatibility policy, and exposed on whatever address the API binds. FastAPI's interactive `/docs` and `/redoc` pages are switched off: they load scripts from a public CDN into the API's origin |

```bash
curl --fail --silent http://127.0.0.1:8080/readyz
curl --fail --silent http://127.0.0.1:8080/v1/system/outbox-lag
```

To tell whether the worker is alive, watch `pending_events` on the lag endpoint while a
compile runs: a number that only grows means the worker is not consuming, and the
worker's `operation_cycle` lines say which operations it ran.

The absence of metrics is recorded as a limitation, not presented as a design goal — see
`RR-015`.

---

## Back up

OAK keeps state in **two stores that are backed up by different tools**, plus a key
directory that is not in either.

| What | Where | Backed up by |
|---|---|---|
| Metadata: workspaces, case versions, artifact index, audit, operations, outbox | PostgreSQL | `pg_dump` |
| **Artifact bytes** | `$OAK_ARTIFACT_ROOT/sha256/` (Compose volume `oak-community_oak-artifacts`) | A filesystem copy |
| **Model state** — *do not back this up* | `$OAK_CREDENTIALS_DIRECTORY` and `$OAK_MODELS_DIRECTORY` (Compose volume `oak-community_oak-model-state`) | Nothing. It holds user-supplied provider keys in plain text and can be re-entered in seconds; a backup of it is a copy of those keys (`RR-040`) |
| Signing keys and trust anchors | `$OAK_TRUST_DIRECTORY` (default `~/.oak/trust`) | A **separate**, protected copy |
| Outbound dispatch mailbox | `$OAK_DISPATCH_MAILBOX` (default `~/.oak/mailbox`) | A filesystem copy, if leases are in flight. The runner removes processed dispatch directories older than `OAK_RUNNER_DISPATCH_RETENTION_DAYS` (default 30) at the end of each run, never the newest nor one whose completion is not yet ingested |
| Extension quarantine and activations | `$OAK_EXTENSIONS_DIRECTORY` (default `~/.oak/extensions`) | A filesystem copy |
| Runner identity, journals (never removed), the consumed-nonce ledger (holding each nonce until its lease's expiry plus five minutes), the revocation-sequence mark, and `docker-config/`, the empty Docker client configuration the runner's `docker` commands use (a `run-*` directory there is a run's private working directory, removed when it ends: nothing to back up) | `$OAK_RUNNER_HOME` (default `~/.oak/runner`) | A **separate**, protected copy — it holds the runner's own Ed25519 private key |

> **A `pg_dump` alone is not a backup.** Artifact bytes are read *only* from the artifact
> root; the JSONB copy in `artifact_versions.canonical_document` is never read back at
> runtime. Restoring only the database gives you a control plane that indexes artifacts
> which are not on disk, and every read fails later at use time rather than at restore
> time. This is proven, not asserted:
> `tests/integration/test_backup_restore.py::test_a_postgresql_deployment_restored_without_its_artifact_root_is_detected`.

Procedure — take both from the same point in time:

```bash
docker compose stop api worker            # quiesce writers first
docker compose exec -T postgres pg_dump -U oak -Fc oak > oak-metadata.dump
docker run --rm -v oak-community_oak-artifacts:/artifacts -v "$PWD":/backup alpine \
  tar czf /backup/oak-artifacts.tar.gz -C /artifacts .
docker compose start api worker
```

Take the two in that order and without writers running. They are separate stores with no
shared transaction, so a backup taken while the API is serving can capture an artifact the
database does not yet index, or the reverse.

Back up `~/.oak/trust` separately and treat it as a credential store. Losing it does not
corrupt any stored case; it means previously signed envelopes can no longer be re-signed
by the same identity, and anything pinned to those anchors must be re-pinned.

**A canonical export is not a deployment backup.** `oak export` carries workspace state,
artifacts, audit and idempotency records. It does not carry operations, job checkpoints,
outbox events, consumer receipts or projection positions, and it does not carry your
keys: the plan signature and the approvals of a file workspace travel as signed documents,
verifiable only against the anchors that signed them. It is the portability path, not the recovery path.

---

## Restore

Restore-forward. Never downgrade.

```bash
docker compose down                                       # stop everything
docker volume rm -f oak-community_oak-postgres-data       # start from a clean database
docker volume rm -f oak-community_oak-artifacts
docker volume rm -f oak-community_oak-model-state        # provider keys are re-entered, not restored
docker compose up -d --wait postgres                      # --wait: initdb must finish first
docker compose exec -T postgres pg_restore -U oak -d oak --clean --if-exists < oak-metadata.dump
docker run --rm -v oak-community_oak-artifacts:/artifacts -v "$PWD":/backup alpine \
  tar xzf /backup/oak-artifacts.tar.gz -C /artifacts
docker compose up -d --build migrate api worker web
```

`--wait` matters: `docker compose up -d` returns as soon as the container starts, and the
PostgreSQL entrypoint is still running `initdb` at that point, so an immediate `pg_restore`
fails with "the database system is starting up". The database named `oak` already exists
after initialisation — `POSTGRES_DB` creates it — so there is no `createdb` step, and
`--clean --if-exists` will print harmless notices about objects that were not there to drop.

`docker compose up -d migrate ...` re-runs `oak-db-migrate`. Against a dump that already
carries `alembic_version` at the current revision it is a no-op, which is the intended
restore-forward behaviour.

Then **verify the restore rather than assuming it**.

On a Compose deployment neither `OAK_DATABASE_URL` nor `OAK_ARTIFACT_ROOT` is reachable
from your shell: they name `postgres:5432` and `/var/lib/oak/artifacts` *inside* the
containers. Publish the database port and copy the artifact volume out first — this is the
sequence the `0.7.0` rehearsal actually ran:

```bash
cat > compose.override.yaml <<'YML'
services:
  postgres:
    ports:
      - "127.0.0.1:15432:5432"
YML
docker compose up -d --wait postgres

mkdir -p /tmp/oak-restored-root
docker run --rm -v oak-community_oak-artifacts:/artifacts -v /tmp/oak-restored-root:/out \
  alpine cp -R /artifacts/sha256 /out/

python scripts/verify_deployment.py \
  --database-url "postgresql+psycopg://oak:oak-local-only@127.0.0.1:15432/oak" \
  --artifact-root /tmp/oak-restored-root
```

For a non-Compose deployment, where both values already name paths and hosts you can
reach, the two arguments are simply `$OAK_DATABASE_URL` and `$OAK_ARTIFACT_ROOT`.

For a file workspace:

```bash
python scripts/verify_deployment.py --workspace /path/to/workspace
```

It walks every row of `artifact_versions`, re-reads each object from the artifact root and
re-checks its size and SHA-256. Exit `0` means the two stores agree; exit `2` names each
artifact that does not resolve, and also fires when the index is empty unless you pass
`--allow-empty`; exit `3` means the deployment could not be read at all — an unreachable
database, a missing workspace — which is the code you are most likely to hit mid-restore. It is read-only, and it detects missing objects, truncated
objects and same-length-different-content substitution.

**Compare the count against what you backed up.** "Verified 0 artifacts" after a restore is
a failed restore, not a clean one, so the tool treats an empty index as a failure and says
so loudly. Pass `--allow-empty` only when you genuinely expect nothing — a fresh install.

> **On a development machine, expect false alarms, and know how to read them.** The tool
> walks *every* row of `artifact_versions`. If this database has ever been the target of
> `OAK_TEST_DATABASE_URL` — which is how the PostgreSQL-gated suites are meant to be run —
> it also holds rows those suites wrote while keeping the bytes in per-test temporary
> directories that no longer exist. Those rows can never verify, so the tool reports
> "the metadata and the artifact bytes are not from the same backup, or one of them is
> damaged" on a restore that was in fact perfect. The `0.8.0` rehearsal hit exactly this:
> 137 of 1,118 referenced digests were already missing *before* the backup was taken,
> accounting for 5,766 of 8,389 rows.
>
> Tell the two apart before you distrust a backup:
>
> ```bash
> # Was the shortfall already there? Count objects in the archive you restored from.
> tar tzf oak-artifacts.tar.gz | grep -c 'sha256/.'
> # ...against the distinct digests the database references.
> docker compose exec -T postgres psql -U oak -d oak -tAc \
>   "select count(distinct digest) from artifact_versions"
> ```
>
> If the archive already held fewer objects than the database references, the restore is
> faithful and the orphans predate it. If the counts agree but verification still fails, you
> have a real problem: the two stores are from different points in time, or one is damaged.
> A production deployment, whose database no test ever wrote to, has no orphans and the
> tool's verdict is unambiguous.

---

## Upgrade

### The control-plane database

Migrations are forward-only. `0001_sprint3_baseline` is currently the only revision, and
its `downgrade()` deliberately raises — pinned by
`tests/integration/test_backup_restore.py::test_the_alembic_baseline_refuses_to_downgrade`.

1. Back up both stores as above, and verify the backup restores somewhere else first.
2. Record the current revision:
   ```bash
   docker compose exec -T postgres psql -U oak -d oak -c "SELECT version_num FROM alembic_version"
   ```
3. Stop `api` and `worker`.
4. Deploy the new version and run `oak-db-migrate` (the Compose `migrate` service does
   this for you and `api`/`worker` wait on it).
5. Start `api` and `worker`, then verify with `scripts/verify_deployment.py`.

> **`/readyz` checks the schema revision.** It answers 503 until the database is at the
> revision this release's migrations end at: a new `oak-api` against a database that has
> not been migrated yet, or an old binary against a schema a newer one migrated, stays not
> ready instead of failing later with opaque query errors (`RR-016`, closed). Run
> `oak-db-migrate` (step 4) and readiness turns green; the Compose `depends_on: migrate`
> guard does that for you. Step 2's record of the previous revision is still what a
> restore-forward needs.

> If you invoke `alembic` directly rather than `oak-db-migrate`, note that
> `migrations/env.py` reads `OAK_DATABASE_URL` from the environment and **ignores** the
> `sqlalchemy.url` config option. Export the variable.

### A file workspace

A file workspace names its format in its manifest's `schema_version`: `0.4.0`, the format
every published release wrote. This build reads the current format and carries an older
one forward with `oak workspace migrate`, the only command that migrates. It runs the
format's chain of pure, idempotent steps under the workspace lock, writes any object a step
produced as a new object, records a reshaped design case as a successor with a
`workspace_migrated` audit event, and leaves every stored object and the history as they
were; running it twice is a no-op. Nothing migrates on an ordinary read: until it has run, a
workspace at an older format is refused on every other command with
`OAK-WORKSPACE-MIGRATE`, naming the command, and `oak workspace status` says where the
workspace stands. `oak export` copies a workspace at any format this build knows **as it
is**, so a workspace can always be rescued, and `oak import` and `oak validate export` take
such an export as it is, saying it needs migrating. No published release has written a
format other than the current one, so the shipped chain holds no step and upgrading to this
tree needs nothing; the mechanism is what a future format bump ships with, in the same
release, beside the PostgreSQL store's own alembic revision
(`tests/integration/test_workspace_format.py`, and the `0.9.0` reference workspace in
`tests/integration/test_workspace_corpus.py`).

A format this build does not know, one a newer build wrote, is refused on every command,
`export` included, with `OAK-WORKSPACE-FORMAT`, naming the build that reads it: nothing can
be believed about such a manifest, and downgrade is not supported
(`tests/integration/test_backup_restore.py::test_a_workspace_written_by_an_unknown_format_fails_closed`).

**Therefore: `oak export` before upgrading.** The exported tree is what a newer build reads
and, if it must, migrates. Going back is where it bites: once `0.9.0` records an observation
in a workspace, the new `observation_record` kind means `0.8.0` can no longer validate that
workspace's manifest. The same holds again for this tree: once it records a report
(`architecture_report`, `report_narrative`, `report_rendering`), research
(`research_snapshot`, `research_review`) or a migration (`workspace_migrated`) in a
workspace, the published `0.9.0` cannot validate its manifest — on every command, including
`export` — although this tree also reports `0.9.0`. Export before running an older build
against a workspace. Make exporting first a habit before an upgrade ever needs it. `RR-017`
records the mechanism as closed, and downgrade as unsupported.

### Rollback limits

There is no downgrade path for the database. Rolling back means restoring the backup you
took in step 1 into a clean database and running the *older* binary's migrations. If you
did not take that backup, there is no rollback.

---

## Troubleshoot

Every refusal carries a stable `OAK-*` code on stderr (CLI) or in the problem-details
body (REST). Look it up in [error-codes.md](error-codes.md). CLI exit codes are `0`
success, `2` refusal or invalid input, `4` version or idempotency conflict.

| Symptom | Likely cause | What to do |
|---|---|---|
| An operation never leaves `queued` | No worker running | Start `oak-worker`; check `pending_events` on the lag endpoint |
| `OAK-WORKSPACE-CORRUPT` on every command | The manifest or an indexed object is unreadable or invalid | Run `scripts/verify_deployment.py --workspace`; restore from your last `oak export` |
| `OAK-WORKSPACE-MIGRATE` on every command but `workspace status` and `export` | The workspace is at an older format this build knows | Run `oak workspace migrate` once, or `oak export` to copy it as it is |
| `OAK-WORKSPACE-FORMAT` on every command, `export` included | The manifest names a format this build does not read: a newer build wrote it | Use the build that wrote it, and export from there; downgrade is not supported |
| `OAK-RUNNER-REPLAY` on every dispatch | The consumed-nonce ledger `$OAK_RUNNER_HOME/consumed-nonces.json` (a map of each nonce to its lease's expiry; a list written by `0.9` still reads) is corrupt; it deliberately refuses rather than reading as empty | Inspect the file. Remove it only if you accept that previously burned nonces become replayable — for the local fixture that is usually acceptable; record the decision |
| `OAK-RUNNER-CONFIG` naming `OAK_RUNNER_HEARTBEAT_SECONDS` or `OAK_RUNNER_DISPATCH_RETENTION_DAYS` | The value is not a number in range (0 to 3600 seconds; 0 to 3650 days) | Fix the variable. `0` switches heartbeats off, or keeps every processed dispatch |
| `OAK-RUNNER-REVOCATION` on every dispatch | The mailbox's `revocations/manifest.json` is missing, the notice set does not match it, or the runner's recorded sequence is ahead of it | Re-publish the revocation state from the control plane (`oak revoke-approval`, or a fresh dispatch establishes an empty manifest). Do not hand-delete notices — the mismatch is the protection working |
| `OAK-EXPECTED-VERSION` | Someone else advanced the case | Re-read the case and retry with the current version. This is a normal concurrency refusal, not a fault |
| `OAK-IDEMPOTENCY-CONFLICT` | An idempotency key was reused with different input | Use a new key, or send the original input |
| `429 OAK-RATE-LIMIT-ADDRESS` or `OAK-RATE-LIMIT-TENANT` | More requests in a minute than the limit admits from one address or one tenant; everything on this machine shares one address | Wait the `Retry-After` seconds; raise `OAK_REQUESTS_PER_MINUTE_PER_ADDRESS` or `OAK_REQUESTS_PER_MINUTE_PER_TENANT`, or set one to `0` |
| `429 OAK-OPERATION-QUOTA` | The tenant has `OAK_OPERATIONS_PER_TENANT` operations queued or running | Check that `oak-worker` is running and draining them; cancel one; or raise the value |
| `429 OAK-MODEL-BUDGET` (`OAK-MODEL-BUDGET` on the CLI) | The case has recorded `OAK_MODEL_REQUESTS_PER_CASE_PER_DAY` billable model requests today | Use the deterministic mode, wait for 00:00 UTC, or raise the value |
| `OAK-LIMIT-CONFIG` at start, or from a command | One of the four limit variables is not a whole number from 0 to 1000000 | Fix the value; `0` switches that limit off |
| `OAK-REMOTE-UNSUPPORTED` | A local-only command was run with `--server` | Signing, approval (including `approve architecture`), dispatch, ingest, observation (`oak observe`), keys, model-provider configuration, extensions, policy, rendering and validation are local-only by design; the full list is in [interfaces.md](interfaces.md). `oak architecture` works in remote mode |
| `OAK-REMOTE-UNAVAILABLE` | The control plane is unreachable | Check the URL and that `oak-api` is up |
| Server refuses to start | `OAK_DATABASE_URL` unset (`oak-worker`, `oak-db-migrate`, `oak-mcp`), or a non-loopback bind without `OAK_ALLOW_NON_LOOPBACK` | See [configuration.md](configuration.md) |
| `oak-api` runs but every design-case or operation call under `/v1` returns 503 `OAK-DATABASE-UNCONFIGURED` | `OAK_DATABASE_URL` unset — `oak-api` and `oak serve` start regardless, and say so at startup | Set it to the PostgreSQL database, then restart; `curl /readyz` returns 503 in exactly this case |
| Artifact reads fail after a restore | The artifact root was not restored with the database | See [Restore](#restore) |
| Dependency install fails on macOS | An Intel or Rosetta interpreter | See [platforms.md](platforms.md#prerequisites) |
| `OAK-APPROVAL-ARCHITECTURE` from `oak approve apply` | No current architecture approval for this plan: never recorded, expired, revoked, or the plan was recompiled | Run `oak approve architecture` first, then `oak approve apply` |
| `OAK-RUNNER-FOREIGN` on apply, rollback or destroy | A container this case does not own already has the derived name | Inspect it with `docker inspect <name>`. The runner never adopts or removes it; remove or rename it yourself if it is yours to remove, then re-dispatch |
| `OAK-RUNNER-SMOKE-TEST` | A started container exited, became unhealthy, or was not running within 15 s; on a fixture-only profile, a container was not `created` | Read the completion's `test_result` evidence. The containers that apply created have been removed, unless the completion says `manual_recovery_required` |

---

## Export

`oak export` writes a portable, digest-verified tree; `oak import` reads one back.

```bash
oak export --output ./case-export
oak validate export ./case-export
```

`oak validate` needs no server and no database, so it works in CI and on a machine that
has never run OAK. Read the scope of what it checks in [interfaces.md](interfaces.md):
a detached bundle's semantic manifest and, since Tier 3's Batch A, its assurance plan
are bound by digest, and a bundle written before that edge reports its assurance plan
`unbound`.

**What a restored history says.** Importing a server export onto a server
(`oak --server import`, `POST /v1/design-cases:import`) restores the case with its
history as written: the file adapter checks every digest, the hash chain and the tenant,
not who acted, so the actors and interface origins of the restored events are the
export's claims, as good as the export's custody. The restore then records one
`workspace_restored` event under the importing command's actor, naming the export's
manifest, its digest and the number of events restored (`oak.community/restored_from`
on the case): read the history from that event backwards as the export's word, and from
it forwards as the server's own. Importing the same export again is answered as a
duplicate of that restore; an export of another state of the case is refused. A local
workspace's export is not restored on a server at all; it is re-created from its brief
and confirmed answers under the importing actor (`workspace_imported`).

---

## Securing a local deployment

- **Compose ships hardened; overrides can silently undo it.** Every service runs with
  `cap_drop: [ALL]`, `no-new-privileges`, a read-only root filesystem where the image
  tolerates one, and memory/CPU ceilings (postgres adds back exactly the six ownership
  and identity capabilities its entrypoint needs). A `compose.override.yaml` that
  redefines a service replaces these keys — re-state them in the override if you add one.
- **Keep the bind on loopback.** `OAK_ALLOW_NON_LOOPBACK` exists for containers on an
  internal network, and Compose uses it because the containers publish only to
  `127.0.0.1` on the host. Setting it on a host interface publishes an unauthenticated
  control plane. The actor and tenant are headers; anyone who can reach the port can
  claim any actor. What the API does defend against is a web page: it refuses any request
  other than `/healthz` and `/readyz` whose `Host` is not a loopback name or an exact
  `OAK_ALLOWED_HOSTS` entry, and any
  request whose `Origin` or `Sec-Fetch-Site` header comes from another site
  (`OAK-HOST-DENIED`, `OAK-ORIGIN-DENIED`). If you acknowledge a non-loopback bind, list
  the names clients will use in `OAK_ALLOWED_HOSTS`; the server warns when it is empty.
- **Protect `~/.oak/trust`.** It holds Ed25519 private keys, created `0600`. It is not in
  your database backup. Anyone who reads it can sign plans and approvals as you.
- **Give the runner its own anchors.** The single-host walkthrough points
  `OAK_RUNNER_TRUST_ANCHORS` at the same directory that holds the control plane's private
  keys. Copy only the `*.identity.json` files to a separate directory as soon as the
  runner is not on the same machine (`RR-012`).
- **Enroll each runner once.** `oak ingest` believes a runner message only when an enrolled
  runner signed it (`OAK-INGEST-RUNNER-UNENROLLED` until one is): print the runner's public
  identity with `oak-runner identity`, using its own `OAK_RUNNER_HOME`, and pin it with
  `oak keys enroll-runner --identity <file>`. Each enrolled runner is a file under the trust
  directory's `runners/`; delete that file to withdraw one. After upgrading from `0.9.0`,
  enroll before the first ingest.
- **Rotate by regenerating and re-pinning.** There is no rotation command. Generate new
  keys into a fresh trust directory, distribute the new `*.identity.json` anchors, and
  re-sign anything that must remain verifiable. Old signatures verify only against old
  anchors, so keep the retired public identities as long as you need to read old
  envelopes.
- **Treat `OAK_DATABASE_URL` as a secret.** The Compose default embeds a password.
- **`oak keys show` only reads.** It prints the three identities, and refuses with
  `OAK-KEYS-UNINITIALIZED` when none exists (`OAK-SIGNING-KEY-MISSING` when one of the
  three is gone), so it cannot recreate what an uninstall deleted. Only `oak keys init`
  creates keys (`RR-018`, closed: before this change `show` created missing keys).

---

## Configure a model provider

Nothing in OAK contacts a model until a request asks for one, and the configuration
is machine-local: keys are read from a hidden prompt or standard input, stored in the OS
keychain or an owner-only file, and never accepted as a command argument or returned by any
interface.

On a host, `oak models set-key` (which verifies the token with Hugging Face by default) and
`oak models discover` are the whole procedure for Online AI; `oak models select local
<model_id>` pins the model Local AI calls. Under Compose the state belongs to the `api`
service, so configure it there:

```bash
docker compose exec -T api oak models token      # the capability token the API minted
printf '%s\n' "$YOUR_TOKEN" | docker compose exec -T api oak models set-key --stdin
docker compose exec -T api oak models discover   # the preferred pair and every callable pair
docker compose exec -T api oak models select huggingface Qwen/Qwen3.8-27B --provider deepinfra  # optional pin
docker compose exec -T api oak models select local qwen3:8b                                  # Local AI
docker compose exec -T api oak models status     # the verdict with its age; what each mode would call
```

**Local AI cannot work under Compose.** Its endpoint must be a loopback address
(`OAK_MODEL_ENDPOINT_LOCAL`), and inside the `api` container loopback is the container
itself, not the host, so a model server on your own machine is unreachable from the stack
and a Local AI interpretation fails and records nothing. The `select local` line above
only records a choice.
To use Local AI, run the CLI from a source install on the machine that runs the model
server.

The web workspace asks for that token once, on the Models screen, and keeps it for the
session only. The token is minted per API process: restarting `api` invalidates it, which is
deliberate — it is a capability, not a password, and `oak models token` reprints the current
one. The `/v1/models` routes refuse without it (`OAK-MODEL-TOKEN-REQUIRED`).

Nothing is called unless a request asks: `oak design --interpreter online` sends the brief
to Hugging Face and the provider it routes to (`RR-039`), `--interpreter local` to the loopback
server, and the default — no flag, any brief — contacts nothing. A stored token's verdict is
shown with its age by `oak models status` and is stale after a day (`RR-042`); `oak models
verify` re-checks it.

## Installed architectures

A selected architecture can be installed on the runner's local Docker daemon, from a
target profile that acknowledges it. [signed-runner.md](signed-runner.md#installing-testing-and-observing)
has the whole journey. The commands an operator meets:

| Command | What it does | Where it runs |
|---|---|---|
| `oak architecture` | Prints the selected architecture and, once it is compiled for a mutation profile, the image each node would run and which of the two approvals exist. Writes nothing | Local and remote |
| `oak approve architecture` | Records the approval of the architecture as compiled. Installs nothing, and `oak approve apply` is refused without it (`OAK-APPROVAL-ARCHITECTURE`) | Local only |
| `oak observe` | Records an `observation_record` from the runner completions that ingest accepted, and moves the case to `observing`. Proposes and dispatches nothing | Local only |

The browser's **Take it** sheet downloads the same document as `oak architecture`, as
YAML or JSON, through the read-only `GET /v1/design-cases/{case_id}/architecture`.

An installation is one container per node of the selected candidate, labelled
`oak.fixture=true`, `oak.case=<case id>` and `oak.node=<node id>`. On a profile that
acknowledges `isolated-non-production-hardened-start`, those containers keep running until
they are removed (`RR-043`). Remove them the signed way, running the runner with its
environment as in [signed-runner.md](signed-runner.md):

```bash
oak approve rollback
oak dispatch rollback
oak-runner run-once
oak ingest                 # believes only an enrolled runner (`oak keys enroll-runner`)
```

The runner removes only containers that carry the case's labels, and proves each is gone.
If it cannot — no current plan or approval, a lost trust directory, a journal that needs
manual recovery — remove them by hand:

```bash
docker ps --all --filter label=oak.fixture=true     # or label=oak.case=<case id>
docker rm --force --volumes <name>
```

A removal by hand produces no runner completion, so `oak observe` cannot see it.

## Uninstall

Removing OAK means four separate things. Doing only the first leaves your design cases,
your private keys and several gigabytes of cache behind.

```bash
# 1. Containers, volumes (your data), networks and images
docker compose down --volumes --remove-orphans
docker volume rm -f oak-community_oak-postgres-data oak-community_oak-artifacts 2>/dev/null || true
# Provider keys, if you configured a model. This is the copy the api container reads.
docker volume rm -f oak-community_oak-model-state 2>/dev/null || true
# Compose names its images `<project>-<service>`; a hand-built or release-workflow
# image uses `<org>/<name>`. Both exist in practice, so remove both.
docker image rm -f $(docker image ls -q 'oak-community-*') 2>/dev/null || true
docker image rm -f $(docker image ls -q 'oak-community/*') 2>/dev/null || true
docker rm --force --volumes $(docker ps -aq --filter "label=oak.fixture=true") 2>/dev/null || true

# 2. Home-directory state: PRIVATE KEYS, provider keys, mailbox, extensions, runner journals
#    (~/.oak/credentials holds any provider key the CLI stored in the file backend)
rm -rf ~/.oak
# A key stored in the OS keychain is not under ~/.oak. Remove those first, per family:
#   oak models remove-key <family>

# 3. Any workspaces you created (each holds a .oak directory)
#    You chose these paths; OAK does not track them.
rm -rf /path/to/your/workspace

# 4. The source checkout and its caches, if you built from source
make clean-all
```

`~/.oak` contains Ed25519 **private keys**. Delete it deliberately, and only after
exporting anything you still want.

Global toolchain caches are shared with other projects and are **not** OAK's to remove —
`~/.cache/uv`, the pnpm store, and the Playwright browser cache stay unless you clear
them yourself.

The same applies to the third-party images OAK causes Docker to pull: `postgres:17.6-alpine`,
`python:3.13.12-slim`, `node:24.18.0-alpine`, `nginxinc/nginx-unprivileged:1.30.6-trixie`,
`ghcr.io/astral-sh/uv:0.10.8` (a build stage of the API image),
`docker.io/rancher/mirrored-pause:3.10` (pinned by digest; pulled when `oak-runner` installs
from a shipped mutation profile, and by the Docker-gated end-to-end tests), and
`aquasec/trivy` if you ran `make scan-images`. Neither the commands above nor
`scripts/check_clean_machine.py` touches or reports them, because they are shared Docker
state rather than OAK's. Remove them with `docker image rm` if you want the disk back.

Then confirm the machine is actually clean:

```bash
python scripts/check_clean_machine.py
```

It reports any surviving `~/.oak` tree, OAK Docker volume, image, network or labelled
fixture container, and any in-repo build artifact — so removal is evidence rather than a
claim. It is read-only and deletes nothing.
