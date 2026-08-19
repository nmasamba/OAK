# SPDX-License-Identifier: Apache-2.0
"""OAK-S6-007: swap policy and deployment adapters without changing canonical meaning."""

import shutil
from typing import Any

import pytest

from oak.adapters.deployment import HelmKubernetesRenderer, LocalManifestRenderer
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.policies import BuiltinPolicyEngine, LocalPolicyPackStore
from oak.adapters.policies.opa import OpaPolicyEngine
from oak.application.policy import PolicyService
from oak.application.rendering import DeploymentRenderService
from oak.domain import canonical_json_bytes, content_digest
from oak.domain.extension_sdk import (
    HELM_KUBERNETES_RENDERER_ID,
    LOCAL_MANIFEST_RENDERER_ID,
)
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

PACK_ID = "pack.community-baseline"


def _policy_service(harness: Any) -> PolicyService:
    return PolicyService(
        FileWorkspaceRepository(harness.workspace, harness.registry),
        harness.registry,
        LocalPolicyPackStore((ROOT / "policy-packs",), harness.registry),
        {"builtin": BuiltinPolicyEngine, "opa": OpaPolicyEngine},
    )


@pytest.mark.skipif(
    shutil.which("opa") is None,
    reason="the optional opa binary is not installed; the built-in engine is authoritative",
)
def test_swapping_the_policy_engine_preserves_the_canonical_decision(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    builtin_case = build_compiled_case(tmp_path_factory.mktemp("swap-builtin"))
    opa_case = build_compiled_case(tmp_path_factory.mktemp("swap-opa"))
    builtin_decision = (
        _policy_service(builtin_case)
        .evaluate(PACK_ID, builtin_case.context("swap-engine-builtin-1", "0.1.7"))
        .decision
    )
    opa_decision = (
        _policy_service(opa_case)
        .evaluate(PACK_ID, opa_case.context("swap-engine-builtin-1", "0.1.7"), engine="opa")
        .decision
    )
    assert canonical_json_bytes(builtin_decision) == canonical_json_bytes(opa_decision)
    assert "engine" not in builtin_decision


def test_swapping_the_deployment_renderer_changes_target_artifacts_only(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    harness = build_compiled_case(tmp_path_factory.mktemp("swap-render"))
    repository = FileWorkspaceRepository(harness.workspace, harness.registry)
    case_before = repository.current_case()
    assert case_before is not None
    case_digest_before = content_digest(canonical_json_bytes(case_before))
    semantic_ref_before = case_before["extensions"]["oak.community/semantic_manifest_ref"]
    manifest_version_before = repository.manifest()["version"]

    service = DeploymentRenderService(
        repository,
        {
            LOCAL_MANIFEST_RENDERER_ID: LocalManifestRenderer(),
            HELM_KUBERNETES_RENDERER_ID: HelmKubernetesRenderer(),
        },
    )
    out = tmp_path_factory.mktemp("swap-out")
    local_files = set(service.render(LOCAL_MANIFEST_RENDERER_ID, out / "local"))
    helm_files = set(service.render(HELM_KUBERNETES_RENDERER_ID, out / "helm"))

    assert local_files != helm_files, "swapping renderers must change target artifacts"
    case_after = repository.current_case()
    assert case_after is not None
    assert content_digest(canonical_json_bytes(case_after)) == case_digest_before
    assert case_after["extensions"]["oak.community/semantic_manifest_ref"] == (semantic_ref_before)
    assert repository.manifest()["version"] == manifest_version_before
