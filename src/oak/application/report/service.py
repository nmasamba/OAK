# SPDX-License-Identifier: Apache-2.0
"""Record the architecture report beside the case.

Recording composes the report from the case's records, renders it, and stores the
document and its PDF (and, in a model mode, the checked notes) as immutable artifacts. It
then revises the case at its own status and appends a `report_recorded` audit event. It
needs no signature, moves no status, and nothing in approval, dispatch or the runner reads
what it writes. The deterministic mode imports no model provider and opens no socket.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from oak.application.context import CommandContext
from oak.application.model_budget import (
    DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY,
    check_model_budget,
)
from oak.application.persistence import build_workspace_mutation
from oak.application.report.composer import (
    MAIN_SECTIONS,
    RECORDABLE_STATUSES,
    Narrative,
    narrator_facts,
    report_document,
)
from oak.application.report.notes import check_notes
from oak.application.report.records import gather_records
from oak.contracts import SchemaRegistry
from oak.domain import (
    Artifact,
    ArtifactReference,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.design_case import DesignCase, DesignCaseStatus, next_patch_version
from oak.domain.report import (
    NARRATIVE_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    RENDERING_KIND,
    REPORT_EXTENSION,
    REPORT_MEDIA_TYPE,
)
from oak.ports import ProposalLimits, WorkspaceRepository
from oak.ports.report import ReportNarratorPort, ReportRendererPort

CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"
NARRATIVE_MODES = ("deterministic", "online", "local")
MODEL_EXTENSION = "oak.community/model"
ReportNarratorFactory = Callable[[str], ReportNarratorPort | None]
NOT_CONFIGURED_REMEDIES = {
    "online": (
        "Online AI has nothing to call yet: store a Hugging Face token with `oak models "
        "set-key`, run `oak models discover` (or pin a model with `oak models select "
        "huggingface <model_id>`), or record with --narrative deterministic"
    ),
    "local": (
        "Local AI has nothing to call yet: pin a model on the local server with `oak models "
        "select local <model_id>`, or record with --narrative deterministic"
    ),
}
# What stands between an earlier case and its first report, in the user's words.
MISSING_STEP = {
    DesignCaseStatus.DRAFT: "interpret the brief, confirm it, generate candidates and select one",
    DesignCaseStatus.NEEDS_CONFIRMATION: (
        "answer the open questions, generate candidates and select one"
    ),
    DesignCaseStatus.READY_FOR_CANDIDATES: "generate candidates and select one",
    DesignCaseStatus.CANDIDATES_READY: "select a candidate (`oak select <candidate>`)",
}


@dataclass(frozen=True, slots=True)
class ReportResult:
    case: dict[str, Any]
    report: dict[str, Any]
    document: dict[str, Any]
    duplicate: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "report": self.report,
            "document": self.document,
            "duplicate": self.duplicate,
        }


class ReportService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        registry: SchemaRegistry,
        renderer: ReportRendererPort | None,
        *,
        oak_version: str,
        narrator_factory: ReportNarratorFactory | None = None,
        proposal_limits: ProposalLimits | None = None,
        model_requests_per_day: int = DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._renderer = renderer
        self._oak_version = oak_version
        self._narrator_factory = narrator_factory
        self._limits = proposal_limits or ProposalLimits()
        self._model_requests_per_day = model_requests_per_day

    @staticmethod
    def resolve_narrative(narrative: str = "deterministic") -> str:
        if narrative not in NARRATIVE_MODES:
            raise OAKError("OAK-NARRATIVE-MODE", "narrative must be deterministic, online or local")
        return narrative

    def latest(self) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """The current case and the report it holds, if any; reads only."""

        case = self._require_case()
        entry = (case.get("extensions") or {}).get(REPORT_EXTENSION)
        return case, entry if isinstance(entry, dict) else None

    def artifact_bytes(self, reference: dict[str, Any]) -> bytes:
        """One recorded report artifact's bytes; the repository checks the digest."""

        return self._repository.read_artifact(ArtifactReference.from_document(reference))

    def record(self, context: CommandContext, *, narrative: str = "deterministic") -> ReportResult:
        mode = self.resolve_narrative(narrative)
        # A derived key is scoped to the case version, so recording again after the case
        # moves on is a new request; an explicit key stays the caller's own retry handle.
        scope = {} if context.idempotency_key else {"case_version": context.expected_version}
        input_digest = self._request_digest(
            context, {"action": "record_report", "narrative": mode, **scope}
        )
        context = self._normalized_context(context, "record-report", input_digest)
        self._check_context(context)
        if self._repository.manifest()["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            entry = dict((duplicate.get("extensions") or {}).get(REPORT_EXTENSION) or {})
            document = (
                self._repository.read_json_artifact(
                    ArtifactReference.from_document(entry["document_ref"])
                )
                if isinstance(entry.get("document_ref"), dict)
                else {}
            )
            return ReportResult(case=duplicate, report=entry, document=document, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status.value not in RECORDABLE_STATUSES:
            missing = MISSING_STEP.get(current.status)
            raise OAKError(
                "OAK-REPORT-STATE",
                f"a report is recorded from candidate_selected onwards; first {missing}"
                if missing
                else "a closed case takes no new report",
            )
        if context.expected_version is not None and context.expected_version != current.version:
            # Before any note is asked for: a stale request used to send the slides to the
            # model and spend credit, then be refused at the commit (F2-6).
            raise OAKError(
                "OAK-EXPECTED-VERSION",
                "expected case version does not match current version",
                retriable=True,
            )
        if self._renderer is None or PDF_MEDIA_TYPE not in self._renderer.formats():
            raise OAKError("OAK-REPORT-RENDER", "no PDF report renderer is configured")
        records = gather_records(self._repository)
        suffix = current.id.removeprefix("design-case.")
        report_id = f"report.{suffix}.from-{current.version}"
        arguments: dict[str, Any] = {
            "report_id": report_id,
            "generated_at": context.occurred_at,
            "generated_by": context.actor,
            "oak_version": self._oak_version,
            "renderer": self._renderer.identity(),
        }
        artifacts: list[Artifact] = []
        notes: Narrative | None = None
        if mode != "deterministic":
            # The case's daily count of billable requests, before any note is asked for
            # (RR-041).
            check_model_budget(
                self._repository,
                occurred_at=context.occurred_at,
                maximum=self._model_requests_per_day,
            )
            notes, narrative_artifact = self._narrate(
                mode, report_document(records, **arguments), current, suffix
            )
            artifacts.append(narrative_artifact)
        document = report_document(records, narrative=notes, **arguments)
        self._registry.validate("architecture-report.schema.json", document)
        document_artifact = json_artifact(
            artifact_id=report_id,
            version="0.1.0",
            kind="architecture_report",
            media_type=REPORT_MEDIA_TYPE,
            document=document,
        )
        rendering = Artifact(
            id=f"{report_id}.pdf",
            version="0.1.0",
            kind=RENDERING_KIND,
            media_type=PDF_MEDIA_TYPE,
            content=self._renderer.render(document, PDF_MEDIA_TYPE),
        )
        artifacts += [document_artifact, rendering]
        entry = {
            "document_ref": document_artifact.reference.to_document(),
            "pdf_ref": rendering.reference.to_document(),
            "narrative_ref": artifacts[0].reference.to_document() if notes else None,
            "narrative_mode": mode,
            "made_from_case_version": current.version,
            "recorded_case_version": next_patch_version(current.version),
            "recorded_at": context.occurred_at,
        }
        extensions = copy.deepcopy(current.extensions or {})
        extensions[REPORT_EXTENSION] = entry
        successor = current.revise(
            status=current.status, updated_at=context.occurred_at, extensions=extensions
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            context=context,
            input_digest=input_digest,
            artifacts=tuple(artifacts),
        )
        return ReportResult(case=published, report=entry, document=document, duplicate=False)

    def _narrate(
        self, mode: str, draft: dict[str, Any], current: DesignCase, suffix: str
    ) -> tuple[Narrative, Artifact]:
        adapter = self._narrator_factory(mode) if self._narrator_factory is not None else None
        if adapter is None:
            raise OAKError("OAK-MODEL-NOT-CONFIGURED", NOT_CONFIGURED_REMEDIES[mode])
        facts = narrator_facts(draft)
        proposal = adapter.propose(facts, self._limits)
        kept, dropped = check_notes(proposal.get("notes"), facts)
        if not kept:
            raise OAKError(
                "OAK-NARRATIVE-EMPTY",
                "none of the model's notes passed OAK's checks, so nothing was recorded; "
                "record again or use --narrative deterministic",
            )
        details = (proposal.get("extensions") or {}).get(MODEL_EXTENSION)
        if not isinstance(details, dict):
            raise OAKError("OAK-NARRATIVE-MALFORMED", "the narrator did not name its model")
        model = {
            field: details.get(field)
            for field in (
                "family",
                "model_id",
                "provider_route",
                "prompt_digest",
                "response_digest",
                "usage",
                "attempts",
            )
        }
        model["dropped_notes"] = int(details.get("dropped_notes") or 0) + dropped
        narrative_document = {
            "schema_version": "0.1.0",
            "id": f"narrative.{suffix}.from-{current.version}",
            "version": "0.1.0",
            "case_id": current.id,
            "mode": mode,
            "facts_digest": content_digest(canonical_json_bytes(facts)),
            "notes": [
                {"section": section, "text": kept[section]}
                for section in MAIN_SECTIONS
                if section in kept
            ],
            "extensions": {MODEL_EXTENSION: model},
        }
        self._registry.validate("report-narrative.schema.json", narrative_document)
        artifact = json_artifact(
            artifact_id=str(narrative_document["id"]),
            version="0.1.0",
            kind="report_narrative",
            media_type=NARRATIVE_MEDIA_TYPE,
            document=narrative_document,
        )
        route = model.get("provider_route")
        label = f"{model['model_id']} via {route}" if route else str(model["model_id"])
        return (
            Narrative(
                mode=mode,
                narrative_ref=artifact.reference.to_document(),
                model=label,
                notes=kept,
            ),
            artifact,
        )

    def _publish(
        self,
        *,
        current: dict[str, Any],
        successor: DesignCase,
        context: CommandContext,
        input_digest: str,
        artifacts: tuple[Artifact, ...],
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
            event_type="report_recorded",
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
                    artifact.reference.to_document() for artifact in artifacts
                ]
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

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    @staticmethod
    def _check_context(context: CommandContext) -> None:
        if len(context.idempotency_key) < 16:
            raise OAKError(
                "OAK-IDEMPOTENCY-KEY", "idempotency key must contain at least 16 characters"
            )
        if len(context.correlation_id) < 8:
            raise OAKError(
                "OAK-CORRELATION-ID", "correlation ID must contain at least 8 characters"
            )

    @staticmethod
    def _normalized_context(
        context: CommandContext, operation: str, input_digest: str
    ) -> CommandContext:
        digest_hex = input_digest.removeprefix("sha256:")
        return replace(
            context,
            idempotency_key=(context.idempotency_key or f"{operation}:{digest_hex}"),
            correlation_id=(context.correlation_id or f"correlation:{digest_hex[:24]}"),
        )

    @staticmethod
    def _request_digest(context: CommandContext, input_document: dict[str, Any]) -> str:
        return content_digest(
            canonical_json_bytes(
                {"actor": context.actor, "tenant_id": context.tenant_id, "input": input_document}
            )
        )
