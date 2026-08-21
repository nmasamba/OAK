<!-- SPDX-License-Identifier: Apache-2.0 -->

# Operations runbook

For the person running OAK Community `0.7.0`: install, configure, observe, back up,
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
evaluation and compilation are durable operations, and without a worker they stay
queued forever with no error.

Verify the release artifacts you downloaded before installing them — see
[release-process.md](release-process.md#verifying-a-release). Remember that OAK
Community artifacts are **unsigned**: checksums prove the bytes match the manifest, not
who produced them.

---

## Configure

Every setting is an environment variable; there is no configuration file.
[configuration.md](configuration.md) is the complete list, and a contract test keeps it
that way.

The four that change a trust boundary rather than a path:

| Variable | Why it matters |
|---|---|
| `OAK_ALLOW_NON_LOOPBACK` | Setting it exposes an unauthenticated service |
| `OAK_DATABASE_URL` | Carries a password in the Compose default |
| `OAK_TRUST_DIRECTORY` | Holds the Ed25519 **private** signing keys |
| `OAK_RUNNER_TRUST_ANCHORS` | Decides which signatures the runner will believe |

One setting deserves attention before you have any data: **`OAK_ARTIFACT_ROOT` defaults
to the relative path `.oak/server-artifacts`**, resolved against whatever directory the
process was started in. Set it to an absolute path now. A backup procedure cannot copy a
directory whose location depends on where someone happened to be standing.

---

## Observe

Be realistic about what is available: OAK Community emits **no application logs and no
metrics**. `oak-api` runs uvicorn with `access_log=False`
(`src/oak/interfaces/api/server.py:36`), and nothing in `src/` configures a logger. What
you have is four endpoints and the database.

| Signal | Where | What it tells you |
|---|---|---|
| Liveness | `GET /healthz` | The process is accepting requests |
| Readiness | `GET /readyz` | The database answered. **It does not check the schema revision** — see [Upgrade](#upgrade) |
| Build identity | `GET /version` | Version and `OAK_COMMIT` |
| Projection lag | `GET /v1/system/outbox-lag` | Pending outbox events and sequence lag for the built-in projection |
| Work in flight | `GET /v1/operations/{id}` | Status, attempts and checkpoint of one durable operation |

```bash
curl --fail --silent http://127.0.0.1:8080/readyz
curl --fail --silent http://127.0.0.1:8080/v1/system/outbox-lag
```

To tell whether the worker is alive, watch `pending_events` on the lag endpoint while a
compile runs: a number that only grows means the worker is not consuming. Container
stdout (`docker compose logs worker`) carries process-level output only.

The absence of logging and metrics is recorded as a limitation, not presented as a
design goal — see `RR-015`.

---

## Back up

OAK keeps state in **two stores that are backed up by different tools**, plus a key
directory that is not in either.

| What | Where | Backed up by |
|---|---|---|
| Metadata: workspaces, case versions, artifact index, audit, operations, outbox | PostgreSQL | `pg_dump` |
| **Artifact bytes** | `$OAK_ARTIFACT_ROOT/sha256/` (Compose volume `oak-community_oak-artifacts`) | A filesystem copy |
| Signing keys and trust anchors | `$OAK_TRUST_DIRECTORY` (default `~/.oak/trust`) | A **separate**, protected copy |
| Outbound dispatch mailbox | `$OAK_DISPATCH_MAILBOX` (default `~/.oak/mailbox`) | A filesystem copy, if leases are in flight |
| Extension quarantine and activations | `$OAK_EXTENSIONS_DIRECTORY` (default `~/.oak/extensions`) | A filesystem copy |
| Runner identity, journal and consumed nonces | `$OAK_RUNNER_HOME` (default `~/.oak/runner`) | A **separate**, protected copy — it holds the runner's own Ed25519 private key |

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
outbox events, consumer receipts, projection positions or approvals, and it does not
carry your keys. It is the portability path, not the recovery path.

---

## Restore

Restore-forward. Never downgrade.

```bash
docker compose down                                       # stop everything
docker volume rm -f oak-community_oak-postgres-data       # start from a clean database
docker volume rm -f oak-community_oak-artifacts
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
artifact that does not resolve. It is read-only, and it detects missing objects, truncated
objects and same-length-different-content substitution.

**Compare the count against what you backed up.** "Verified 0 artifacts" after a restore is
a failed restore, not a clean one, so the tool treats an empty index as a failure and says
so loudly. Pass `--allow-empty` only when you genuinely expect nothing — a fresh install.

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

> **`/readyz` does not check the schema revision.** It confirms the database answered,
> nothing more. Nothing stops you starting a new `oak-api` against a database still at an
> older revision, or an old binary against a newer schema — readiness goes green either
> way and failures surface later as opaque query errors. The Compose
> `depends_on: migrate` guard covers the Compose path only, not a hand-run deployment.
> Recorded as `RR-016`. Step 2 above is the manual substitute.

> If you invoke `alembic` directly rather than `oak-db-migrate`, note that
> `migrations/env.py` reads `OAK_DATABASE_URL` from the environment and **ignores** the
> `sqlalchemy.url` config option. Export the variable.

### A file workspace

There is no file-workspace format migration, and none is planned for `0.7.0`. A
workspace whose manifest carries a `schema_version` this build does not know is refused
with `OAK-WORKSPACE-CORRUPT` — on **every** command, including `export`, so it cannot be
rescued after the fact
(`tests/integration/test_backup_restore.py::test_a_workspace_written_by_an_unknown_format_fails_closed`).

**Therefore: `oak export` before upgrading.** The exported tree is the migration unit.
`0.7.0` does not move any manifest `schema_version`, so upgrading to it needs nothing —
but make exporting first a habit before it does. Recorded as `RR-017`.

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
| `OAK-WORKSPACE-CORRUPT` on every command | Manifest unreadable, or a schema version this build does not know | Run `scripts/verify_deployment.py --workspace`; if the manifest version is foreign, you need the build that wrote it |
| `OAK-EXPECTED-VERSION` | Someone else advanced the case | Re-read the case and retry with the current version. This is a normal concurrency refusal, not a fault |
| `OAK-IDEMPOTENCY-CONFLICT` | An idempotency key was reused with different input | Use a new key, or send the original input |
| `OAK-REMOTE-UNSUPPORTED` | A local-only command was run with `--server` | Signing, approval, dispatch, keys, extensions and policy are local-only by design |
| `OAK-REMOTE-UNAVAILABLE` | The control plane is unreachable | Check the URL and that `oak-api` is up |
| Server refuses to start | `OAK_DATABASE_URL` unset, or a non-loopback bind without `OAK_ALLOW_NON_LOOPBACK` | See [configuration.md](configuration.md) |
| Artifact reads fail after a restore | The artifact root was not restored with the database | See [Restore](#restore) |
| Dependency install fails on macOS | An Intel or Rosetta interpreter | See [platforms.md](platforms.md#prerequisites) |

---

## Export

`oak export` writes a portable, digest-verified tree; `oak import` reads one back.

```bash
oak export --output ./case-export
oak validate export ./case-export
```

`oak validate` needs no server and no database, so it works in CI and on a machine that
has never run OAK. Read the scope of what it checks in [interfaces.md](interfaces.md) —
in particular, a detached bundle's assurance plan and semantic manifest carry no digest
edge into the bundle spine.

---

## Securing a local deployment

- **Keep the bind on loopback.** `OAK_ALLOW_NON_LOOPBACK` exists for containers on an
  internal network, and Compose uses it because the containers publish only to
  `127.0.0.1` on the host. Setting it on a host interface publishes an unauthenticated
  control plane. The actor and tenant are headers; anyone who can reach the port can
  claim any actor.
- **Protect `~/.oak/trust`.** It holds Ed25519 private keys, created `0600`. It is not in
  your database backup. Anyone who reads it can sign plans and approvals as you.
- **Give the runner its own anchors.** The single-host walkthrough points
  `OAK_RUNNER_TRUST_ANCHORS` at the same directory that holds the control plane's private
  keys. Copy only the `*.identity.json` files to a separate directory as soon as the
  runner is not on the same machine (`RR-012`).
- **Rotate by regenerating and re-pinning.** There is no rotation command. Generate new
  keys into a fresh trust directory, distribute the new `*.identity.json` anchors, and
  re-sign anything that must remain verifiable. Old signatures verify only against old
  anchors, so keep the retired public identities as long as you need to read old
  envelopes.
- **Treat `OAK_DATABASE_URL` as a secret.** The Compose default embeds a password.
- **Note that `oak keys show` writes.** It creates the trust directory and three private
  keys if they do not exist, despite reading like a query — so it will recreate exactly
  what you just deleted (`RR-018`).

---

## Uninstall

Removing OAK means four separate things. Doing only the first leaves your design cases,
your private keys and several gigabytes of cache behind.

```bash
# 1. Containers, volumes (your data), networks and images
docker compose down --volumes --remove-orphans
docker volume rm -f oak-community_oak-postgres-data oak-community_oak-artifacts 2>/dev/null || true
# Compose names its images `<project>-<service>`; a hand-built or release-workflow
# image uses `<org>/<name>`. Both exist in practice, so remove both.
docker image rm -f $(docker image ls -q 'oak-community-*') 2>/dev/null || true
docker image rm -f $(docker image ls -q 'oak-community/*') 2>/dev/null || true
docker rm -f $(docker ps -aq --filter "label=oak.fixture=true") 2>/dev/null || true

# 2. Home-directory state: PRIVATE KEYS, mailbox, extensions, runner journals
rm -rf ~/.oak

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

Then confirm the machine is actually clean:

```bash
python scripts/check_clean_machine.py
```

It reports any surviving `~/.oak` tree, OAK Docker volume, image, network or labelled
fixture container, and any in-repo build artifact — so removal is evidence rather than a
claim. It is read-only and deletes nothing.
