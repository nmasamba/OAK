# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-001 local, CI, and container toolchain contract tests."""

from pathlib import Path

from tools.check_toolchains import check

ROOT = Path(__file__).resolve().parents[2]


def test_repository_toolchain_declarations_agree() -> None:
    assert check(ROOT) == []


def test_ci_uv_drift_is_rejected(tmp_path: Path) -> None:
    paths = (
        ".python-version",
        ".node-version",
        "package.json",
        "deploy/images/api.Dockerfile",
        "deploy/images/web.Dockerfile",
        ".github/workflows/ci.yml",
        "README.md",
        "docs/development.md",
    )
    for relative in paths:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace('version: "0.10.8"', 'version: "0.10.7"'),
        encoding="utf-8",
    )

    assert "uv version differs between CI and API container" in check(tmp_path)
