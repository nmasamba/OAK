# SPDX-License-Identifier: Apache-2.0
"""Deterministic branch-ready GitOps output for a compiled, reviewed case.

Rendering is a pure function of canonical artifacts: identical case state
produces byte-identical files. Nothing here contacts a Git provider, and the
description states explicitly that promotion stays a human review action.
"""

from __future__ import annotations

import os
import shutil
import tempfile
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
        if output.exists() or output.is_symlink():
            raise OAKError("OAK-OUTPUT-EXISTS", "GitOps output directory already exists")
        approvals = self._approvals(case)
        parent = output.absolute().parent
        parent.mkdir(parents=True, exist_ok=True)
        # Staged beside the destination and renamed into place, so an interrupted render
        # leaves no partial directory that blocks the retry (F1-15).
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=parent))
        try:
            os.chmod(staging, 0o755)
            (staging / "manifests").mkdir()
            written = []
            for name, document in (
                ("manifests/deployment-bundle.json", bundle),
                ("manifests/runner-plan.json", plan),
                ("manifests/semantic-manifest.json", semantic),
                ("manifests/component-lock.json", {"components": bundle["component_lock"]}),
            ):
                _write(staging / name, canonical_json_bytes(document) + b"\n")
                written.append(name)
            description = _patch_description(
                case, bundle_ref, plan_ref, semantic_ref, bundle, approvals
            )
            _write(staging / "PATCH-DESCRIPTION.md", description.encode("utf-8"))
            written.append("PATCH-DESCRIPTION.md")
            if output.exists() or output.is_symlink():
                raise OAKError("OAK-OUTPUT-EXISTS", "GitOps output directory already exists")
            os.replace(staging, output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return tuple(written)

    def _approvals(self, case: dict[str, Any]) -> dict[str, dict[str, Any]]:
        references = case.get("extensions", {}).get("oak.community/approval_refs", {})
        if not isinstance(references, dict):
            return {}
        return {
            str(action): self._repository.read_json_artifact(
                ArtifactReference.from_document(reference)
            )
            for action, reference in references.items()
            if isinstance(reference, dict)
        }

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
    approvals: dict[str, dict[str, Any]],
) -> str:
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
    for action in ("dry_run", "architecture", "apply", "rollback", "destroy"):
        approval = approvals.get(action)
        if approval is None:
            continue
        # A revoked or expired approval used to read as "on file" (F4-10). Expiry is
        # stated as an instant, not judged against the clock, so the output stays
        # byte-identical across runs.
        if approval.get("revoked") is True:
            lines.append(f"- Approval for `{action}`: revoked at {approval.get('revoked_at')}")
        else:
            lines.append(
                f"- Approval for `{action}`: recorded, valid until {approval.get('expires_at')}; "
                "dispatch refuses it once expired"
            )
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
