# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-009: the API tests use httpx's ASGI transport, never Starlette's test client.

Starlette deprecated its test client for use with `httpx` (a `StarletteDeprecationWarning`
on every run), and a deprecated path is the first one an upgrade removes. The synchronous
tests use `tests/asgi_support.ASGIClient`; the asynchronous ones use the transport directly.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_DEPRECATED_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:starlette|fastapi)\.testclient\b", flags=re.MULTILINE
)


def test_no_test_imports_the_deprecated_starlette_test_client() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "tests").rglob("*.py"))
        if _DEPRECATED_IMPORT.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, offenders
