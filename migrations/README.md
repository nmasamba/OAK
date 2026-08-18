<!-- SPDX-License-Identifier: Apache-2.0 -->

# PostgreSQL migrations

Migrations are forward-only and apply to the Community control-plane metadata database.
Set `OAK_DATABASE_URL` to an explicit PostgreSQL SQLAlchemy URL and run:

```bash
oak-db-migrate
```

`0001_sprint3_baseline` is the first PostgreSQL schema. It upgrades an empty database; there
is no invented prior PostgreSQL history. Database rollback is restore-forward: restore a
backup into a clean database, then apply migrations up to the compatible revision. The
baseline intentionally raises on `downgrade` rather than issuing destructive DDL.

Canonical JSON Schema evolution is separate from these storage migrations. A database
column change does not change canonical object meaning.

## Backup and restore-forward

Before a future migration, stop `oak-api` and `oak-worker`, record the current revision with
`alembic current`, and create a PostgreSQL-format backup with the host's reviewed `pg_dump`
procedure. Keep the backup outside the repository and verify it can be listed/restored before
applying the migration.

Recovery creates a clean database, restores that backup with the matching PostgreSQL tools,
sets `OAK_DATABASE_URL` to the restored database, and runs `oak-db-migrate`. Never run a
source-controlled destructive downgrade: the baseline `downgrade()` raises deliberately.
Canonical DesignCase export/import is an additional portability path and does not replace a
database backup for operation leases, consumer receipts, or projection positions.
