# SPDX-License-Identifier: Apache-2.0
"""OAK-S5 exit demonstration through the installed CLI and runner entrypoints."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OAK = ROOT / ".venv" / "bin" / "oak"
OAK_RUNNER = ROOT / ".venv" / "bin" / "oak-runner"
MUTATION_TARGET = ROOT / "examples/targets/local-mutation-fixture.yaml"


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=env, check=False, capture_output=True, text=True
    )


def _environment(tmp_path: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["OAK_TRUST_DIRECTORY"] = str(tmp_path / "trust")
    environment["OAK_DISPATCH_MAILBOX"] = str(tmp_path / "mailbox")
    environment["OAK_ACTOR"] = "local-user"
    return environment


def _compile_case(workspace: Path, environment: dict[str, str], target: Path) -> None:
    assert _run([str(OAK), "init", str(workspace)], ROOT, environment).returncode == 0
    steps = [
        ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")],
        ["questions"],
        ["confirm", "--answers", str(ROOT / "examples/briefs/public-manual-qa-answers.yaml")],
        ["candidates"],
        ["evaluate", "candidate-03"],
    ]
    for step in steps:
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, f"{step}: {result.stderr}"
    rationale = workspace / "decision.md"
    rationale.write_text("Balanced fixture for the runner exit demonstration.\n", encoding="utf-8")
    for step in (
        ["select", "candidate-03", "--rationale-file", str(rationale)],
        ["assure", "candidate-03", "--output", str(workspace / "assurance")],
        ["plan", "candidate-03", "--target", str(target), "--output", str(workspace / "bundle")],
    ):
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, f"{step}: {result.stderr}"


def test_signed_read_only_dispatch_completes_without_touching_a_target(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "workspace"
    _compile_case(workspace, environment, ROOT / "examples/targets/local-fixture.yaml")

    assert _run([str(OAK), "keys", "init"], workspace, environment).returncode == 0
    signed = _run([str(OAK), "sign"], workspace, environment)
    assert signed.returncode == 0, signed.stderr
    approved = _run([str(OAK), "approve", "dry_run"], workspace, environment)
    assert approved.returncode == 0, approved.stderr
    dispatched = _run(
        [str(OAK), "dispatch", "inventory", "validate", "render", "plan", "verify"],
        workspace,
        environment,
    )
    assert dispatched.returncode == 0, dispatched.stderr

    runner_environment = dict(environment)
    runner_environment.update(
        {
            "OAK_RUNNER_MAILBOX": environment["OAK_DISPATCH_MAILBOX"],
            "OAK_RUNNER_HOME": str(tmp_path / "runner"),
            "OAK_RUNNER_TRUST_ANCHORS": environment["OAK_TRUST_DIRECTORY"],
            "OAK_RUNNER_TARGET_PROFILE": str(ROOT / "examples/targets/local-fixture.yaml"),
        }
    )
    ran = _run([str(OAK_RUNNER), "run-once"], ROOT, runner_environment)
    assert ran.returncode == 0, ran.stderr
    assert "succeeded" in ran.stdout

    status = _run([str(OAK_RUNNER), "status"], ROOT, runner_environment)
    report = json.loads(status.stdout)
    assert report["journals"][0]["chain"] == "verified"
    assert report["journals"][0]["manual_recovery_required"] is False

    ingested = _run([str(OAK), "ingest", "--output", "json"], workspace, environment)
    assert ingested.returncode == 0, ingested.stderr
    document = json.loads(ingested.stdout)
    assert len(document["accepted"]) == 1
    assert document["accepted"][0]["payload"]["outcome"] == "succeeded"
    assert document["rejected"] == []


def test_tampered_envelope_is_denied_before_any_target_access(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "workspace"
    _compile_case(workspace, environment, ROOT / "examples/targets/local-fixture.yaml")
    for step in (["keys", "init"], ["sign"], ["approve", "dry_run"]):
        assert _run([str(OAK), *step], workspace, environment).returncode == 0
    assert (
        _run([str(OAK), "dispatch", "inventory", "verify"], workspace, environment).returncode == 0
    )

    mailbox = Path(environment["OAK_DISPATCH_MAILBOX"])
    dispatch_dir = next((mailbox / "dispatches").iterdir())
    envelope_path = dispatch_dir / "envelope.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["requested_kinds"] = ["inventory", "verify", "apply"]
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    runner_environment = dict(environment)
    runner_environment.update(
        {
            "OAK_RUNNER_MAILBOX": environment["OAK_DISPATCH_MAILBOX"],
            "OAK_RUNNER_HOME": str(tmp_path / "runner"),
            "OAK_RUNNER_TRUST_ANCHORS": environment["OAK_TRUST_DIRECTORY"],
            "OAK_RUNNER_TARGET_PROFILE": str(ROOT / "examples/targets/local-fixture.yaml"),
        }
    )
    ran = _run([str(OAK_RUNNER), "run-once"], ROOT, runner_environment)
    assert ran.returncode == 0
    assert "denied" in ran.stderr
    assert not (tmp_path / "runner" / "journals").exists()


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is required for the apply cycle")
def test_signed_apply_and_rollback_touch_only_the_fixture_container(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "workspace"
    _compile_case(workspace, environment, MUTATION_TARGET)
    for step in (
        ["keys", "init"],
        ["sign"],
        ["approve", "dry_run"],
        ["approve", "apply"],
        ["approve", "rollback"],
    ):
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, result.stderr
    dispatched = _run(
        [str(OAK), "dispatch", "apply", "verify", "rollback"], workspace, environment
    )
    assert dispatched.returncode == 0, dispatched.stderr

    runner_environment = dict(environment)
    runner_environment.update(
        {
            "OAK_RUNNER_MAILBOX": environment["OAK_DISPATCH_MAILBOX"],
            "OAK_RUNNER_HOME": str(tmp_path / "runner"),
            "OAK_RUNNER_TRUST_ANCHORS": environment["OAK_TRUST_DIRECTORY"],
            "OAK_RUNNER_TARGET_PROFILE": str(MUTATION_TARGET),
        }
    )
    ran = _run([str(OAK_RUNNER), "run-once"], ROOT, runner_environment)
    assert ran.returncode == 0, ran.stderr
    assert "succeeded" in ran.stdout

    # The fixture container was created and then removed by the rollback operation.
    remaining = subprocess.run(
        ["docker", "ps", "--all", "--filter", "name=oak-fixture-", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert "oak-fixture-local-mutation-fixture" not in remaining.stdout

    journal_path = next((tmp_path / "runner" / "journals").glob("*.jsonl"))
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    kinds = [entry["entry_type"] for entry in entries]
    assert "operation_before" in kinds and "rollback_after" in kinds
