# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-001 local, CI, and container toolchain contract tests."""

import json
import re
from pathlib import Path

from tools.check_toolchains import _npm_version, check, runtime_failures

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
        "compose.yaml",
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
        "compose.yaml",
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


def test_web_runtime_base_unpinning_is_rejected(tmp_path: Path) -> None:
    """The nginx runtime line previously escaped drift detection entirely.

    Only the uv, Python and Node FROM lines were guarded, so the web runtime base
    could lose its digest — or change image — without any gate noticing (RR-037's
    fix depends on this base staying what the Dockerfile says it is).
    """

    tree = _mirror(ROOT, tmp_path)
    dockerfile = tree / "deploy/images/web.Dockerfile"
    dockerfile.write_text(
        re.sub(
            r"^FROM nginxinc/nginx-unprivileged:(\d+\.\d+\.\d+)-alpine@sha256:[a-f0-9]{64}$",
            r"FROM nginxinc/nginx-unprivileged:\1-alpine",
            dockerfile.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )

    failures = check(tree)
    assert "deploy/images/web.Dockerfile: expected pinned unprivileged nginx runtime" in failures


def test_api_build_stage_python_drift_is_rejected(tmp_path: Path) -> None:
    """The anchored runtime regex cannot see the `AS build` line, so it was unguarded."""

    tree = _mirror(ROOT, tmp_path)
    dockerfile = tree / "deploy/images/api.Dockerfile"
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            f"FROM python:{python_version}-slim", "FROM python:3.12.0-slim", 1
        ),
        encoding="utf-8",
    )

    failures = check(tree)
    assert "Python version differs between .python-version and API build stage" in failures


def test_compose_postgres_unpinning_is_rejected(tmp_path: Path) -> None:
    """compose.yaml was never read by the toolchain check, leaving its pin unguarded."""

    tree = _mirror(ROOT, tmp_path)
    compose = tree / "compose.yaml"
    compose.write_text(
        re.sub(
            r"^    image: postgres:(\d+\.\d+)-alpine@sha256:[a-f0-9]{64}$",
            r"    image: postgres:\1-alpine",
            compose.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )

    failures = check(tree)
    assert "compose.yaml: expected pinned postgres image with immutable digest" in failures


def test_runtime_check_passes_when_the_provisioned_node_matches_the_pin() -> None:
    """The running Python must equal the pin, and a pnpm reporting the pinned Node passes.

    The Python half runs against the real interpreter — the venv is provisioned by uv
    from `.python-version`, so a mismatch here means the pin and the toolchain have
    genuinely diverged.
    """

    pinned = (ROOT / ".node-version").read_text(encoding="utf-8").strip()
    assert runtime_failures(ROOT, run=lambda _argv: f"v{pinned}\n") == []


def test_runtime_node_drift_is_fatal() -> None:
    """A pnpm-provisioned Node that differs from .node-version must fail the check.

    RR-034: the 0.7.0 web artifacts were built on Node 22.17.1 against a 24.18.0 pin
    and every declaration-only gate stayed green.
    """

    failures = runtime_failures(ROOT, run=lambda _argv: "v22.17.1\n")
    assert any("does not match .node-version" in failure for failure in failures)


def test_runtime_check_fails_closed_when_pnpm_cannot_run() -> None:
    """Not being able to ask pnpm for its Node is a failure, never a pass."""

    def refuse(argv: tuple[str, ...]) -> str:
        raise OSError("pnpm is not installed")

    failures = runtime_failures(ROOT, run=refuse)
    assert any("could not report its Node version" in failure for failure in failures)


def test_managed_node_version_drift_is_rejected(tmp_path: Path) -> None:
    """devEngines.runtime is the setting that makes pnpm provision the pinned Node.

    If its version drifts from .node-version, pnpm would silently provision and run a
    different Node than every other declaration names.
    """

    tree = _mirror(ROOT, tmp_path)
    manifest = tree / "package.json"
    node_version = (ROOT / ".node-version").read_text(encoding="utf-8").strip()
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            f'"version": "{node_version}"', '"version": "22.17.1"'
        ),
        encoding="utf-8",
    )

    assert "Node version differs between .node-version and devEngines.runtime" in check(tree)


def test_a_missing_managed_node_declaration_is_rejected(tmp_path: Path) -> None:
    tree = _mirror(ROOT, tmp_path)
    manifest = tree / "package.json"
    document = manifest.read_text(encoding="utf-8")
    assert '"devEngines"' in document
    parsed = json.loads(document)
    del parsed["devEngines"]
    manifest.write_text(json.dumps(parsed), encoding="utf-8")

    assert "package.json: devEngines.runtime must pin the managed Node" in check(tree)


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
