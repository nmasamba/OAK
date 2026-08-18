# SPDX-License-Identifier: Apache-2.0
"""Schema access for the runner without control-plane composition imports."""

from __future__ import annotations

import os
from pathlib import Path

from oak.contracts import SchemaRegistry


def canonical_schema_directory() -> Path:
    configured = os.getenv("OAK_SCHEMA_DIRECTORY")
    package_root = Path(__file__).resolve().parents[1]
    candidates = [
        Path(configured) if configured else None,
        package_root / "canonical_schemas",
        package_root.parents[1] / "schemas",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "common.schema.json").is_file():
            return candidate
    raise RuntimeError("canonical OAK schemas are not installed")


def load_registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(canonical_schema_directory())
