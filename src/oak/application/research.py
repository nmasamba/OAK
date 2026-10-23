# SPDX-License-Identifier: Apache-2.0
"""Research at the point of design: the plan, the consented run and the recorded review.

Sprint 14 (ADR-0018). `plan` is a read: the hosts, the derived terms and their digest for
the case's current intent, which the consent card shows verbatim. `run` sends those terms
once the caller's consent names the same hosts and digest, writes the `research_snapshot`
and every researched manifest, sets `oak.community/research_snapshot_ref`, revises the
case at its own status and appends `research_completed`. `review` records one human
decision about an unvetted item as a `research_review`, bound to the snapshot's digest and
the item's response digest. Nothing here approves, selects or installs anything, and the
research is allowed only while the case is `ready_for_candidates`.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.compiler import derive_research_terms, terms_digest
from oak.contracts import SchemaRegistry
from oak.domain import (
    RESEARCH_REVIEW_MEDIA_TYPE,
    RESEARCH_REVIEW_REFS,
    RESEARCH_SNAPSHOT_MEDIA_TYPE,
    RESEARCH_SNAPSHOT_REF,
    TRUSTED_NAMESPACES,
    Artifact,
    ArtifactReference,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.design_case import DesignCase, DesignCaseStatus
from oak.domain.intake import holds_control_character
from oak.ports import CataloguePort, ResearchVocabularyPort, WorkspaceRepository
from oak.ports.research import ResearchRunner, ResearchSourceFactory, ResearchSourceMode

AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"
CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
MAXIMUM_RATIONALE = 4000
DECISIONS = frozenset({"accept", "reject"})
SourceFactory = ResearchSourceFactory
SourceMode = ResearchSourceMode


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    case_id: str
    case_version: str
    status: str
    allowed: bool
    source_mode: str
    hosts: tuple[str, ...]
    terms: dict[str, Any]
    terms_digest: str

    def to_document(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_version": self.case_version,
            "status": self.status,
            "allowed": self.allowed,
            "source_mode": self.source_mode,
            "hosts": list(self.hosts),
            "terms": self.terms,
            "terms_digest": self.terms_digest,
        }


@dataclass(frozen=True, slots=True)
class ResearchResult:
    case: dict[str, Any]
    snapshot: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {"case": self.case, "snapshot": self.snapshot, "duplicate": self.duplicate}


@dataclass(frozen=True, slots=True)
class ResearchReviewResult:
    case: dict[str, Any]
    review: dict[str, Any]
    duplicate: bool


class ResearchService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        registry: SchemaRegistry,
        catalogue: CataloguePort,
        vocabulary: ResearchVocabularyPort,
        *,
        source_factory: SourceFactory,
        source_mode: SourceMode,
        runner: ResearchRunner,
        cache: Any = None,
        trusted_namespaces: frozenset[str] = TRUSTED_NAMESPACES,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._catalogue = catalogue
        self._vocabulary = vocabulary
        self._source_factory = source_factory
        self._source_mode = source_mode
        self._runner = runner
        self._cache = cache
        self._trusted_namespaces = trusted_namespaces

    # ----- the plan: a read -------------------------------------------------------------

    def plan(self) -> ResearchPlan:
        case = self._require_case()
        if not isinstance(case.get("intent_ref"), dict):
            # A draft has no intent to derive terms from (F2-4).
            raise OAKError(
                "OAK-RESEARCH-STATE",
                "research needs an interpreted case; this case has no intent yet",
            )
        intent = self._repository.read_json_artifact(
            ArtifactReference.from_document(case["intent_ref"])
        )
        vocabulary = self._vocabulary.load()
        patterns = self._catalogue.load().patterns
        terms = derive_research_terms(intent, vocabulary, patterns)
        mode, hosts = self._source_mode()
        return ResearchPlan(
            case_id=str(case["id"]),
            case_version=str(case["version"]),
            status=str(case["status"]),
            allowed=str(case["status"]) == DesignCaseStatus.READY_FOR_CANDIDATES.value,
            source_mode=mode,
            hosts=tuple(sorted(hosts)),
            terms=terms,
            terms_digest=terms_digest(terms, source_mode=mode, hosts=hosts),
        )

    def check_consent(self, consent: dict[str, Any], plan: ResearchPlan | None = None) -> None:
        """The consent must name exactly the plan's hosts and terms digest (K3)."""

        plan = plan or self.plan()
        hosts = consent.get("hosts")
        digest = consent.get("terms_digest")
        if (
            not isinstance(hosts, list)
            or any(not isinstance(host, str) for host in hosts)
            or sorted(set(hosts)) != list(plan.hosts)
            or digest != plan.terms_digest
        ):
            raise OAKError(
                "OAK-RESEARCH-CONSENT",
                "the consent does not name the hosts and terms this research would send; "
                "read the plan again and consent to what it shows",
            )

    def check_state(self, case: dict[str, Any] | None = None) -> dict[str, Any]:
        case = case or self._require_case()
        if str(case["status"]) != DesignCaseStatus.READY_FOR_CANDIDATES.value:
            raise OAKError(
                "OAK-RESEARCH-STATE",
                "research runs only while the case is ready for candidates; once candidates "
                "exist the recorded design is kept as it is",
            )
        return case

    # ----- the run ----------------------------------------------------------------------

    def run(self, context: CommandContext, *, consent: dict[str, Any]) -> ResearchResult:
        scope = {} if context.idempotency_key else {"case_version": context.expected_version}
        input_digest = self._request_digest(
            context,
            {
                "action": "research_catalogue",
                "terms_digest": consent.get("terms_digest"),
                "hosts": sorted(consent.get("hosts") or [])
                if isinstance(consent.get("hosts"), list)
                else [],
                **scope,
            },
        )
        context = self._normalized_context(context, "research", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return ResearchResult(
                case=duplicate, snapshot=self._snapshot_for(duplicate), duplicate=True
            )
        current_document = self.check_state()
        current = DesignCase.from_document(current_document)
        if context.expected_version != current.version:
            raise OAKError(
                "OAK-EXPECTED-VERSION",
                "expected case version does not match current version",
                retriable=True,
            )
        plan = self.plan()
        self.check_consent(consent, plan)
        fetch, mode, hosts = self._source_factory(context.occurred_at)
        if mode != plan.source_mode or frozenset(hosts) != frozenset(plan.hosts):
            raise OAKError("OAK-RESEARCH-CONSENT", "the research source changed since the plan")
        suffix = current.id.removeprefix("design-case.")
        snapshot_id = f"research.{suffix}"
        existing = sum(
            1
            for entry in self._repository.manifest()["artifact_index"]
            if entry["kind"] == "research_snapshot" and entry["id"] == snapshot_id
        )
        snapshot_version = f"0.{existing + 1}.0"
        if current.intent_ref is None:
            raise OAKError("OAK-RESEARCH-STATE", "the case holds no interpreted intent yet")
        # A fixture run measures no time: its snapshot is a synthetic record that two
        # workspaces must produce byte for byte, so its clock is a constant.
        clock: Any = (lambda: 0.0) if mode == "fixture" else time.monotonic
        run = self._runner(
            fetch,
            terms=plan.terms,
            terms_digest=plan.terms_digest,
            vocabulary=self._vocabulary.load(),
            trusted_namespaces=self._trusted_namespaces,
            intent_ref=_reference_document(current.intent_ref),
            case_id=current.id,
            snapshot_id=snapshot_id,
            snapshot_version=snapshot_version,
            occurred_at=context.occurred_at,
            source_mode=mode,
            cache=self._resolve_cache() if mode != "fixture" else None,
            clock=clock,
        )
        self._registry.validate("research-snapshot.schema.json", run.snapshot)
        snapshot_artifact = json_artifact(
            artifact_id=snapshot_id,
            version=snapshot_version,
            kind="research_snapshot",
            media_type=RESEARCH_SNAPSHOT_MEDIA_TYPE,
            document=run.snapshot,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions[RESEARCH_SNAPSHOT_REF] = _reference_document(snapshot_artifact.reference)
        # Reviews bind to a snapshot's digest, so a new run starts with none.
        extensions[RESEARCH_REVIEW_REFS] = []
        successor = current.revise(
            status=current.status, updated_at=context.occurred_at, extensions=extensions
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="research_completed",
            context=context,
            input_digest=input_digest,
            artifacts=(*run.manifests, snapshot_artifact),
            event_extensions={
                "oak.community/research": {
                    "terms_digest": plan.terms_digest,
                    "hosts": list(plan.hosts),
                    "source_mode": mode,
                    "summary": run.snapshot["summary"],
                    "snapshot_ref": _reference_document(snapshot_artifact.reference),
                }
            },
        )
        return ResearchResult(case=published, snapshot=run.snapshot, duplicate=False)

    # ----- the review -------------------------------------------------------------------

    def review(
        self, context: CommandContext, *, item_id: str, decision: str, rationale: str
    ) -> ResearchReviewResult:
        if decision not in DECISIONS:
            raise OAKError("OAK-RESEARCH-REVIEW-DECISION", "a review is accept or reject")
        if not isinstance(rationale, str) or not rationale.strip():
            raise OAKError("OAK-RESEARCH-REVIEW-RATIONALE", "a review needs a rationale")
        if holds_control_character(rationale):
            # The same rule a selection rationale already met (F1-11).
            raise OAKError(
                "OAK-RESEARCH-REVIEW-RATIONALE",
                "a rationale must not hold a control or formatting character",
            )
        if len(rationale) > MAXIMUM_RATIONALE:
            raise OAKError(
                "OAK-RESEARCH-REVIEW-SIZE",
                f"a rationale holds at most {MAXIMUM_RATIONALE} characters",
            )
        scope = {} if context.idempotency_key else {"case_version": context.expected_version}
        input_digest = self._request_digest(
            context,
            {
                "action": "review_research_item",
                "item_id": item_id,
                "decision": decision,
                "rationale_digest": content_digest(rationale.encode("utf-8")),
                **scope,
            },
        )
        context = self._normalized_context(context, "review-research-item", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            reviews = self._reviews_for(duplicate)
            return ResearchReviewResult(case=duplicate, review=reviews[-1], duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.READY_FOR_CANDIDATES:
            raise OAKError(
                "OAK-RESEARCH-REVIEW-STATE",
                "a research item is reviewed only while the case is ready for candidates",
            )
        if context.expected_version != current.version:
            raise OAKError(
                "OAK-EXPECTED-VERSION",
                "expected case version does not match current version",
                retriable=True,
            )
        reference = (current.extensions or {}).get(RESEARCH_SNAPSHOT_REF)
        if not isinstance(reference, dict):
            raise OAKError("OAK-RESEARCH-MISSING", "the case holds no research snapshot to review")
        snapshot = self._repository.read_json_artifact(ArtifactReference.from_document(reference))
        item = next((entry for entry in snapshot["items"] if entry["id"] == item_id), None)
        if item is None:
            raise OAKError("OAK-RESEARCH-ITEM-UNKNOWN", "the snapshot holds no such item")
        if item["verdict"] != "needs_review":
            raise OAKError(
                "OAK-RESEARCH-ITEM-STATE",
                "only an item that needs a review can be reviewed; a passed or failed item "
                "keeps the verdict the gates gave it",
            )
        for earlier in self._reviews_for(current_document):
            if earlier.get("item_id") == item_id and (earlier.get("snapshot_ref") or {}).get(
                "digest"
            ) == str(reference["digest"]):
                # One recorded decision per item per run is the invariant the compiler, the
                # workspace and the report all read; a changed mind is a new research run.
                raise OAKError(
                    "OAK-RESEARCH-ITEM-STATE",
                    "this item is already reviewed against this research snapshot; one "
                    "decision is recorded per item per run, so run research again to review "
                    "it afresh",
                )
        suffix = current.id.removeprefix("design-case.")
        slug = item_id.removeprefix("research.item.").replace("/", ".")
        review_id = f"research-review.{suffix}.{slug}"
        existing = sum(
            1
            for entry in self._repository.manifest()["artifact_index"]
            if entry["kind"] == "research_review" and entry["id"] == review_id
        )
        review_document = {
            "schema_version": "0.1.0",
            "id": review_id,
            "version": f"0.{existing + 1}.0",
            "case_id": current.id,
            "snapshot_ref": {
                "id": str(reference["id"]),
                "version": str(reference["version"]),
                "digest": str(reference["digest"]),
            },
            "item_id": item_id,
            "item_response_digest": str(item["response_digest"]),
            "decision": decision,
            "rationale": rationale,
            "actor": context.actor,
            "recorded_at": context.occurred_at,
            "extensions": {},
        }
        self._registry.validate("research-review.schema.json", review_document)
        artifact = json_artifact(
            artifact_id=review_id,
            version=str(review_document["version"]),
            kind="research_review",
            media_type=RESEARCH_REVIEW_MEDIA_TYPE,
            document=review_document,
        )
        extensions = copy.deepcopy(current.extensions or {})
        refs = list(extensions.get(RESEARCH_REVIEW_REFS) or [])
        refs.append(_reference_document(artifact.reference))
        extensions[RESEARCH_REVIEW_REFS] = refs
        successor = current.revise(
            status=current.status, updated_at=context.occurred_at, extensions=extensions
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="research_item_reviewed",
            context=context,
            input_digest=input_digest,
            artifacts=(artifact,),
            event_extensions={
                "oak.community/research_review": {
                    "item_id": item_id,
                    "decision": decision,
                    "review_ref": _reference_document(artifact.reference),
                }
            },
        )
        return ResearchReviewResult(case=published, review=review_document, duplicate=False)

    # ----- reads -----------------------------------------------------------------------

    def latest(self) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
        """The current case, the snapshot it holds (if any) and its reviews; reads only."""

        case = self._require_case()
        reference = (case.get("extensions") or {}).get(RESEARCH_SNAPSHOT_REF)
        snapshot = (
            self._repository.read_json_artifact(ArtifactReference.from_document(reference))
            if isinstance(reference, dict)
            else None
        )
        return case, snapshot, self._reviews_for(case)

    def _snapshot_for(self, case: dict[str, Any]) -> dict[str, Any]:
        reference = (case.get("extensions") or {}).get(RESEARCH_SNAPSHOT_REF)
        if not isinstance(reference, dict):
            raise OAKError("OAK-RESEARCH-MISSING", "the case holds no research snapshot")
        return self._repository.read_json_artifact(ArtifactReference.from_document(reference))

    def _resolve_cache(self) -> Any:
        """The cache, built on first use when a factory was given: the reader behind it is
        imported only when a consented live run needs it, never at startup."""

        if callable(self._cache):
            self._cache = self._cache()
        return self._cache

    def _reviews_for(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        references = (case.get("extensions") or {}).get(RESEARCH_REVIEW_REFS) or []
        return [
            self._repository.read_json_artifact(ArtifactReference.from_document(reference))
            for reference in references
            if isinstance(reference, dict)
        ]

    # ----- the commit ------------------------------------------------------------------

    def _publish(
        self,
        *,
        current: dict[str, Any],
        successor: DesignCase,
        event_type: str,
        context: CommandContext,
        input_digest: str,
        artifacts: tuple[Artifact, ...],
        event_extensions: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = self._repository.manifest()
        intent_ref = ArtifactReference.from_document(current["intent_ref"])
        intent = self._repository.read_json_artifact(intent_ref)
        source_value = (intent.get("extensions") or {}).get("oak.community/source_record")
        source_record_ref = (
            ArtifactReference.from_document(source_value)
            if isinstance(source_value, dict)
            else None
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type=event_type,
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=intent_ref,
            source_record_ref=source_record_ref,
            extensions={
                "oak.community/artifact_refs": [
                    _reference_document(artifact.reference) for artifact in artifacts
                ],
                **event_extensions,
            },
        )
        self._registry.validate("audit-event.schema.json", event_document)
        event = json_artifact(
            artifact_id=str(event_document["id"]),
            version=str(sequence),
            kind="audit_event",
            media_type=AUDIT_MEDIA_TYPE,
            document=event_document,
        )
        successor = successor.with_audit_head(event.digest)
        case_document = successor.to_document()
        self._registry.validate("design-case.schema.json", case_document)
        case = json_artifact(
            artifact_id=successor.id,
            version=successor.version,
            kind="design_case",
            media_type=CASE_MEDIA_TYPE,
            document=case_document,
        )
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(*artifacts, event, case),
                current_case_ref=case.reference,
                event_artifact=event,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        return committed.case_document

    # ----- helpers ---------------------------------------------------------------------

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    def _check_tenant(self, context: CommandContext) -> None:
        if self._repository.manifest()["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")

    @staticmethod
    def _check_context(context: CommandContext) -> None:
        if len(context.idempotency_key) < 16:
            raise OAKError(
                "OAK-IDEMPOTENCY-KEY", "idempotency key must contain at least 16 characters"
            )
        if not context.correlation_id or len(context.correlation_id) < 8:
            raise OAKError(
                "OAK-CORRELATION-ID", "correlation id must contain at least 8 characters"
            )

    @staticmethod
    def _normalized_context(
        context: CommandContext, action: str, input_digest: str
    ) -> CommandContext:
        key = context.idempotency_key or f"{action}-{input_digest.removeprefix('sha256:')[:40]}"
        correlation = context.correlation_id or f"correlation-{key}"
        return CommandContext(
            actor=context.actor,
            tenant_id=context.tenant_id,
            idempotency_key=key,
            expected_version=context.expected_version,
            correlation_id=correlation,
            interface_origin=context.interface_origin,
            occurred_at=context.occurred_at,
        )

    @staticmethod
    def _request_digest(context: CommandContext, input_document: dict[str, Any]) -> str:
        return content_digest(
            canonical_json_bytes(
                {
                    "actor": context.actor,
                    "tenant_id": context.tenant_id,
                    "interface_origin": context.interface_origin,
                    "input": input_document,
                }
            )
        )


def _reference_document(reference: ArtifactReference) -> dict[str, Any]:
    """The full reference, media type included: the export-lineage check compares it."""

    return reference.to_document()
