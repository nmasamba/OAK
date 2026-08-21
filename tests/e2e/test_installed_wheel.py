# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-001: the artifact that ships must work outside the source checkout.

Every other end-to-end test runs against `.venv`, which holds an *editable* install
of the repository. An editable install always resolves canonical schemas, the
catalogue, migrations and policy packs from the source tree, so it never exercises
the packaged-data branch in `oak.bootstrap` that the wheel's `force-include` entries
exist to satisfy. That gap is not hypothetical: a force-included directory that never
reached the image build context left the API image unbuildable for a whole sprint,
and neither `make build` nor CI could see it.

These tests build the real wheel, unpack it somewhere with no source tree above it,
and drive it from there. They are hermetic and need no network.
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
FORCE_INCLUDED_SENTINELS = {
    "oak/canonical_schemas/common.schema.json": "canonical schemas",
    "oak/community_catalogue": "community catalogue",
    "oak/community_policy_packs": "community policy packs",
    "oak/migrations/env.py": "alembic migrations",
}
CONSOLE_SCRIPTS = {
    "oak",
    "oak-api",
    "oak-db-migrate",
    "oak-worker",
    "oak-runner",
    "oak-mcp",
}

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the release wheel from the current tree."""

    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--no-build-isolation", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "UV_CACHE_DIR": str(ROOT / ".uv-cache")},
    )
    built = sorted(out.glob("*.whl"))
    assert len(built) == 1, f"expected exactly one wheel, got {built}"
    return built[0]


@pytest.fixture(scope="module")
def unpacked(wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Unpack the wheel where no source checkout sits above it."""

    destination = tmp_path_factory.mktemp("site")
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(destination)
    assert not (destination.parent.parent / "schemas").exists(), (
        "the unpack location must not have a source tree above it, or the "
        "source-checkout fallback would mask a broken wheel"
    )
    return destination


def _run_packaged(unpacked: Path, code: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run Python against the unpacked wheel only, from outside the checkout."""

    environment = {
        key: value
        for key, value in os.environ.items()
        # A configured directory would defeat the point: these tests assert that the
        # packaged copies resolve with no configuration at all.
        if key
        not in {
            "OAK_SCHEMA_DIRECTORY",
            "OAK_CATALOGUE_DIRECTORY",
            "OAK_POLICY_PACK_DIRECTORY",
            "PYTHONPATH",
        }
    }
    environment["PYTHONPATH"] = str(unpacked)
    environment["NO_PROXY"] = "*"
    environment["no_proxy"] = "*"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_the_wheel_carries_every_force_included_tree(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    for sentinel, description in FORCE_INCLUDED_SENTINELS.items():
        present = sentinel in names or any(name.startswith(f"{sentinel}/") for name in names)
        assert present, f"{description} missing from the wheel ({sentinel})"


def test_the_wheel_declares_every_console_script(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        entry_points = archive.read(f"oak_community-{VERSION}.dist-info/entry_points.txt").decode(
            "utf-8"
        )

    declared = {
        line.split("=", 1)[0].strip()
        for line in entry_points.splitlines()
        if "=" in line and not line.startswith("[")
    }
    assert declared == CONSOLE_SCRIPTS


def test_console_script_targets_import_from_the_packaged_wheel(
    wheel: Path, unpacked: Path, tmp_path: Path
) -> None:
    """A console script that names a deleted module fails only at first run.

    The Sprint 0 placeholder entrypoints survived into a built wheel exactly this
    way, so the targets are resolved rather than trusted.
    """

    with zipfile.ZipFile(wheel) as archive:
        entry_points = archive.read(f"oak_community-{VERSION}.dist-info/entry_points.txt").decode(
            "utf-8"
        )

    targets = [
        line.split("=", 1)[1].strip()
        for line in entry_points.splitlines()
        if "=" in line and not line.startswith("[")
    ]
    code = (
        "import importlib\n"
        f"targets = {targets!r}\n"
        "for target in targets:\n"
        "    module_name, _, attribute = target.partition(':')\n"
        "    module = importlib.import_module(module_name)\n"
        "    assert hasattr(module, attribute), target\n"
        "print('ok')\n"
    )

    result = _run_packaged(unpacked, code, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_packaged_data_resolves_from_the_wheel_not_a_source_tree(
    unpacked: Path, tmp_path: Path
) -> None:
    code = (
        "import json\n"
        "from oak.bootstrap import (\n"
        "    canonical_catalogue_directory,\n"
        "    canonical_policy_pack_directory,\n"
        "    canonical_schema_directory,\n"
        ")\n"
        "print(json.dumps({\n"
        "    'schemas': str(canonical_schema_directory()),\n"
        "    'catalogue': str(canonical_catalogue_directory()),\n"
        "    'policy_packs': str(canonical_policy_pack_directory()),\n"
        "}))\n"
    )

    result = _run_packaged(unpacked, code, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    assert set(resolved) == {"schemas", "catalogue", "policy_packs"}
    for name, path in resolved.items():
        assert Path(path).is_relative_to(unpacked), f"{name} resolved outside the wheel: {path}"
        assert not Path(path).is_relative_to(ROOT), f"{name} resolved into the checkout: {path}"


def test_the_packaged_cli_completes_the_reference_journey_outside_the_checkout(
    unpacked: Path, tmp_path: Path
) -> None:
    """Schemas and the catalogue are both needed before candidates can be produced."""

    brief = tmp_path / "brief.yaml"
    shutil.copyfile(ROOT / "examples" / "briefs" / "public-manual-qa.yaml", brief)
    answers = tmp_path / "answers.yaml"
    shutil.copyfile(ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml", answers)
    workspace = tmp_path / "workspace"

    code = (
        "import sys\n"
        "from oak.interfaces.cli.main import app\n"
        "from typer.testing import CliRunner\n"
        "runner = CliRunner()\n"
        "for arguments in (\n"
        f"    ['init', {str(workspace)!r}],\n"
        "):\n"
        "    result = runner.invoke(app, arguments)\n"
        "    assert result.exit_code == 0, (arguments, result.output)\n"
        "print('init-ok')\n"
    )
    initialised = _run_packaged(unpacked, code, cwd=tmp_path)
    assert initialised.returncode == 0, initialised.stderr
    assert "init-ok" in initialised.stdout

    journey = (
        "from oak.interfaces.cli.main import app\n"
        "from typer.testing import CliRunner\n"
        "runner = CliRunner()\n"
        f"design = runner.invoke(app, ['design', {str(brief)!r}, '--output', 'json'])\n"
        "assert design.exit_code == 0, design.output\n"
        "questions = runner.invoke(app, ['questions', '--output', 'json'])\n"
        "assert questions.exit_code == 0, questions.output\n"
        f"confirm = runner.invoke(app, ['confirm', '--answers', {str(answers)!r}])\n"
        "assert confirm.exit_code == 0, confirm.output\n"
        "candidates = runner.invoke(app, ['candidates', '--output', 'json'])\n"
        "assert candidates.exit_code == 0, candidates.output\n"
        "assert 'candidate-03' in candidates.output\n"
        "print('journey-ok')\n"
    )
    result = _run_packaged(unpacked, journey, cwd=workspace)

    assert result.returncode == 0, result.stderr
    assert "journey-ok" in result.stdout


def test_the_packaged_version_matches_the_version_file(unpacked: Path, tmp_path: Path) -> None:
    result = _run_packaged(unpacked, "import oak; print(oak.__version__)", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VERSION
