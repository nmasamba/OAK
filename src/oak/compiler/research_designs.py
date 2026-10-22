# SPDX-License-Identifier: Apache-2.0
"""Researched designs: at most one per curated pattern with a model role (ADR-0018).

Pure. From a research snapshot, the recorded reviews, the research bindings and the merged
catalogue it builds, deterministically, the pattern each researched design is compiled
from: the curated pattern with its model role filled by the newest passing researched
model, and one added serving role when a passing harness's release notes name that
model's family. The curated patterns are never edited; the ids run from `candidate-05`
in pattern-id order; the curated loader never sees a binding.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from oak.domain import OAKError

RESEARCHED_FIRST_ID = 5
LABEL_SUFFIX = "new"
SERVING_PURPOSE = "Serve the researched model"


@dataclass(frozen=True, slots=True)
class ResearchedDesign:
    candidate_id: str
    pattern_id: str
    pattern: dict[str, Any]
    research: dict[str, Any]


def effective_verdicts(snapshot: dict[str, Any], reviews: dict[str, str]) -> dict[str, str]:
    """Each verdict after the reviews: an accept lifts `needs_review`, a reject fails it."""

    verdicts: dict[str, str] = {}
    for item in snapshot["items"]:
        verdict = str(item["verdict"])
        review = reviews.get(str(item["id"]))
        if review == "reject":
            verdict = "failed"
        elif review == "accept" and verdict == "needs_review":
            verdict = "passed"
        verdicts[str(item["id"])] = verdict
    return verdicts


def passing_manifest_ids(snapshot: dict[str, Any], verdicts: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item["manifest_ref"]["id"])
            for item in snapshot["items"]
            if verdicts.get(str(item["id"])) == "passed"
            and isinstance(item.get("manifest_ref"), dict)
        )
    )


def researched_designs(
    snapshot: dict[str, Any],
    verdicts: dict[str, str],
    bindings: tuple[dict[str, Any], ...],
    patterns: dict[str, dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    *,
    snapshot_ref: dict[str, Any],
) -> tuple[ResearchedDesign, ...]:
    items = {str(item["id"]): item for item in snapshot["items"]}
    models = [
        item
        for item in snapshot["items"]
        if item["kind"] == "model"
        and verdicts.get(str(item["id"])) == "passed"
        and isinstance(item.get("manifest_ref"), dict)
        and str(item["manifest_ref"]["id"]) in manifests
    ]
    # Newest first by Hub creation date, ties broken by id (a stable sort on id, then date).
    models.sort(key=lambda item: str(item["id"]))
    models.sort(key=lambda item: str(item.get("created_or_released_at") or ""), reverse=True)
    harness_for_model: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for pairing in sorted(snapshot["pairings"], key=lambda p: str(p["harness_item_id"])):
        harness = items.get(str(pairing["harness_item_id"]))
        if (
            harness is None
            or verdicts.get(str(harness["id"])) != "passed"
            or not isinstance(harness.get("manifest_ref"), dict)
            or str(harness["manifest_ref"]["id"]) not in manifests
        ):
            continue
        harness_for_model.setdefault(str(pairing["model_item_id"]), (harness, pairing))
    designs: list[ResearchedDesign] = []
    for binding in sorted(bindings, key=lambda b: str(b["pattern_id"])):
        pattern = patterns.get(str(binding["pattern_id"]))
        if pattern is None:
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research binding names an unknown pattern")
        roles = {str(role["id"]): role for role in pattern["roles"]}
        model_role = roles[str(binding["model_role_id"])]
        capability = str(model_role["required_capability"])
        chosen = next(
            (
                item
                for item in models
                if capability
                in manifests[str(item["manifest_ref"]["id"])]["extensions"].get(
                    "oak.community/capabilities", []
                )
            ),
            None,
        )
        if chosen is None:
            continue
        model_manifest = manifests[str(chosen["manifest_ref"]["id"])]
        design_pattern = copy.deepcopy(pattern)
        requirements = []
        for requirement in design_pattern["component_requirements"]:
            if str(requirement["role_id"]) == str(binding["model_role_id"]):
                requirement = {**requirement, "manifest_id": str(model_manifest["id"])}
            requirements.append(requirement)
        research: dict[str, Any] = {
            "research_snapshot_ref": snapshot_ref,
            "binding_id": str(binding["id"]),
            "label_suffix": LABEL_SUFFIX,
            "model_item_id": str(chosen["id"]),
            "model_source": str(chosen["source"]),
            "model_source_id": str(chosen["source_id"]),
            "model_created_at": chosen.get("created_or_released_at"),
            "model_tier": str(chosen["tier"]),
            "harness_item_id": None,
            "harness_source_id": None,
            "harness_released_at": None,
            "harness_tier": None,
            "pairing_claim_classes": [],
            "evidence_classes": sorted(
                {str(claim["evidence_class"]) for claim in chosen["claims"]}
            ),
        }
        paired = harness_for_model.get(str(chosen["id"]))
        if paired is not None:
            harness, pairing = paired
            harness_manifest = manifests[str(harness["manifest_ref"]["id"])]
            design_pattern["roles"].append(copy.deepcopy(binding["serving_role"]))
            design_pattern["edges"].append(copy.deepcopy(binding["serving_edge"]))
            requirements.append(
                {
                    "role_id": str(binding["serving_role"]["id"]),
                    "manifest_id": str(harness_manifest["id"]),
                    "purpose": SERVING_PURPOSE,
                    "required": True,
                }
            )
            research.update(
                {
                    "harness_item_id": str(harness["id"]),
                    "harness_source_id": str(harness["source_id"]),
                    "harness_released_at": harness.get("created_or_released_at"),
                    "harness_tier": str(harness["tier"]),
                    "pairing_claim_classes": list(pairing["claim_classes"]),
                    "evidence_classes": sorted(
                        set(research["evidence_classes"])
                        | {str(claim["evidence_class"]) for claim in harness["claims"]}
                    ),
                }
            )
        design_pattern["component_requirements"] = requirements
        designs.append(
            ResearchedDesign(
                candidate_id=f"candidate-{RESEARCHED_FIRST_ID + len(designs):02d}",
                pattern_id=str(pattern["id"]),
                pattern=design_pattern,
                research=research,
            )
        )
    return tuple(designs)
