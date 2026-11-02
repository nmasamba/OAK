# SPDX-License-Identifier: Apache-2.0
"""A synthetic older workspace format for the migration tests.

No published release wrote a manifest format other than the current one, so the chain the
package ships holds no step. These helpers invent one: format ``0.3.9`` is the current
format with a label kept on the manifest instead of on the design case. Its step moves the
label onto the case and, to exercise every rule a step is held to, re-records the intent at
a new version that names the format it was carried from. The stored intent and case stay
as they were; the application records the successor and the audit event.
"""

from __future__ import annotations

import copy
import json
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.domain import json_artifact
from oak.domain.artifacts import canonical_json_bytes
from oak.domain.design_case import next_patch_version
from oak.domain.workspace_format import FormatChain, FormatStep, ReadObject, StepResult

ROOT = Path(__file__).resolve().parents[1]
LEGACY_FORMAT = "0.3.9"
LEGACY_LABEL_KEY = "oak.community/legacy_label"
LABEL_KEY = "oak.community/label"
MIGRATED_FROM_KEY = "oak.community/migrated_from_format"
STEP_NAME = "legacy-label-into-case"
INTENT_MEDIA_TYPE = "application/vnd.oak.system-intent+json"


def write_legacy_workspace(workspace: Path, label: str = "legacy") -> bytes:
    """Rewrite a current-format workspace's manifest as format 0.3.9; return its bytes."""

    manifest_path = workspace / ".oak" / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema_version"] = LEGACY_FORMAT
    manifest["extensions"] = {**manifest.get("extensions", {}), LEGACY_LABEL_KEY: label}
    content = canonical_json_bytes(manifest)
    manifest_path.write_bytes(content)
    return content


def _apply(manifest: dict[str, Any], read: ReadObject) -> StepResult:
    migrated = copy.deepcopy(manifest)
    migrated["schema_version"] = "0.4.0"
    label = migrated["extensions"].pop(LEGACY_LABEL_KEY)
    reference = migrated.get("current_case_ref")
    if reference is None:
        return StepResult(manifest=migrated)
    case = json.loads(read(reference["digest"]))
    new_artifacts: tuple[Any, ...] = ()
    intent_reference = case.get("intent_ref")
    if intent_reference is not None:
        intent = json.loads(read(intent_reference["digest"]))
        old_version = str(intent["version"])
        intent["version"] = next_patch_version(old_version)
        intent["supersedes"] = f"{intent['id']}@{old_version}"
        intent["extensions"][MIGRATED_FROM_KEY] = LEGACY_FORMAT
        artifact = json_artifact(
            artifact_id=str(intent["id"]),
            version=str(intent["version"]),
            kind="system_intent",
            media_type=INTENT_MEDIA_TYPE,
            document=intent,
        )
        migrated["artifact_index"] = sorted(
            [*migrated["artifact_index"], artifact.index_document()],
            key=lambda item: (str(item["kind"]), str(item["id"]), str(item["version"])),
        )
        case["intent_ref"] = artifact.reference.to_document()
        new_artifacts = (artifact,)
    case["extensions"] = {**case.get("extensions", {}), LABEL_KEY: label}
    return StepResult(manifest=migrated, new_artifacts=new_artifacts, case_document=case)


SYNTHETIC_STEP = FormatStep(
    from_format=LEGACY_FORMAT, to_format="0.4.0", name=STEP_NAME, apply=_apply
)
SYNTHETIC_CHAIN = FormatChain((SYNTHETIC_STEP,))


def install_synthetic_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every bootstrap factory build its file repository with the synthetic chain."""

    import oak.bootstrap

    monkeypatch.setattr(
        oak.bootstrap,
        "FileWorkspaceRepository",
        partial(FileWorkspaceRepository, chain=SYNTHETIC_CHAIN),
    )


def migrate_with_synthetic_chain(workspace: Path, *, occurred_at: str) -> None:
    """Run the migration with a fixed clock, as the two-interpreter test does."""

    from oak.application.context import CommandContext
    from oak.application.workspace_format import WorkspaceFormatService
    from oak.contracts import SchemaRegistry

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(workspace, registry, chain=SYNTHETIC_CHAIN)
    WorkspaceFormatService(repository, registry).migrate(
        CommandContext(
            actor="local-user",
            tenant_id="local",
            idempotency_key="",
            expected_version=None,
            correlation_id="",
            interface_origin="cli",
            occurred_at=occurred_at,
        )
    )
