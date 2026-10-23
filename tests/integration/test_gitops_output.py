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


def test_the_description_states_each_approval_and_never_lists_a_revoked_one_as_on_file(
    tmp_path: Path,
) -> None:
    """F4-10: a revoked approval used to read "Approval on file"."""

    harness = build_compiled_case(tmp_path)
    harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
    harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
    harness.release.revoke_approval(
        "dry_run", "drill", harness.context("revoke-dryrun-00001", "0.1.9")
    )
    output = tmp_path / "gitops"
    _render(harness.workspace, harness.registry, output)
    description = (output / "PATCH-DESCRIPTION.md").read_text(encoding="utf-8")
    assert "on file" not in description
    assert "- Approval for `dry_run`: revoked at " in description


def test_an_interrupted_render_leaves_nothing_behind(tmp_path: Path, monkeypatch) -> None:
    """F1-15: the output is staged and renamed into place."""

    import oak.application.gitops as gitops

    harness = build_compiled_case(tmp_path)
    calls = {"count": 0}
    real_write = gitops._write

    def interrupted(path: Path, content: bytes) -> None:
        calls["count"] += 1
        if calls["count"] == 3:
            raise KeyboardInterrupt
        real_write(path, content)

    monkeypatch.setattr(gitops, "_write", interrupted)
    output = tmp_path / "gitops"
    with pytest.raises(KeyboardInterrupt):
        _render(harness.workspace, harness.registry, output)
    assert not output.exists()
    assert [path.name for path in tmp_path.iterdir() if path.name.startswith(".gitops")] == []
    monkeypatch.setattr(gitops, "_write", real_write)
    assert _render(harness.workspace, harness.registry, output)
