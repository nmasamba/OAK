# SPDX-License-Identifier: Apache-2.0
"""Deterministic catalogue eligibility and snapshot compilation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import (
    CURATED_RULES_VERSION,
    RESEARCH_GATES_VERSION,
    Artifact,
    OAKError,
    json_artifact,
)
from oak.domain.catalogue_rules import (
    catalogue_timestamp,
    eligibility_reasons,
)

MANIFEST_MEDIA_TYPE = "application/vnd.oak.component-manifest+json"
PATTERN_MEDIA_TYPE = "application/vnd.oak.architecture-pattern+json"
SNAPSHOT_MEDIA_TYPE = "application/vnd.oak.catalogue-snapshot+json"


# Curated reasons that still make a researched manifest ineligible (ADR-0018); every other
# curated reason is kept on its entry as a visible review item.
BLOCKING_REVIEW_ITEMS = frozenset({"OAK-CAT-KNOWN-VULNERABILITY", "OAK-CAT-EVIDENCE-FUTURE"})


@dataclass(frozen=True, slots=True)
class ResearchInput:
    """What a merged compile needs: the snapshot it merges and the manifests that passed."""

    snapshot_ref: dict[str, Any]
    snapshot_version: str
    case_key: str
    researched_manifest_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class CompiledCatalogue:
    snapshot: Artifact
    manifests: tuple[Artifact, ...]
    patterns: tuple[Artifact, ...]
    manifest_documents: dict[str, dict[str, Any]]
    pattern_documents: dict[str, dict[str, Any]]
    eligibility: dict[str, tuple[bool, tuple[str, ...]]]


def compile_catalogue(
    manifests_input: tuple[dict[str, Any], ...],
    patterns_input: tuple[dict[str, Any], ...],
    registry: SchemaRegistry,
    *,
    created_at: str,
    research: ResearchInput | None = None,
) -> CompiledCatalogue:
    valid_at = _timestamp(created_at)
    researched_ids = research.researched_manifest_ids if research is not None else frozenset()
    manifests: list[Artifact] = []
    entries: list[dict[str, Any]] = []
    manifest_documents: dict[str, dict[str, Any]] = {}
    eligibility: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for document in sorted(manifests_input, key=lambda item: str(item["id"])):
        registry.validate("component-manifest.schema.json", document)
        manifest_id = str(document["id"])
        if manifest_id in manifest_documents:
            raise OAKError("OAK-CATALOGUE-DUPLICATE", "component manifest ID is duplicated")
        artifact = json_artifact(
            artifact_id=manifest_id,
            version=str(document["release"]["version"]),
            kind="component_manifest",
            media_type=MANIFEST_MEDIA_TYPE,
            document=document,
        )
        reasons = eligibility_reasons(document, valid_at)
        if manifest_id in researched_ids:
            # Eligibility for comparison was decided by community-research-gates-1.0.0; the
            # curated reasons stay on the entry as review items, and only a blocked licence,
            # a known vulnerability or future-dated evidence still makes it ineligible.
            eligible = not any(
                reason in BLOCKING_REVIEW_ITEMS or reason.endswith("-LICENCE-BLOCKED")
                for reason in reasons
            )
        else:
            eligible = not reasons
        evidence_checked_at = max(str(item["checked_at"]) for item in document["evidence"])
        entries.append(
            {
                "manifest_ref": artifact.reference.to_document(),
                "category": document["category"],
                "availability_class": document["availability_class"],
                "eligible": eligible,
                "reasons": list(reasons),
                "evidence_checked_at": evidence_checked_at,
                "next_review_at": document["next_review_at"],
            }
        )
        manifests.append(artifact)
        manifest_documents[manifest_id] = document
        eligibility[manifest_id] = (eligible, reasons)

    patterns: list[Artifact] = []
    pattern_documents: dict[str, dict[str, Any]] = {}
    pattern_variants: set[str] = set()
    for document in sorted(patterns_input, key=lambda item: str(item["id"])):
        registry.validate("architecture-pattern.schema.json", document)
        pattern_id = str(document["id"])
        if pattern_id in pattern_documents:
            raise OAKError("OAK-CATALOGUE-DUPLICATE", "architecture pattern ID is duplicated")
        variant = str(document["variant"])
        if variant in pattern_variants:
            raise OAKError("OAK-CATALOGUE-DUPLICATE", "architecture pattern variant is duplicated")
        _validate_pattern(document, manifest_documents)
        artifact = json_artifact(
            artifact_id=pattern_id,
            version=str(document["version"]),
            kind="architecture_pattern",
            media_type=PATTERN_MEDIA_TYPE,
            document=document,
        )
        patterns.append(artifact)
        pattern_documents[pattern_id] = document
        pattern_variants.add(variant)

    if not any(eligible for eligible, _reasons in eligibility.values()):
        raise OAKError("OAK-CATALOGUE-INELIGIBLE", "catalogue has no eligible manifests")
    eligible_ids = sorted(
        manifest_id for manifest_id, (eligible, _reasons) in eligibility.items() if eligible
    )
    rejected_ids = sorted(
        manifest_id for manifest_id, (eligible, _reasons) in eligibility.items() if not eligible
    )
    snapshot_document = {
        "schema_version": "0.4.0",
        "id": "catalogue.community-fixture",
        "version": "0.1.0",
        "created_at": created_at,
        "valid_at": created_at,
        "policy_version": CURATED_RULES_VERSION,
        "entries": entries,
        "eligible_manifest_ids": eligible_ids,
        "rejected_manifest_ids": rejected_ids,
        "extensions": {},
    }
    if research is not None:
        # A merged snapshot has its own identity, so the curated one's bytes never move and
        # the workspace never sees a second digest for catalogue.community-fixture@0.1.0.
        snapshot_document["id"] = f"catalogue.research.{research.case_key}"
        snapshot_document["version"] = research.snapshot_version
        snapshot_document["extensions"] = {
            "oak.community/research": {
                "rule_set": RESEARCH_GATES_VERSION,
                "research_snapshot_ref": research.snapshot_ref,
                "researched_manifest_ids": sorted(researched_ids),
            }
        }
    registry.validate("catalogue-snapshot.schema.json", snapshot_document)
    snapshot = json_artifact(
        artifact_id=str(snapshot_document["id"]),
        version=str(snapshot_document["version"]),
        kind="catalogue_snapshot",
        media_type=SNAPSHOT_MEDIA_TYPE,
        document=snapshot_document,
    )
    return CompiledCatalogue(
        snapshot=snapshot,
        manifests=tuple(manifests),
        patterns=tuple(patterns),
        manifest_documents=manifest_documents,
        pattern_documents=pattern_documents,
        eligibility=eligibility,
    )


def _validate_pattern(pattern: dict[str, Any], manifests: dict[str, dict[str, Any]]) -> None:
    roles = {str(role["id"]): role for role in pattern["roles"]}
    if len(roles) != len(pattern["roles"]):
        raise OAKError("OAK-CATALOGUE-PATTERN", "architecture pattern roles are duplicated")
    requirements = {
        str(requirement["role_id"]): requirement
        for requirement in pattern["component_requirements"]
    }
    if len(requirements) != len(pattern["component_requirements"]) or set(requirements) != set(
        roles
    ):
        raise OAKError(
            "OAK-CATALOGUE-PATTERN",
            "every architecture role must have exactly one component requirement",
        )
    for edge in pattern["edges"]:
        if str(edge["from"]) not in roles or str(edge["to"]) not in roles:
            raise OAKError("OAK-CATALOGUE-PATTERN", "architecture edge references an unknown role")
    for role_id, requirement in requirements.items():
        manifest = manifests.get(str(requirement["manifest_id"]))
        if manifest is None:
            raise OAKError(
                "OAK-CATALOGUE-PATTERN",
                "architecture pattern references a missing component manifest",
            )
        role = roles[role_id]
        capabilities = manifest["extensions"].get("oak.community/capabilities", [])
        if (
            manifest["category"] != role["component_category"]
            or role["required_capability"] not in capabilities
        ):
            raise OAKError(
                "OAK-CATALOGUE-PATTERN",
                "component does not satisfy its declared provider-neutral role",
            )


def _timestamp(value: str) -> datetime:
    return catalogue_timestamp(value)
