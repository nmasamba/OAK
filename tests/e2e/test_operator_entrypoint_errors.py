# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: operator entrypoints fail with a stable code, never a traceback.

`oak-runner` and `oak-db-migrate` are run by a person at a terminal, usually while
something is already wrong. Both used to answer a misconfiguration with a raw Python
traceback: the runner because `main` caught only `OAKError` while the target profile was
loaded outside any guard, and `oak-db-migrate` because nothing wrapped `alembic upgrade`.

A traceback is a worse answer than a code — it is unactionable, it discloses absolute
paths and connection details, and the CLI contract promises `CODE: message` on stderr.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OAK_RUNNER = ROOT / ".venv" / "bin" / "oak-runner"
OAK_DB_MIGRATE = ROOT / ".venv" / "bin" / "oak-db-migrate"

pytestmark = pytest.mark.e2e


def _run(executable: Path, *arguments: str, **environment: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*", **environment},
    )


@pytest.fixture
def runner_environment(tmp_path: Path) -> dict[str, str]:
    mailbox = tmp_path / "mailbox"
    anchors = tmp_path / "anchors"
    mailbox.mkdir()
    anchors.mkdir()
    return {
        "OAK_RUNNER_MAILBOX": str(mailbox),
        "OAK_RUNNER_TRUST_ANCHORS": str(anchors),
        "OAK_RUNNER_HOME": str(tmp_path / "home"),
    }


def test_a_missing_target_profile_is_a_stable_runner_code(
    runner_environment: dict[str, str], tmp_path: Path
) -> None:
    result = _run(
        OAK_RUNNER,
        "run-once",
        **runner_environment,
        OAK_RUNNER_TARGET_PROFILE=str(tmp_path / "absent.yaml"),
    )

    assert result.returncode != 0
    assert result.stderr.startswith("OAK-RUNNER-CONFIG:")
    assert "Traceback" not in result.stderr


def test_a_malformed_target_profile_is_a_stable_runner_code(
    runner_environment: dict[str, str], tmp_path: Path
) -> None:
    """YAML parse errors are not `ValueError`, which is how this escaped before."""

    profile = tmp_path / "broken.yaml"
    profile.write_text("not: [a valid\n", encoding="utf-8")

    result = _run(
        OAK_RUNNER, "run-once", **runner_environment, OAK_RUNNER_TARGET_PROFILE=str(profile)
    )

    assert result.returncode != 0
    assert result.stderr.startswith("OAK-RUNNER-CONFIG:")
    assert "Traceback" not in result.stderr
    assert "yaml" not in result.stderr.lower()


def test_a_schema_invalid_target_profile_is_a_stable_runner_code(
    runner_environment: dict[str, str], tmp_path: Path
) -> None:
    profile = tmp_path / "wrong-shape.yaml"
    profile.write_text("id: target.nope\n", encoding="utf-8")

    result = _run(
        OAK_RUNNER, "run-once", **runner_environment, OAK_RUNNER_TARGET_PROFILE=str(profile)
    )

    assert result.returncode != 0
    assert result.stderr.startswith("OAK-RUNNER-CONFIG:")
    assert "Traceback" not in result.stderr


def test_an_unreachable_database_is_a_stable_migration_code_without_the_url() -> None:
    """The connection URL carries a password; a traceback used to print its host and user."""

    result = _run(
        OAK_DB_MIGRATE,
        OAK_DATABASE_URL="postgresql+psycopg://oak:hunter2@127.0.0.1:1/oak",
    )

    assert result.returncode != 0
    assert "OAK-DATABASE-MIGRATION:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "hunter2" not in result.stderr
    assert "127.0.0.1" not in result.stderr


def test_a_missing_database_url_is_refused_before_any_work() -> None:
    result = _run(OAK_DB_MIGRATE, OAK_DATABASE_URL="")

    assert result.returncode != 0
    assert "OAK-DATABASE-CONFIG:" in result.stderr
    assert "Traceback" not in result.stderr
