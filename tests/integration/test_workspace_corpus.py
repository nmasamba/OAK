# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-029 (RR-017): the `0.9.0` reference workspace, as that release exported it.

`tests/fixtures/workspaces/0.9.0/` is the export of one reference journey run with the
`v0.9.0` tag's own build (`oak init`, `design`, `questions`, `confirm`, `candidates`,
`evaluate`, `select`, `assure`, `plan`, `export`), taken on 2026-10-29 in a detached
worktree. It holds the local tenant, a workspace id derived from a directory name, the
public example brief and what the compiler made of it, and nothing else. This build must
import it, report it at the current format, migrate it as a no-op, run every command on
it and export it again.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from oak.domain.workspace_format import CURRENT_MANIFEST_FORMAT
from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "workspaces" / "0.9.0"
runner = CliRunner()

pytestmark = pytest.mark.integration


def _output(result) -> str:  # type: ignore[no-untyped-def]
    return str(result.output) + str(result.stderr or "")


def _oak(*arguments: str, cwd: Path) -> Any:
    previous = Path.cwd()
    os.chdir(cwd)
    try:
        return runner.invoke(cli_app, list(arguments))
    finally:
        os.chdir(previous)


def test_the_corpus_is_what_it_claims_to_be() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_bytes())
    assert manifest["schema_version"] == "0.4.0"
    assert manifest["tenant_id"] == "local"
    assert manifest["id"].startswith("workspace.oak-corpus-")
    assert manifest["version"] == 8 and len(manifest["artifact_index"]) == 43
    objects = {path.name for path in (CORPUS / "objects" / "sha256").iterdir()}
    assert objects == {
        entry["digest"].removeprefix("sha256:") for entry in manifest["artifact_index"]
    }
    for path in (CORPUS / "objects" / "sha256").iterdir():
        content = path.read_bytes()
        assert b"/private/" not in content and b"/Users/" not in content
        assert b"PRIVATE KEY" not in content and b"hf_" not in content


def test_the_corpus_imports_migrates_as_a_no_op_and_runs_every_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    workspace = tmp_path / "corpus"
    imported = _oak(
        "import", str(CORPUS), "--directory", str(workspace), "--output", "json", cwd=tmp_path
    )
    assert imported.exit_code == 0, _output(imported)
    assert json.loads(imported.stdout)["case"]["version"] == "0.1.7"

    status = _oak("workspace", "status", "--output", "json", cwd=workspace)
    assert status.exit_code == 0, _output(status)
    assert json.loads(status.stdout)["current"] is True

    before = (workspace / ".oak" / "manifest.json").read_bytes()
    migrated = _oak("workspace", "migrate", "--output", "json", cwd=workspace)
    assert migrated.exit_code == 0, _output(migrated)
    assert json.loads(migrated.stdout)["changed"] is False
    assert (workspace / ".oak" / "manifest.json").read_bytes() == before

    questions = _oak("questions", "--output", "json", cwd=workspace)
    assert questions.exit_code == 0, _output(questions)
    assert json.loads(questions.stdout)["status"] == "bundle_compiled"
    architecture = _oak("architecture", cwd=workspace)
    assert architecture.exit_code == 0, _output(architecture)
    recorded = _oak("report", "--record", "--format", "json", "--output", "-", cwd=workspace)
    assert recorded.exit_code == 0, _output(recorded)

    export = tmp_path / "export"
    exported = _oak("export", "--output", str(export), cwd=workspace)
    assert exported.exit_code == 0, _output(exported)
    assert (
        json.loads((export / "manifest.json").read_bytes())["schema_version"]
        == CURRENT_MANIFEST_FORMAT
    )
    validated = _oak("validate", "export", str(export), "--output", "json", cwd=tmp_path)
    assert validated.exit_code == 0, _output(validated)
    assert json.loads(validated.stdout)["migration_needed"] is False
