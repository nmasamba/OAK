# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-024 (RR-015, review L1): a failing start is logged by type, never by message.

A database URL that does not parse made `oak-api`, `oak-worker` and `oak-mcp` die with a
Python traceback whose message quoted part of the password. Each must now end with an
allowlisted JSON line instead.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".venv" / "bin"
SENTINEL = "oaksentinelpw"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.mark.parametrize("entrypoint", ["oak-api", "oak-worker", "oak-mcp"])
def test_a_database_url_that_does_not_parse_never_reaches_stderr(
    tmp_path: Path, entrypoint: str
) -> None:
    environment = {
        **{key: value for key, value in os.environ.items() if not key.startswith("OAK_")},
        "OAK_DATABASE_URL": f"postgresql+psycopg://oak:Tr0ub@4dor:{SENTINEL}@127.0.0.1:5432/oak",
        "OAK_PORT": str(_free_port()),
        "OAK_CREDENTIALS_DIRECTORY": str(tmp_path / "credentials"),
        "OAK_MODELS_DIRECTORY": str(tmp_path / "models"),
        "OAK_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
    }
    result = subprocess.run(
        [str(BIN / entrypoint)],
        input=b"",
        capture_output=True,
        env=environment,
        cwd=tmp_path,
        timeout=60,
        check=False,
    )

    stderr = result.stderr.decode("utf-8", "replace")
    assert result.returncode != 0
    assert SENTINEL not in stderr and SENTINEL not in result.stdout.decode("utf-8", "replace")
    assert "Traceback" not in stderr
    events = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
    assert any(event["event"] == "startup_failed" for event in events), stderr
