# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-047: the `inventory` operation's scan runs its commands the way the run does.

`oak-runner run-once` builds one executor per run, so that every command it starts sees
only the empty, runner-owned Docker configuration in `$OAK_RUNNER_HOME/docker-config`
(`RR-013`) and starts in the run's private `run-*` directory under the runner home
(`RR-027`). The hardware scan inside `inventory` was not handed that executor: its commands,
`docker version` among them, ran through the process-wide default one, from a temporary
directory of its own with a Docker configuration of its own.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from oak.runner.hardware import DOCKER_VERSION_ARGUMENTS
from oak.runner.main import run_once
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration


def test_the_inventory_scan_runs_in_the_runs_directory_with_the_runners_docker_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The runner judges plan expiry and leases on the wall clock, so this runs on it too.
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    harness = build_compiled_case(tmp_path, now=now)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.dispatch(("inventory",), harness.context("dispatch-inventory-1", "0.1.9"))
    home = tmp_path / "runner"
    monkeypatch.setenv("OAK_RUNNER_MAILBOX", str(harness.mailbox_root))
    monkeypatch.setenv("OAK_RUNNER_HOME", str(home))
    monkeypatch.setenv("OAK_RUNNER_TRUST_ANCHORS", str(harness.trust_directory))
    monkeypatch.setenv(
        "OAK_RUNNER_TARGET_PROFILE", str(ROOT / "examples/targets/local-fixture.yaml")
    )
    # A `docker` first on PATH, so that the scan asks for the daemon's version on every
    # machine the suite runs on. Nothing is executed: each child is recorded, not started.
    docker = tmp_path / "bin" / "docker"
    docker.parent.mkdir()
    docker.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    docker.chmod(0o755)
    monkeypatch.setenv(
        "PATH", os.pathsep.join((str(docker.parent), os.environ.get("PATH", os.defpath)))
    )
    # The process-wide default executor resolves its executables once and keeps them: it
    # starts afresh here and is restored afterwards, so this PATH never outlives the test.
    monkeypatch.setattr("oak.runner.adapters._DEFAULT_EXECUTOR", None)
    children: list[dict[str, Any]] = []

    def record(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        existed = Path(kwargs["cwd"]).is_dir()
        children.append({"argv": tuple(argv), "cwd_existed": existed, **kwargs})
        # The daemon answers; every other tool fails, which the scan records and moves past.
        if tuple(argv) == (str(docker), *DOCKER_VERSION_ARGUMENTS[1:]):
            return subprocess.CompletedProcess(argv, 0, stdout="28.5.1\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    monkeypatch.setattr("oak.runner.adapters.subprocess.run", record)

    assert run_once() == 0

    [version] = [child for child in children if child["argv"][1:] == DOCKER_VERSION_ARGUMENTS[1:]]
    assert version["argv"][0] == str(docker)
    assert version["env"] == {"PATH": os.defpath, "DOCKER_CONFIG": str(home / "docker-config")}
    work = Path(version["cwd"])
    assert work.parent == home and work.name.startswith("run-") and version["cwd_existed"]
    # Every other tool the scan ran, not only `docker`, ran the same way.
    assert all(child["cwd"] == work and child["env"] == version["env"] for child in children)
    # And the completion reports what that `docker` answered.
    [message] = (harness.mailbox_root / "messages").glob("runner-message.completion.*.json")
    payload = json.loads(message.read_text(encoding="utf-8"))["payload"]
    assert payload["outcome"] == "succeeded" and payload["applied_kinds"] == ["inventory"]
    inventory = next(item for item in payload["evidence"] if item["operation"] == "inventory")
    prerequisites = inventory["content"]["hardware"]["prerequisites"]
    assert {"name": "docker", "state": "present"} in prerequisites
