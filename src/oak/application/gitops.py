# SPDX-License-Identifier: Apache-2.0
"""Deterministic branch-ready GitOps output for a compiled, reviewed case.

Rendering is a pure function of canonical artifacts: identical case state
produces byte-identical files. Nothing here contacts a Git provider, and the
description states explicitly that promotion stays a human review action.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from oak.domain import ArtifactReference, OAKError, canonical_json_bytes
from oak.ports import WorkspaceRepository


class GitOpsRenderer:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    def render(self, output: Path) -> tuple[str, ...]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        bundle_ref = self._reference(case, "deployment_bundle_ref")
        plan_ref = self._reference(case, "runner_plan_ref")
        bundle = self._repository.read_json_artifact(bundle_ref)
        plan = self._repository.read_json_artifact(plan_ref)
        semantic_ref = ArtifactReference.from_document(
            case["extensions"]["oak.community/semantic_manifest_ref"]
        )
        semantic = self._repository.read_json_artifact(semantic_ref)
        if output.exists():
            raise OAKError("OAK-OUTPUT-EXISTS", "GitOps output directory already exists")
        output.mkdir(parents=True, mode=0o755)
        (output / "manifests").mkdir()
        written = []
        for name, document in (
            ("manifests/deployment-bundle.json", bundle),
            ("manifests/runner-plan.json", plan),
            ("manifests/semantic-manifest.json", semantic),
            ("manifests/component-lock.json", {"components": bundle["component_lock"]}),
        ):
            path = output / name
            _write(path, canonical_json_bytes(document) + b"\n")
            written.append(name)
        description = _patch_description(case, bundle_ref, plan_ref, semantic_ref, bundle)
        _write(output / "PATCH-DESCRIPTION.md", description.encode("utf-8"))
        written.append("PATCH-DESCRIPTION.md")
        return tuple(written)

    @staticmethod
    def _reference(case: dict[str, Any], field: str) -> ArtifactReference:
        value = case.get(field)
        if not isinstance(value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", f"case has no {field}")
        return ArtifactReference.from_document(value)


def _patch_description(
    case: dict[str, Any],
    bundle_ref: ArtifactReference,
    plan_ref: ArtifactReference,
    semantic_ref: ArtifactReference,
    bundle: dict[str, Any],
) -> str:
    approvals = case.get("extensions", {}).get("oak.community/approval_refs", {})
    signature = case.get("extensions", {}).get("oak.community/plan_signature_ref")
    lines = [
        "<!-- SPDX-License-Identifier: Apache-2.0 -->",
        "",
        f"# Architecture change: {case['title']}",
        "",
        f"Design case `{case['id']}` at version `{case['version']}` ({case['status']}).",
        "",
        "## Immutable content",
        "",
        f"- Deployment bundle `{bundle_ref.id}` — `{bundle_ref.digest}`",
        f"- Runner plan `{plan_ref.id}` — `{plan_ref.digest}`",
        f"- Semantic manifest `{semantic_ref.id}` — `{semantic_ref.digest}`",
        "",
        "## Component lock",
        "",
    ]
    for component in bundle["component_lock"]:
        lines.append(
            f"- `{component['manifest_id']}` {component['version']} — "
            f"`{component['digest']}` ({component['licence_decision']})"
        )
    lines += [
        "",
        "## Review lineage",
        "",
        f"- Plan signature: {'recorded' if isinstance(signature, dict) else 'not recorded'}",
    ]
    for action in ("dry_run", "apply", "rollback", "destroy"):
        if isinstance(approvals, dict) and action in approvals:
            lines.append(f"- Approval on file for `{action}`")
    lines += [
        "",
        "## Promotion",
        "",
        "Merging this change is a human review decision. Nothing in this output",
        "promotes automatically, and no runner gains authority from the merge",
        "itself: dispatch still requires the signed envelope and current",
        "digest-bound approvals.",
        "",
    ]
    return "\n".join(lines)


def _write(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
