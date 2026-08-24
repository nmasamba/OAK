# SPDX-License-Identifier: Apache-2.0
"""Installed-wheel entrypoint for the forward-only metadata migration set."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def canonical_migration_directory() -> Path:
    candidates = (
        Path(__file__).resolve().parents[1] / "migrations",
        Path(__file__).resolve().parents[3] / "migrations",
    )
    for candidate in candidates:
        if (candidate / "env.py").is_file() and (candidate / "versions").is_dir():
            return candidate
    raise RuntimeError("OAK database migrations are not installed")


def main() -> None:
    database_url = os.getenv("OAK_DATABASE_URL")
    if not database_url:
        raise SystemExit("OAK-DATABASE-CONFIG: OAK_DATABASE_URL is required")
    config = Config()
    config.set_main_option("script_location", str(canonical_migration_directory()))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    try:
        command.upgrade(config, "head")
    # An unreachable or misconfigured database used to produce a full SQLAlchemy
    # traceback on the operator's terminal, disclosing the connection host, port and
    # user. The exception type is enough to act on; the URL is a secret.
    except Exception as error:
        raise SystemExit(
            f"OAK-DATABASE-MIGRATION: the metadata migration did not complete "
            f"({type(error).__name__}). Check that OAK_DATABASE_URL points at a "
            f"reachable database and that the role may create schema objects."
        ) from error


if __name__ == "__main__":  # pragma: no cover
    main()
