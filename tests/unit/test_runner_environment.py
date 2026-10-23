# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-010: what the runner's environment can no longer change.

The runner read `OAK_SCHEMA_DIRECTORY`, so whoever set it chose the rules every dispatch
was verified against (RR-033); it resolved `docker` through `PATH` on every call (RR-002);
and its children ran in whatever directory the operator started it from (RR-027).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from oak.contracts import ContractValidationError
from oak.domain import OAKError

ROOT = Path(__file__).resolve().parents[2]


def _fake_binary(directory: Path, name: str, body: str = "exit 0") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_the_runner_verifies_against_its_bundled_schemas_whatever_the_environment_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from oak.bootstrap import canonical_schema_directory as control_plane_directory
    from oak.runner.schemas import canonical_schema_directory, load_registry

    forged = tmp_path / "schemas"
    forged.mkdir()
    for name in ("common.schema.json", "target-profile.schema.json"):
        (forged / name).write_text(
            '{"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "' + name + '"}',
            encoding="utf-8",
        )
    monkeypatch.setenv("OAK_SCHEMA_DIRECTORY", str(forged))

    assert canonical_schema_directory() != forged
    assert (canonical_schema_directory() / "runner-plan.schema.json").is_file()
    with pytest.raises(ContractValidationError):
        load_registry().validate("target-profile.schema.json", {"anything": "accepted"})
    # The control plane still honours the variable; it is the runner that must not.
    assert control_plane_directory() == forged


def test_docker_is_resolved_once_on_the_absolute_entries_of_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from oak.runner.adapters import isolated_executor

    planted = _fake_binary(tmp_path / "bin", "docker")
    trusted = _fake_binary(tmp_path / "trusted", "docker")
    later = _fake_binary(tmp_path / "later", "docker")
    monkeypatch.chdir(tmp_path)
    # `bin` is relative: it would mean tmp_path/bin here and something else elsewhere.
    monkeypatch.setenv("PATH", os.pathsep.join(("bin", str(trusted.parent))))
    captured: list[dict[str, Any]] = []

    def fake_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append({"argv": tuple(argv), **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("oak.runner.adapters.subprocess.run", fake_run)
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    execute = isolated_executor(tmp_path / "docker-config", working_directory=work)
    monkeypatch.setenv("PATH", str(later.parent))
    execute(("docker", "version"), 5)
    execute(("docker", "info"), 5)

    assert [call["argv"][0] for call in captured] == [str(trusted), str(trusted)]
    assert str(planted) not in {call["argv"][0] for call in captured}
    assert all(call["cwd"] == work for call in captured)
    assert all(call["shell"] is False for call in captured)


def test_a_missing_docker_is_reported_when_it_is_needed_and_nothing_else_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from oak.runner.adapters import isolated_executor

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    ran: list[Any] = []
    monkeypatch.setattr("oak.runner.adapters.subprocess.run", lambda *a, **k: ran.append(a))
    execute = isolated_executor(tmp_path / "docker-config", working_directory=tmp_path)

    with pytest.raises(OAKError) as missing:
        execute(("docker", "version"), 5)
    assert missing.value.code == "OAK-RUNNER-EXECUTABLE"
    with pytest.raises(OAKError) as refused:
        execute(("sh", "-c", "id"), 5)
    assert refused.value.code == "OAK-RUNNER-EXECUTABLE"
    assert ran == []


def test_each_run_works_in_a_private_directory_that_is_removed_after_it(tmp_path: Path) -> None:
    from oak.runner.main import _run_directory

    home = tmp_path / "runner"
    home.mkdir(mode=0o700)
    stale = home / "run-left-by-a-crash"
    stale.mkdir()
    (stale / "leftover").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("x", encoding="utf-8")
    (home / "run-link").symlink_to(outside, target_is_directory=True)

    with _run_directory(home) as work:
        assert work.parent == home and work.is_dir()
        assert stat.S_IMODE(work.stat().st_mode) == 0o700
        assert list(work.iterdir()) == []
        assert not stale.exists(), "a crashed run's directory is removed first"
    assert not work.exists()

    with pytest.raises(RuntimeError), _run_directory(home) as failing:
        raise RuntimeError("the run failed")
    assert not failing.exists()
    assert (outside / "keep").is_file(), "a symlink is never followed into"
