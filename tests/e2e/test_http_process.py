# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-006 real loopback-process smoke test."""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_oak_api_serves_version_on_loopback() -> None:
    port = _available_port()
    environment = {**os.environ, "OAK_PORT": str(port), "OAK_HOST": "127.0.0.1"}
    process = subprocess.Popen(
        ["oak-api"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        response: httpx.Response | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(f"oak-api exited early: stdout={stdout!r} stderr={stderr!r}")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/version", timeout=0.5)
                break
            except httpx.TransportError:
                time.sleep(0.05)
        assert response is not None
        assert response.status_code == 200
        assert response.json()["version"] == (ROOT / "VERSION").read_text().strip()
    finally:
        process.terminate()
        process.wait(timeout=5)
