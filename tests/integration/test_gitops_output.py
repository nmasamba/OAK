# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-010 deterministic GitOps output and non-promotion."""

from pathlib import Path

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.gitops import GitOpsRenderer
from tests.runner_support import build_compiled_case

pytestmark = pytest.mark.integration


def _render(workspace: Path, registry, output: Path) -> tuple[str, ...]:
    return GitOpsRenderer(FileWorkspaceRepository(workspace, registry)).render(output)


def test_gitops_output_is_byte_identical_across_runs(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    first = tmp_path / "gitops-a"
    second = tmp_path / "gitops-b"
    written_a = _render(harness.workspace, harness.registry, first)
    written_b = _render(harness.workspace, harness.registry, second)
    assert written_a == written_b
    for name in written_a:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_patch_description_states_promotion_is_manual(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    output = tmp_path / "gitops"
    _render(harness.workspace, harness.registry, output)
    description = (output / "PATCH-DESCRIPTION.md").read_text(encoding="utf-8")
    assert "human review decision" in description
    assert "promotes automatically" in description
    lowered = description.casefold()
    assert "component lock" in lowered
    manifests = output / "manifests"
    assert (manifests / "deployment-bundle.json").is_file()
    assert (manifests / "runner-plan.json").is_file()


def test_gitops_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    output = tmp_path / "gitops"
    _render(harness.workspace, harness.registry, output)
    from oak.domain import OAKError

    with pytest.raises(OAKError) as caught:
        _render(harness.workspace, harness.registry, output)
    assert caught.value.code == "OAK-OUTPUT-EXISTS"
