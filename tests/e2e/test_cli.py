# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-005 and OAK-S1-009 installed CLI behavior tests."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OAK = ROOT / ".venv" / "bin" / "oak"
OAK_RUNNER = ROOT / ".venv" / "bin" / "oak-runner"


def _run_oak(*arguments: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}
    return subprocess.run(
        [str(OAK), *arguments],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_installed_cli_version_matches_version_file() -> None:
    result = subprocess.run(
        [str(OAK), "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert result.stderr == ""


def test_installed_cli_help_exposes_only_implemented_behavior() -> None:
    result = subprocess.run(
        [str(OAK), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "serve" in result.stdout
    for available_command in ("candidates", "evaluate", "select", "assure", "plan"):
        assert available_command in result.stdout
    for unavailable_command in ("apply",):
        unavailable = subprocess.run(
            [str(OAK), unavailable_command],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert unavailable.returncode != 0
        assert "No such command" in unavailable.stderr


def test_unimplemented_runner_fails_honestly() -> None:
    result = subprocess.run(
        [str(OAK_RUNNER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 69
    assert "not available" in result.stderr


def test_offline_design_confirmation_retry_and_portable_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    export = tmp_path / "case-export"
    imported = tmp_path / "imported"
    brief = ROOT / "examples" / "briefs" / "public-manual-qa.yaml"
    answers = ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml"

    initialized = _run_oak("init", str(workspace), "--output", "json", cwd=tmp_path)
    designed = _run_oak("design", str(brief), "--output", "json", cwd=workspace)
    questions = _run_oak("questions", "--output", "json", cwd=workspace)
    confirmed = _run_oak("confirm", "--answers", str(answers), "--output", "json", cwd=workspace)
    retry = _run_oak("confirm", "--answers", str(answers), "--output", "json", cwd=workspace)
    exported = _run_oak("export", "--output", str(export), cwd=workspace)
    imported_result = _run_oak(
        "import", str(export), "--directory", str(imported), "--output", "json", cwd=tmp_path
    )

    assert json.loads(initialized.stdout)["status"] == "initialized"
    assert json.loads(designed.stdout)["id"] == "intent.public-manual-qa"
    assert len(json.loads(questions.stdout)["questions"]) == 5
    first_confirmation = json.loads(confirmed.stdout)
    retry_confirmation = json.loads(retry.stdout)
    assert first_confirmation["case"]["version"] == "0.1.1"
    assert first_confirmation["duplicate"] is False
    assert retry_confirmation["duplicate"] is True
    assert retry_confirmation["case"] == first_confirmation["case"]
    assert "Exported design-case.public-manual-qa@0.1.1" in exported.stdout
    assert json.loads(imported_result.stdout)["case"] == first_confirmation["case"]
    source_manifest = json.loads((workspace / ".oak" / "manifest.json").read_text())
    imported_manifest = json.loads((imported / ".oak" / "manifest.json").read_text())
    assert source_manifest == imported_manifest
    assert len(source_manifest["audit_events"]) == 2


def test_cli_rejects_malformed_confirmation_without_state_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    brief = ROOT / "examples" / "briefs" / "public-manual-qa.yaml"
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("answers: [unterminated\n", encoding="utf-8")
    _run_oak("init", str(workspace), cwd=tmp_path)
    _run_oak("design", str(brief), cwd=workspace)
    before = (workspace / ".oak" / "manifest.json").read_bytes()

    result = _run_oak("confirm", "--answers", str(malformed), cwd=workspace, check=False)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("OAK-CONFIRM-MALFORMED:")
    assert (workspace / ".oak" / "manifest.json").read_bytes() == before

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * 65_537)
    oversized_result = _run_oak("confirm", "--answers", str(oversized), cwd=workspace, check=False)
    assert oversized_result.returncode == 2
    assert oversized_result.stderr.startswith("OAK-CONFIRM-SIZE:")
    assert (workspace / ".oak" / "manifest.json").read_bytes() == before


def test_offline_candidate_to_plan_flow_is_semantically_reproducible(tmp_path: Path) -> None:
    brief = ROOT / "examples/briefs/public-manual-qa.yaml"
    answers = ROOT / "examples/briefs/public-manual-qa-answers.yaml"
    target = ROOT / "examples/targets/local-fixture.yaml"
    rationale = tmp_path / "decision.md"
    rationale.write_text(
        "Select candidate-03 to exercise bounded cited-answer drafting while retaining the "
        "simpler baseline as a visible alternative.\n",
        encoding="utf-8",
    )

    outputs: list[Path] = []
    for sequence in (1, 2):
        workspace = tmp_path / f"workspace-{sequence}"
        assurance = tmp_path / f"assurance-{sequence}"
        bundle = tmp_path / f"bundle-{sequence}"
        _run_oak("init", str(workspace), cwd=tmp_path)
        _run_oak("design", str(brief), cwd=workspace)
        confirmed = _run_oak(
            "confirm", "--answers", str(answers), "--output", "json", cwd=workspace
        )
        candidates = _run_oak("candidates", "--output", "table", cwd=workspace)
        evaluation = _run_oak("evaluate", "candidate-03", "--output", "json", cwd=workspace)
        _run_oak(
            "select",
            "candidate-03",
            "--rationale-file",
            str(rationale),
            cwd=workspace,
        )
        _run_oak("assure", "candidate-03", "--output", str(assurance), cwd=workspace)
        planned = _run_oak(
            "plan",
            "candidate-03",
            "--target",
            str(target),
            "--output",
            str(bundle),
            cwd=workspace,
        )

        assert json.loads(confirmed.stdout)["case"]["status"] == "ready_for_candidates"
        assert "candidate-00" in candidates.stdout
        assert "simpler_baseline" in candidates.stdout
        assert "candidate-04" in candidates.stdout
        assert "infeasible" in candidates.stdout
        assert json.loads(evaluation.stdout)["evaluation"]["status"] == "pass"
        assert "no target action was invoked" in planned.stdout
        runner_plan = json.loads((bundle / "runner-plan.json").read_text(encoding="utf-8"))
        assert runner_plan["status"] == "draft"
        assert runner_plan["approvals"] == []
        assert [item["kind"] for item in runner_plan["operations"]] == [
            "inventory",
            "validate",
            "render",
            "plan",
            "verify",
        ]
        serialized = json.dumps(runner_plan, sort_keys=True).casefold()
        assert '"command"' not in serialized
        assert '"shell"' not in serialized
        outputs.append(bundle)

    assert (outputs[0] / "semantic-manifest.json").read_bytes() == (
        outputs[1] / "semantic-manifest.json"
    ).read_bytes()
