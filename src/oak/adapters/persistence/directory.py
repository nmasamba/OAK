# SPDX-License-Identifier: Apache-2.0
"""Tenant-scoped PostgreSQL design-case directory queries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, and_, select

from oak.adapters.persistence.models import design_case_heads, design_case_versions


class PostgreSQLCaseDirectory:
    """Read current design-case heads for one tenant/environment scope.

    This is a read-only query surface over the authoritative head and version
    tables; it grants no transition authority and exposes only summary fields.
    """

    def __init__(self, engine: Engine, *, tenant_id: str, environment_id: str = "local") -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgreSQLCaseDirectory requires a PostgreSQL engine")
        self._engine = engine
        self._tenant_id = tenant_id
        self._environment_id = environment_id

    def list_cases(self) -> tuple[dict[str, Any], ...]:
        query = (
            select(
                design_case_heads.c.case_id,
                design_case_heads.c.workspace_id,
                design_case_heads.c.current_version,
                design_case_heads.c.current_digest,
                design_case_heads.c.updated_at,
                design_case_versions.c.status,
                design_case_versions.c.document["title"].astext.label("title"),
            )
            .select_from(
                design_case_heads.join(
                    design_case_versions,
                    and_(
                        design_case_versions.c.tenant_id == design_case_heads.c.tenant_id,
                        design_case_versions.c.environment_id == design_case_heads.c.environment_id,
                        design_case_versions.c.workspace_id == design_case_heads.c.workspace_id,
                        design_case_versions.c.case_id == design_case_heads.c.case_id,
                        design_case_versions.c.case_version == design_case_heads.c.current_version,
                    ),
                )
            )
            .where(
                and_(
                    design_case_heads.c.tenant_id == self._tenant_id,
                    design_case_heads.c.environment_id == self._environment_id,
                )
            )
            .order_by(design_case_heads.c.case_id)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return tuple(
            {
                "id": row["case_id"],
                "workspace_id": row["workspace_id"],
                "version": row["current_version"],
                "digest": row["current_digest"],
                "status": row["status"],
                "title": row["title"],
                "updated_at": _format_time(row["updated_at"]),
            }
            for row in rows
        )


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
