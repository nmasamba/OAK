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
    command.upgrade(config, "head")


if __name__ == "__main__":  # pragma: no cover
    main()
