# SPDX-License-Identifier: Apache-2.0
"""A synchronous client for the API tests, over httpx's own ASGI transport.

Starlette deprecated using its test client (`starlette.testclient`, which
`fastapi.testclient` re-exports) with `httpx`. The asynchronous suites already drive the
app through `httpx.ASGITransport`; this gives the synchronous ones the same transport.
Each request runs to completion in its own event loop, which the app allows because it
keeps no state in a loop and declares no lifespan.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import anyio
import httpx


class ASGIClient:
    """The subset of the old test client these tests use: one call per HTTP method.

    Redirects are followed and an exception the app does not handle is raised in the test,
    as the Starlette client did; ``app`` is the application under test.
    """

    def __init__(self, app: Any, *, base_url: str = "http://127.0.0.1") -> None:
        self.app = app
        self._base_url = base_url

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url=self._base_url,
                follow_redirects=True,
            ) as client:
                return await client.request(method, url, **kwargs)

        return anyio.run(send)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def __enter__(self) -> ASGIClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None
