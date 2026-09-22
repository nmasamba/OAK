# SPDX-License-Identifier: Apache-2.0
"""OAK-S10-007: the remote CLI forwards the chosen mode, and only a chosen one."""

from __future__ import annotations

from typing import Any

import pytest

from oak.interfaces.cli.remote import RemoteClient


@pytest.mark.parametrize(
    "interpreter,expected_path,sends_token",
    [
        ("deterministic", "/v1/design-cases/design-case.x:interpret", False),
        ("online", "/v1/design-cases/design-case.x:interpret?interpreter=online", True),
        ("local", "/v1/design-cases/design-case.x:interpret?interpreter=local", True),
    ],
)
def test_interpret_forwards_the_mode_as_the_query_the_api_reads(
    monkeypatch: pytest.MonkeyPatch, interpreter: str, expected_path: str, sends_token: bool
) -> None:
    seen: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(self: RemoteClient, method: str, path: str, **options: Any) -> dict[str, Any]:
        seen.append((method, path, options))
        return {"case": {"id": "design-case.x", "version": "0.1.1"}}

    monkeypatch.setattr(RemoteClient, "_request", fake_request)
    client = RemoteClient("http://127.0.0.1:9", model_token="token-0123456789abcdef")

    client.interpret(
        "design-case.x",
        expected_version="0.1.0",
        idempotency_key="remote-interpret-0123456789",
        interpreter=interpreter,
    )

    assert seen == [
        (
            "POST",
            expected_path,
            {
                "idempotency_key": "remote-interpret-0123456789",
                "expected_version": "0.1.0",
                "model_token": sends_token,
            },
        )
    ]
