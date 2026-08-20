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


def test_status_reports_the_current_repository_version() -> None:
    """STATUS.md's version claim must track the packaged version.

    Nothing else compares them, so the header silently kept reporting the
    previous sprint's version after a release bump.
    """

    root = Path(__file__).resolve().parents[2]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    status = (root / "STATUS.md").read_text(encoding="utf-8")
    assert f"- **Repository version:** `{version}`" in status


def test_wheel_force_includes_are_copied_into_the_api_image() -> None:
    """Every force-included directory must reach the image build context.

    `uv sync` builds the wheel inside the image, so a force-include that is not
    COPYed fails the build with `Forced include not found`. Nothing else compares
    the two lists, and `make build` cannot catch it because it runs at the repo
    root where every directory already exists.
    """

    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    dockerfile = (root / "deploy" / "images" / "api.Dockerfile").read_text(encoding="utf-8")

    block = pyproject.split("[tool.hatch.build.targets.wheel.force-include]")[1]
    block = block.split("[", 1)[0]
    sources = [
        line.split("=")[0].strip().strip('"')
        for line in block.splitlines()
        if "=" in line and line.strip().startswith('"')
    ]
    assert sources, "no force-include entries were parsed"

    missing = [name for name in sources if f"COPY {name} ./{name}" not in dockerfile]
    assert not missing, f"force-included but never COPYed into the API image: {missing}"
