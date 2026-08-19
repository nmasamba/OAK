# SPDX-License-Identifier: Apache-2.0
"""Deployment renderer determinism, safety, and replacement at the port."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.adapters.deployment import HelmKubernetesRenderer, LocalManifestRenderer
from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.rendering import DeploymentRenderService
from oak.domain import OAKError
from oak.domain.extension_sdk import (
    HELM_KUBERNETES_RENDERER_ID,
    LOCAL_MANIFEST_RENDERER_ID,
)
from tests.runner_support import build_compiled_case

pytestmark = pytest.mark.integration

FORBIDDEN_KEYS = {"command", "shell", "executable", "argv"}


@pytest.fixture(scope="module")
def compiled_case(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return build_compiled_case(tmp_path_factory.mktemp("render-case"))


def _service(harness: Any) -> DeploymentRenderService:
    return DeploymentRenderService(
        FileWorkspaceRepository(harness.workspace, harness.registry),
        {
            LOCAL_MANIFEST_RENDERER_ID: LocalManifestRenderer(),
            HELM_KUBERNETES_RENDERER_ID: HelmKubernetesRenderer(),
        },
    )


def _read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_both_renderers_render_the_same_case_at_the_same_port(
    compiled_case: Any, tmp_path: Path
) -> None:
    service = _service(compiled_case)
    local_files = service.render(LOCAL_MANIFEST_RENDERER_ID, tmp_path / "local")
    helm_files = service.render(HELM_KUBERNETES_RENDERER_ID, tmp_path / "helm")
    assert "manifests/deployment-bundle.json" in local_files
    assert "chart/Chart.yaml" in helm_files
    assert any(name.startswith("chart/templates/deployment-") for name in helm_files)
    case = FileWorkspaceRepository(compiled_case.workspace, compiled_case.registry).current_case()
    assert case is not None
    assert case["status"] == "bundle_compiled"


def test_renders_are_byte_identical_across_fresh_workspaces(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    first = build_compiled_case(tmp_path_factory.mktemp("render-a"))
    second = build_compiled_case(tmp_path_factory.mktemp("render-b"))
    out_a = tmp_path_factory.mktemp("out-a") / "render"
    out_b = tmp_path_factory.mktemp("out-b") / "render"
    _service(first).render(HELM_KUBERNETES_RENDERER_ID, out_a)
    _service(second).render(HELM_KUBERNETES_RENDERER_ID, out_b)
    assert _read_tree(out_a) == _read_tree(out_b)


def test_kubernetes_render_is_pinned_inert_and_egress_free(
    compiled_case: Any, tmp_path: Path
) -> None:
    output = tmp_path / "chart-out"
    _service(compiled_case).render(HELM_KUBERNETES_RENDERER_ID, output)
    tree = _read_tree(output)
    policy = yaml.safe_load(tree["chart/templates/networkpolicy.yaml"])
    assert policy["spec"]["egress"] == []
    assert "Egress" in policy["spec"]["policyTypes"]
    deployments = [
        yaml.safe_load(content)
        for name, content in tree.items()
        if name.startswith("chart/templates/deployment-")
    ]
    assert deployments
    for deployment in deployments:
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert "@sha256:" in container["image"]
        assert deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] is False

    def scan(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                assert str(key).casefold() not in FORBIDDEN_KEYS
                scan(nested)
        elif isinstance(value, list):
            for nested in value:
                scan(nested)

    for name, content in tree.items():
        if name.endswith((".yaml", ".yml")):
            scan(yaml.safe_load(content))
        assert b"secret" not in content.lower() or name == "RENDERING.md"


def test_unknown_renderer_and_existing_output_fail_closed(
    compiled_case: Any, tmp_path: Path
) -> None:
    service = _service(compiled_case)
    with pytest.raises(OAKError) as unknown:
        service.render("renderer.not-registered", tmp_path / "unknown")
    assert unknown.value.code == "OAK-RENDER-ADAPTER"
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(OAKError) as collision:
        service.render(LOCAL_MANIFEST_RENDERER_ID, existing)
    assert collision.value.code == "OAK-OUTPUT-EXISTS"


def test_renderer_identities_match_the_pinned_registry(compiled_case: Any) -> None:
    assert LocalManifestRenderer().identity()["id"] == LOCAL_MANIFEST_RENDERER_ID
    assert HelmKubernetesRenderer().identity()["id"] == HELM_KUBERNETES_RENDERER_ID
    assert _service(compiled_case).renderer_ids() == (
        HELM_KUBERNETES_RENDERER_ID,
        LOCAL_MANIFEST_RENDERER_ID,
    )
