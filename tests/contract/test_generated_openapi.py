# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-006 generated contract tests."""

import json
from pathlib import Path

from oak.interfaces.api.app import app

ROOT = Path(__file__).resolve().parents[2]


def test_committed_openapi_matches_application() -> None:
    committed = json.loads((ROOT / "openapi" / "oak.openapi.json").read_text(encoding="utf-8"))

    assert committed == app.openapi()
    assert committed["openapi"].startswith("3.1")
    assert set(committed["paths"]) == {"/healthz", "/readyz", "/version"}
