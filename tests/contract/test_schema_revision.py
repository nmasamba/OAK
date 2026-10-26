# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-011: readiness compares the database with the revision this binary expects.

`SCHEMA_REVISION` is that expectation. It must be the head of the migrations that ship
with it, or every deployment would read as not ready (or, after a forgotten bump, ready
against a schema the binary's queries were not written for).
"""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from oak.adapters.persistence.postgresql import SCHEMA_REVISION
from oak.interfaces.migrations import canonical_migration_directory


def test_the_readiness_revision_is_the_single_head_of_the_shipped_migrations() -> None:
    config = Config()
    config.set_main_option("script_location", str(canonical_migration_directory()))

    assert ScriptDirectory.from_config(config).get_heads() == [SCHEMA_REVISION]
