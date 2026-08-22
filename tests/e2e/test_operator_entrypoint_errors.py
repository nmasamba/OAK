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

import json
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


@pytest.mark.parametrize(
    "envelope",
    [
        '{"protocol_version": "0.1.0", "lease": null, "plan": 5}',
        '{"protocol_version": "0.1.0", "lease": 5}',
        '{"protocol_version": "0.1.0", "lease": []}',
        '{"protocol_version": "0.1.0", "lease": {"lease_id": null}}',
        '{"protocol_version": "0.1.0", "lease": {"lease_id": {"nested": 1}}}',
        '{"protocol_version": "9.9.9", "lease": {"lease_id": 12345}}',
        '{"protocol_version": ["0.1.0"]}',
        "{}",
    ],
)
def test_a_hostile_dispatch_envelope_is_denied_not_a_crash(
    runner_environment: dict[str, str], tmp_path: Path, envelope: str
) -> None:
    """The envelope is unverified input; its *shape* cannot be assumed either.

    The correlation id was derived from `envelope["lease"]["lease_id"]` before the
    schema check and outside the try block, so `"lease": null` raised AttributeError
    and killed the runner before it could deny anything — the same crash-instead-of-
    stable-error shape a previous audit found in the remote CLI.
    """

    profile = tmp_path / "target.yaml"
    profile.write_text(
        (ROOT / "examples" / "targets" / "local-fixture.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    dispatch = Path(runner_environment["OAK_RUNNER_MAILBOX"]) / "dispatches" / "d0001"
    dispatch.mkdir(parents=True)
    (dispatch / "envelope.json").write_text(envelope, encoding="utf-8")

    result = _run(
        OAK_RUNNER, "run-once", **runner_environment, OAK_RUNNER_TARGET_PROFILE=str(profile)
    )

    assert "Traceback" not in result.stderr, result.stderr
    assert "AttributeError" not in result.stdout + result.stderr
    # Either denied, or ignored as unreadable — never a crash, and never applied.
    assert result.returncode in {0, 70}, (result.returncode, result.stdout, result.stderr)


@pytest.mark.parametrize(
    "journal",
    ["not json at all\n", '{"sequence": 1, "prev', "\x00\x01\x02\n", "[]\n", '{"a": 1}\n'],
)
def test_a_corrupt_journal_is_reported_not_a_crash(tmp_path: Path, journal: str) -> None:
    """`status` exists to report a damaged journal; it used to die on one.

    `verify_chain` was guarded against `OAKError` only, so a malformed line raised
    `JSONDecodeError` — a `ValueError` — and `entries()` sat outside any guard, so an
    operator inspecting a damaged runner got a traceback rather than the verdict.
    """

    home = tmp_path / "runner-home"
    (home / "journals").mkdir(parents=True)
    (home / "journals" / "d0001.jsonl").write_text(journal, encoding="utf-8")

    result = _run(OAK_RUNNER, "status", OAK_RUNNER_HOME=str(home))

    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    entry = report["journals"][0]
    assert entry["chain"] in {"unreadable", "tampered"}
    assert entry["manual_recovery_required"] is True


def test_a_missing_required_runner_variable_carries_a_stable_code() -> None:
    """The documented diagnostic contract is `CODE: message`, on every entrypoint."""

    result = _run(OAK_RUNNER, "run-once", OAK_RUNNER_MAILBOX="")

    assert result.returncode != 0
    assert result.stderr.startswith("OAK-RUNNER-CONFIG:")
    assert "OAK_RUNNER_MAILBOX" in result.stderr
    assert "Traceback" not in result.stderr
