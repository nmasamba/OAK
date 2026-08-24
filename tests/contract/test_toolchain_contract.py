# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-001 local, CI, and container toolchain contract tests."""

from pathlib import Path

from tools.check_toolchains import _npm_version, check

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


def test_npm_and_python_version_spellings_agree_for_releases_and_pre_releases() -> None:
    """The two grammars diverge only before a release; both spellings must be derivable."""

    assert _npm_version("0.7.0") == "0.7.0"
    assert _npm_version("0.8.0.dev8") == "0.8.0-dev.8"
    assert _npm_version("1.0.0.rc1") == "1.0.0-rc.1"


def _mirror(root: Path, tmp_path: Path) -> Path:
    """Copy every file the toolchain contract reads into a scratch tree."""

    for relative in (
        "VERSION",
        ".python-version",
        ".node-version",
        "package.json",
        "web/package.json",
        "pyproject.toml",
        "STATUS.md",
        "openapi/oak.openapi.json",
        "deploy/images/api.Dockerfile",
        "deploy/images/web.Dockerfile",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "README.md",
        "docs/development.md",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((root / relative).read_bytes())
    return tmp_path


def test_web_workspace_version_drift_is_rejected(tmp_path: Path) -> None:
    """The web bundle self-reports a version; nothing compared it until 0.7.0.

    `package.json` sat at `0.5.0-dev.5` while the Python distribution was
    `0.6.0.dev6`, so a release would have shipped a web bundle advertising a
    different version than the wheel beside it.
    """

    tree = _mirror(ROOT, tmp_path)
    manifest = tree / "web/package.json"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace('"version": "', '"version": "9.'),
        encoding="utf-8",
    )

    failures = check(tree)
    assert any(
        "web/package.json" in failure and "differs from VERSION" in failure for failure in failures
    )


def test_packaged_version_drift_is_rejected(tmp_path: Path) -> None:
    tree = _mirror(ROOT, tmp_path)
    pyproject = tree / "pyproject.toml"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            f'version = "{version}"', 'version = "9.9.9"', 1
        ),
        encoding="utf-8",
    )

    assert "pyproject.toml: project version differs from VERSION" in check(tree)


def test_openapi_info_version_drift_is_rejected(tmp_path: Path) -> None:
    """`info.version` is published in the OpenAPI contract consumers generate clients from."""

    tree = _mirror(ROOT, tmp_path)
    document = tree / "openapi/oak.openapi.json"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            f'"version": "{version}"', '"version": "9.9.9"'
        ),
        encoding="utf-8",
    )

    assert "openapi/oak.openapi.json: info.version differs from VERSION" in check(tree)


def test_release_builder_uv_drift_is_rejected(tmp_path: Path) -> None:
    """The release workflow must build with the same uv as CI and the container.

    A release produced by a different builder is not the artifact anyone reviewed,
    and nothing else compares the two workflows.
    """

    tree = _mirror(ROOT, tmp_path)
    workflow = tree / ".github/workflows/release.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace('version: "0.10.8"', 'version: "0.10.7"'),
        encoding="utf-8",
    )

    failures = check(tree)
    assert "uv version differs between the release workflow and API container" in failures
