# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-042: the consent text is readable over REST, so the web can show it beside a
native plan; reading it records nothing, and a server without it says so (ADR-0019)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from oak.bootstrap import load_native_consent
from oak.domain.runner_adapters import native_consent_reference
from oak.interfaces.api.app import create_app
from tests.mcp_support import NOW, build_server

pytestmark = pytest.mark.integration


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_the_consent_text_and_its_digest_are_served(tmp_path: Path) -> None:
    _server, control_plane, _store = build_server(tmp_path)
    transport = httpx.ASGITransport(app=create_app(control_plane=control_plane, clock=lambda: NOW))

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as rest:
        answer = await rest.get("/v1/native-consent")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["consent"] == load_native_consent()
    assert body["consent_ref"] == native_consent_reference(load_native_consent())


@pytest.mark.anyio
async def test_a_server_without_the_consent_text_says_so(tmp_path: Path) -> None:
    _server, control_plane, _store = build_server(tmp_path)
    control_plane._native_consent = None
    transport = httpx.ASGITransport(app=create_app(control_plane=control_plane, clock=lambda: NOW))

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as rest:
        answer = await rest.get("/v1/native-consent")

    assert answer.status_code == 503, answer.text
    assert answer.json()["code"] == "OAK-NATIVE-CONSENT"
