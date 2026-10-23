# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-011 (RR-016): `/readyz` is not ready at another schema revision.

A database behind this binary (a skipped `oak-db-migrate`) or ahead of it (an older binary
started after a newer one migrated) answers `SELECT 1`, so readiness went green and the
mismatch surfaced as opaque query errors. Each case here gets its own PostgreSQL schema,
reached through `search_path`, so the shared test database's own revision is never touched.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from oak.adapters.persistence.postgresql import (
    SCHEMA_REVISION,
    PostgreSQLReadinessProbe,
    create_postgresql_engine,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("OAK_TEST_DATABASE_URL")
    if not url:
        pytest.skip("OAK_TEST_DATABASE_URL is required for the readiness revision tests")
    return url


@pytest.fixture
def probe_at(database_url: str) -> Iterator:
    """A probe whose database holds `revisions` in its `alembic_version`, or no table."""

    admin = create_postgresql_engine(database_url)
    schemas: list[str] = []
    engines = []

    def build(revisions: list[str] | None) -> PostgreSQLReadinessProbe:
        schema = f"readiness_{uuid.uuid4().hex[:12]}"
        schemas.append(schema)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            if revisions is not None:
                connection.execute(
                    text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32))')
                )
                for revision in revisions:
                    connection.execute(
                        text(f'INSERT INTO "{schema}".alembic_version VALUES (:revision)'),
                        {"revision": revision},
                    )
        engine = create_engine(database_url, connect_args={"options": f"-csearch_path={schema}"})
        engines.append(engine)
        return PostgreSQLReadinessProbe(engine)

    yield build
    for engine in engines:
        engine.dispose()
    with admin.begin() as connection:
        for schema in schemas:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    admin.dispose()


def test_the_migrated_test_database_is_ready(database_url: str) -> None:
    engine = create_postgresql_engine(database_url)
    try:
        assert PostgreSQLReadinessProbe(engine).is_ready() is True
    finally:
        engine.dispose()


def test_this_binarys_revision_is_ready(probe_at) -> None:
    assert probe_at([SCHEMA_REVISION]).is_ready() is True


@pytest.mark.parametrize(
    "revisions",
    [
        pytest.param(["0000_an_older_revision"], id="behind"),
        pytest.param(["0002_a_newer_revision"], id="ahead"),
        pytest.param([], id="no-revision-recorded"),
        pytest.param([SCHEMA_REVISION, "0002_a_newer_revision"], id="two-heads"),
        pytest.param(None, id="never-migrated"),
    ],
)
def test_any_other_revision_is_not_ready(probe_at, revisions: list[str] | None) -> None:
    assert probe_at(revisions).is_ready() is False
