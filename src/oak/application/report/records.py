# SPDX-License-Identifier: Apache-2.0
"""Read every record a report draws on, through the repository port.

Each read goes by `{id, version, digest}`, so a record whose bytes changed is refused by
the repository, never reported. The records are read from the current case version; the
list of what was read becomes the report's record appendix. The research records
(ADR-0018) are reached through the catalogue snapshot the selected candidate names, never
through the case's latest research, so a report describes the research its design was
generated against.
"""

from __future__ import annotations

from typing import Any

from oak.application.report.composer import ReportRecords
from oak.domain import ArtifactReference, OAKError
from oak.ports import WorkspaceRepository

COMPONENT_MEDIA_TYPE = "application/vnd.oak.component-manifest+json"
CATALOGUE_SNAPSHOT_EXTENSION = "oak.community/catalogue_snapshot_ref"
RESEARCH_EXTENSION = "oak.community/research"
RESEARCH_REVIEW_REFS = "oak.community/research_review_refs"
_CASE_FIELDS = (
    "evaluation_contract_ref",
    "assurance_plan_ref",
    "deployment_bundle_ref",
    "regulatory_nexus_ref",
    "decision_cost_model_ref",
)


class _Reader:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository
        index = repository.manifest()["artifact_index"]
        self._kinds = {(str(item["id"]), str(item["version"])): str(item["kind"]) for item in index}
        self.inputs: list[dict[str, Any]] = []
        self._seen: set[tuple[str, str]] = set()

    def read(self, reference: Any) -> dict[str, Any] | None:
        if not isinstance(reference, dict):
            return None
        artifact_ref = ArtifactReference.from_document(reference)
        document = self._repository.read_json_artifact(artifact_ref)
        key = (artifact_ref.id, artifact_ref.version)
        if key not in self._seen:
            self._seen.add(key)
            self.inputs.append(
                {
                    "kind": self._kinds.get(key, "unknown"),
                    "id": artifact_ref.id,
                    "version": artifact_ref.version,
                    "digest": artifact_ref.digest,
                    "media_type": artifact_ref.media_type,
                }
            )
        return document

    def read_all(self, references: Any) -> tuple[dict[str, Any], ...]:
        if not isinstance(references, list):
            return ()
        return tuple(
            document for reference in references if (document := self.read(reference)) is not None
        )


def _research_reference(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """The research snapshot a catalogue snapshot was merged from, if any."""

    if snapshot is None:
        return None
    research = (snapshot.get("extensions") or {}).get(RESEARCH_EXTENSION)
    reference = research.get("research_snapshot_ref") if isinstance(research, dict) else None
    return reference if isinstance(reference, dict) else None


def gather_records(repository: WorkspaceRepository) -> ReportRecords:
    """The current case and everything its report reads, each checked by digest."""

    manifest = repository.manifest()
    case_ref = manifest.get("current_case_ref")
    if not isinstance(case_ref, dict):
        raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
    reader = _Reader(repository)
    case = reader.read(case_ref)
    assert case is not None
    intent = reader.read(case.get("intent_ref"))
    if intent is None:
        raise OAKError("OAK-DEPENDENCY-MISSING", "the case has no interpreted intent")
    extensions = case.get("extensions") or {}
    candidates = reader.read_all(case.get("candidate_refs"))
    patterns: dict[str, dict[str, Any]] = {}
    components: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        pattern = reader.read((candidate.get("extensions") or {}).get("oak.community/pattern_ref"))
        if pattern is not None:
            patterns[str(pattern["id"])] = pattern
    selected_id = (case.get("selected_candidate_ref") or {}).get("id")
    selected: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate.get("id") != selected_id:
            continue
        selected = candidate
        for component in candidate.get("components") or []:
            reference = {
                "id": component.get("manifest_id"),
                "version": component.get("version"),
                "digest": component.get("digest"),
                "media_type": COMPONENT_MEDIA_TYPE,
            }
            manifest_document = reader.read(reference)
            if manifest_document is not None:
                components[f"{reference['id']}@{reference['version']}"] = manifest_document
    documents = {field: reader.read(case.get(field)) for field in _CASE_FIELDS}
    approvals_refs = extensions.get("oak.community/approval_refs") or {}
    approvals = {
        str(action): document
        for action in sorted(approvals_refs)
        if (document := reader.read(approvals_refs[action])) is not None
    }
    decision = reader.read(extensions.get("oak.community/selection_decision_ref"))
    evaluations = reader.read_all(extensions.get("oak.community/evaluation_refs"))
    # The catalogue snapshot the selected design was generated against, else the case's.
    snapshot_ref = (
        (selected.get("extensions") or {}).get(CATALOGUE_SNAPSHOT_EXTENSION)
        if selected is not None
        else None
    ) or extensions.get(CATALOGUE_SNAPSHOT_EXTENSION)
    snapshot = reader.read(snapshot_ref)
    policy_decisions = reader.read_all(extensions.get("oak.community/policy_decision_refs"))
    observations = reader.read_all(extensions.get("oak.community/observation_refs"))
    proposal = reader.read(
        (intent.get("extensions") or {}).get("oak.community/interpretation_proposal_ref")
    )
    # Research (ADR-0018): the snapshot the design's catalogue names, every manifest it
    # produced, and the reviews bound to its digest; nothing from a later run.
    research_ref = _research_reference(snapshot)
    research = reader.read(research_ref)
    research_manifests: dict[str, dict[str, Any]] = {}
    research_reviews: tuple[dict[str, Any], ...] = ()
    if research is not None and research_ref is not None:
        for item in research.get("items") or []:
            manifest_document = reader.read(item.get("manifest_ref"))
            if manifest_document is not None:
                research_manifests[str(item.get("id"))] = manifest_document
        research_reviews = tuple(
            review
            for review in reader.read_all(extensions.get(RESEARCH_REVIEW_REFS))
            if (review.get("snapshot_ref") or {}).get("digest") == research_ref.get("digest")
        )
    return ReportRecords(
        case=case,
        case_ref=dict(case_ref),
        intent=intent,
        candidates=candidates,
        patterns=patterns,
        decision=decision,
        contract=documents["evaluation_contract_ref"],
        evaluations=evaluations,
        assurance_plan=documents["assurance_plan_ref"],
        bundle=documents["deployment_bundle_ref"],
        components=components,
        snapshot=snapshot,
        policy_decisions=policy_decisions,
        approvals=approvals,
        observations=observations,
        regulatory_nexus=documents["regulatory_nexus_ref"],
        cost_model=documents["decision_cost_model_ref"],
        proposal=proposal,
        research=research,
        research_manifests=research_manifests,
        research_reviews=research_reviews,
        inputs=tuple(reader.inputs),
    )
