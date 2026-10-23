# SPDX-License-Identifier: Apache-2.0
"""Schema access for the runner without control-plane composition imports.

The runner validates only against the schemas installed with it. `OAK_SCHEMA_DIRECTORY`
is a control-plane setting and is deliberately not read here: the registry built from
this directory decides whether a target profile, envelope, lease, approval or signature
is well formed, so whoever could set the variable in the runner's environment could
substitute the rules the runner verifies against (RR-033).
"""

from __future__ import annotations

from pathlib import Path

from oak.contracts import SchemaRegistry


def canonical_schema_directory() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    for candidate in (package_root / "canonical_schemas", package_root.parents[1] / "schemas"):
        if (candidate / "common.schema.json").is_file():
            return candidate
    raise RuntimeError("canonical OAK schemas are not installed")


def load_registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(canonical_schema_directory())
