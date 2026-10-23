# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-012 and OAK-V1-013: the CLI before 1.0.

`oak keys show` created the trust directory and three private keys as a side effect of a
read (RR-018). The rest are the rough edges the 1.0 review noted without numbering them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()

pytestmark = pytest.mark.integration


def _output(result) -> str:  # type: ignore[no-untyped-def]
    return str(result.output) + str(result.stderr or "")


def _files(directory: Path) -> dict[str, int]:
    return {path.name: path.stat().st_mtime_ns for path in sorted(directory.iterdir())}


@pytest.fixture
def trust(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    directory = tmp_path / "trust"
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(directory))
    return directory


def test_keys_show_reads_and_never_creates_what_init_creates(trust: Path) -> None:
    refused = runner.invoke(cli_app, ["keys", "show"])
    assert refused.exit_code == 2
    assert "OAK-KEYS-UNINITIALIZED" in _output(refused)
    assert not trust.exists(), "a read created the trust directory"

    created = runner.invoke(cli_app, ["keys", "init", "--output", "json"])
    assert created.exit_code == 0, _output(created)
    before = _files(trust)
    shown = runner.invoke(cli_app, ["keys", "show", "--output", "json"])
    assert shown.exit_code == 0, _output(shown)
    assert json.loads(shown.stdout)["identities"] == json.loads(created.stdout)["identities"]
    assert _files(trust) == before

    # An uninstall deletes the directory; reading afterwards must not bring the keys back.
    shutil.rmtree(trust)
    again = runner.invoke(cli_app, ["keys", "show"])
    assert again.exit_code == 2
    assert "OAK-KEYS-UNINITIALIZED" in _output(again)
    assert not trust.exists()


def test_keys_show_names_one_missing_key_and_leaves_it_missing(trust: Path) -> None:
    assert runner.invoke(cli_app, ["keys", "init"]).exit_code == 0
    (trust / "approver.key").unlink()

    shown = runner.invoke(cli_app, ["keys", "show"])

    assert shown.exit_code == 2
    assert "OAK-SIGNING-KEY-MISSING" in _output(shown)
    assert not (trust / "approver.key").exists()
