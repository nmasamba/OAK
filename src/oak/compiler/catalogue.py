# SPDX-License-Identifier: Apache-2.0
"""Deterministic catalogue eligibility and snapshot compilation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import Artifact, OAKError, json_artifact

MANIFEST_MEDIA_TYPE = "application/vnd.oak.component-manifest+json"
PATTERN_MEDIA_TYPE = "application/vnd.oak.architecture-pattern+json"
SNAPSHOT_MEDIA_TYPE = "application/vnd.oak.catalogue-snapshot+json"
ALLOWED_AVAILABILITY = frozenset({"osi_open_source_software", "osi_open_source_ai"})
DISALLOWED_LICENCE_CLASSES = frozenset({"restricted", "source_available", "proprietary", "unknown"})


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
) -> CompiledCatalogue:
    valid_at = _timestamp(created_at)
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
        reasons = _eligibility_reasons(document, valid_at)
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
        "policy_version": "community-open-components-1.0.0",
        "entries": entries,
        "eligible_manifest_ids": eligible_ids,
        "rejected_manifest_ids": rejected_ids,
        "extensions": {},
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


def _eligibility_reasons(document: dict[str, Any], valid_at: datetime) -> tuple[str, ...]:
    reasons: list[str] = []
    if document["status"] not in {"eligible", "approved_for_context"}:
        reasons.append("OAK-CAT-STATUS-NOT-ELIGIBLE")
    if document["availability_class"] not in ALLOWED_AVAILABILITY:
        reasons.append("OAK-CAT-AVAILABILITY-BLOCKED")
    if _timestamp(str(document["next_review_at"])) <= valid_at:
        reasons.append("OAK-CAT-EVIDENCE-STALE")
    if document["security"]["known_vulnerabilities"]:
        reasons.append("OAK-CAT-KNOWN-VULNERABILITY")
    if document["licensing"]["transitive_review"] != "passed":
        reasons.append("OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED")
    for domain in ("software", "model", "data"):
        licence = document["licensing"][domain]
        if licence["classification"] in DISALLOWED_LICENCE_CLASSES:
            reasons.append(f"OAK-CAT-{domain.upper()}-LICENCE-BLOCKED")
        if licence["review_status"] not in {"passed", "not_applicable"}:
            reasons.append(f"OAK-CAT-{domain.upper()}-LICENCE-UNREVIEWED")
    for evidence in document["evidence"]:
        if evidence["content_digest"] is None:
            reasons.append("OAK-CAT-EVIDENCE-UNDIGESTED")
        if _timestamp(str(evidence["checked_at"])) > valid_at:
            reasons.append("OAK-CAT-EVIDENCE-FUTURE")
    return tuple(sorted(set(reasons)))


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
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OAKError("OAK-CATALOGUE-TIME", "catalogue timestamp is invalid") from error
