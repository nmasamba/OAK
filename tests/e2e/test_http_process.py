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


def test_readiness_is_not_ready_without_a_configured_database() -> None:
    """A readiness endpoint must not report ready for a service that cannot serve.

    `create_system_information_service` built an *empty* probe tuple when
    `OAK_DATABASE_URL` was unset, and `all(())` is `True` — so `/readyz` answered
    "ready" on an `oak-api` with no database at all, while every `/v1` request returned
    a 500. `/readyz` is what an orchestrator routes traffic on, so a vacuous yes is
    worse than no endpoint.
    """

    port = _available_port()
    environment = {key: value for key, value in os.environ.items() if key != "OAK_DATABASE_URL"}
    environment.update({"OAK_PORT": str(port), "OAK_HOST": "127.0.0.1"})
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
        version: httpx.Response | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(f"oak-api exited early: stdout={stdout!r} stderr={stderr!r}")
            try:
                version = httpx.get(f"http://127.0.0.1:{port}/version", timeout=0.5)
                break
            except httpx.TransportError:
                time.sleep(0.05)

        # The process still starts and still reports its identity — that is deliberate,
        # and the README documents it.
        assert version is not None
        assert version.status_code == 200

        readiness = httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=2)
        assert readiness.status_code == 503, readiness.text
    finally:
        process.terminate()
        process.wait(timeout=5)
