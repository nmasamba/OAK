# SPDX-License-Identifier: Apache-2.0
"""OAK-S6 exit demonstration through the installed CLI entrypoint.

A contributor builds a policy pack and a deployment-adapter binding from the
shipped templates, runs the lifecycle offline, and installs them through
explicit local configuration. A poisoned and an unsigned extension stay
quarantined. Swapping policy engines and deployment renderers changes target
artifacts only.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OAK = ROOT / ".venv" / "bin" / "oak"
TEMPLATES = ROOT / "templates" / "extensions"


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, check=False, capture_output=True, text=True)


def _environment(tmp_path: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["OAK_TRUST_DIRECTORY"] = str(tmp_path / "trust")
    environment["OAK_DISPATCH_MAILBOX"] = str(tmp_path / "mailbox")
    environment["OAK_EXTENSIONS_DIRECTORY"] = str(tmp_path / "extensions")
    environment["OAK_ACTOR"] = "local-user"
    return environment


def _compile_case(workspace: Path, environment: dict[str, str]) -> None:
    assert _run([str(OAK), "init", str(workspace)], ROOT, environment).returncode == 0
    steps = [
        ["design", str(ROOT / "examples/briefs/public-manual-qa.yaml")],
        ["confirm", "--answers", str(ROOT / "examples/briefs/public-manual-qa-answers.yaml")],
        ["candidates"],
        ["evaluate", "candidate-03"],
    ]
    for step in steps:
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, f"{step}: {result.stderr}"
    rationale = workspace / "decision.md"
    rationale.write_text("Balanced fixture for the SDK exit demonstration.\n", encoding="utf-8")
    for step in (
        ["select", "candidate-03", "--rationale-file", str(rationale)],
        ["assure", "candidate-03", "--output", str(workspace / "assurance")],
        [
            "plan",
            "candidate-03",
            "--target",
            str(ROOT / "examples/targets/local-fixture.yaml"),
            "--output",
            str(workspace / "bundle"),
        ],
    ):
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, f"{step}: {result.stderr}"


def test_contributor_extension_journey_and_adapter_swap(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "workspace"
    _compile_case(workspace, environment)
    assert _run([str(OAK), "keys", "init"], workspace, environment).returncode == 0

    # Contributor builds a pack extension from the shipped template.
    pack_source = tmp_path / "my-pack"
    shutil.copytree(TEMPLATES / "policy-pack", pack_source)
    signed = _run([str(OAK), "extensions", "sign", str(pack_source)], workspace, environment)
    assert signed.returncode == 0, signed.stderr
    installed = _run([str(OAK), "extensions", "install", str(pack_source)], workspace, environment)
    assert installed.returncode == 0, installed.stderr
    assert "quarantine" in installed.stdout

    verified = _run(
        [str(OAK), "extensions", "verify", "extension.template-policy-pack"],
        workspace,
        environment,
    )
    assert verified.returncode == 0, verified.stderr
    assert "PASSED" in verified.stdout

    activated = _run(
        [str(OAK), "extensions", "activate", "extension.template-policy-pack"],
        workspace,
        environment,
    )
    assert activated.returncode == 0, activated.stderr

    # A deployment-adapter binding from the template, installed explicitly.
    adapter_source = tmp_path / "my-adapter"
    shutil.copytree(TEMPLATES / "deployment-adapter", adapter_source)
    for step in (
        ["extensions", "sign", str(adapter_source)],
        ["extensions", "install", str(adapter_source)],
        ["extensions", "activate", "extension.template-deployment-adapter"],
    ):
        result = _run([str(OAK), *step], workspace, environment)
        assert result.returncode == 0, f"{step}: {result.stderr}"

    listing = _run([str(OAK), "extensions", "list", "--output", "json"], workspace, environment)
    states = {item["id"]: item["state"] for item in json.loads(listing.stdout)["extensions"]}
    assert states["extension.template-policy-pack"] == "active"
    assert states["extension.template-deployment-adapter"] == "active"

    # The activated pack is usable; the bundled pack still works; both engines
    # would produce the same canonical decision (builtin used here).
    packs = _run([str(OAK), "policy", "packs", "--output", "json"], workspace, environment)
    pack_ids = {item["id"] for item in json.loads(packs.stdout)["packs"]}
    assert {"pack.community-baseline", "pack.template"} <= pack_ids

    evaluated = _run(
        [str(OAK), "policy", "evaluate", "--pack", "pack.template", "--output", "json"],
        workspace,
        environment,
    )
    assert evaluated.returncode == 0, evaluated.stderr
    decision = json.loads(evaluated.stdout)["decision"]
    assert decision["outcome"] == "allow"
    assert "engine" not in decision

    # An unsigned copy stays quarantined with machine-readable reasons.
    unsigned_source = tmp_path / "unsigned-pack"
    shutil.copytree(TEMPLATES / "policy-pack", unsigned_source)
    manifest = yaml.safe_load((unsigned_source / "extension.yaml").read_text())
    manifest["id"] = "extension.unsigned-pack"
    (unsigned_source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    assert (
        _run(
            [str(OAK), "extensions", "install", str(unsigned_source)], workspace, environment
        ).returncode
        == 0
    )
    refused = _run(
        [str(OAK), "extensions", "activate", "extension.unsigned-pack"],
        workspace,
        environment,
    )
    assert refused.returncode == 2
    assert "OAK-EXTENSION-QUARANTINED" in refused.stderr

    # A poisoned (tampered-after-signing) copy stays quarantined too.
    poisoned_source = tmp_path / "poisoned-pack"
    shutil.copytree(TEMPLATES / "policy-pack", poisoned_source)
    manifest = yaml.safe_load((poisoned_source / "extension.yaml").read_text())
    manifest["id"] = "extension.poisoned-pack"
    (poisoned_source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    assert (
        _run(
            [str(OAK), "extensions", "sign", str(poisoned_source)], workspace, environment
        ).returncode
        == 0
    )
    pack_document = yaml.safe_load((poisoned_source / "pack.yaml").read_text())
    pack_document["rules"][0]["outcome"] = "allow"
    (poisoned_source / "pack.yaml").write_text(
        yaml.safe_dump(pack_document, sort_keys=True), encoding="utf-8"
    )
    assert (
        _run(
            [str(OAK), "extensions", "install", str(poisoned_source)], workspace, environment
        ).returncode
        == 0
    )
    poisoned = _run(
        [str(OAK), "extensions", "activate", "extension.poisoned-pack"],
        workspace,
        environment,
    )
    assert poisoned.returncode == 2
    assert "OAK-EXTENSION-QUARANTINED" in poisoned.stderr

    # Swapping deployment renderers changes target artifacts, not the case.
    case_before = json.loads(
        _run([str(OAK), "policy", "packs", "--output", "json"], workspace, environment).stdout
    )
    local_render = _run(
        [
            str(OAK),
            "render",
            "--adapter",
            "renderer.local-manifests",
            "--output",
            str(tmp_path / "render-local"),
        ],
        workspace,
        environment,
    )
    assert local_render.returncode == 0, local_render.stderr
    helm_render = _run(
        [
            str(OAK),
            "render",
            "--adapter",
            "renderer.helm-kubernetes",
            "--output",
            str(tmp_path / "render-helm"),
        ],
        workspace,
        environment,
    )
    assert helm_render.returncode == 0, helm_render.stderr
    local_files = {
        path.relative_to(tmp_path / "render-local").as_posix()
        for path in (tmp_path / "render-local").rglob("*")
        if path.is_file()
    }
    helm_files = {
        path.relative_to(tmp_path / "render-helm").as_posix()
        for path in (tmp_path / "render-helm").rglob("*")
        if path.is_file()
    }
    assert local_files != helm_files
    assert "chart/Chart.yaml" in helm_files
    assert "manifests/semantic-manifest.json" in local_files
    case_after = json.loads(
        _run([str(OAK), "policy", "packs", "--output", "json"], workspace, environment).stdout
    )
    assert case_before == case_after

    # Capability discovery reports the SDK surface.
    capabilities = _run(
        [str(OAK), "extensions", "capabilities", "--output", "json"], workspace, environment
    )
    document = json.loads(capabilities.stdout)
    assert document["sdk_version"] == "1.0.0"
    assert {entry["id"] for entry in document["deployment_renderers"]} == {
        "renderer.helm-kubernetes",
        "renderer.local-manifests",
    }
