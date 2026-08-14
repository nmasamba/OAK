# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-005 installed CLI behavior tests."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installed_cli_version_matches_version_file() -> None:
    result = subprocess.run(
        ["oak", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert result.stderr == ""


def test_installed_cli_help_exposes_only_implemented_behavior() -> None:
    result = subprocess.run(
        ["oak", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "serve" in result.stdout
    for unavailable_command in ("evaluate", "apply"):
        unavailable = subprocess.run(
            ["oak", unavailable_command],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert unavailable.returncode != 0
        assert "No such command" in unavailable.stderr


def test_unimplemented_runner_fails_honestly() -> None:
    result = subprocess.run(
        ["oak-runner"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 69
    assert "not available" in result.stderr
