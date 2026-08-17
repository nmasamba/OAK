# SPDX-License-Identifier: Apache-2.0
"""Reusable OAK-S3-002 workspace repository contract fixtures."""

from oak.application.persistence import build_workspace_mutation
from oak.domain import Artifact, DesignCase, DesignCaseStatus, json_artifact
from oak.domain.audit import audit_event_document
from oak.ports import WorkspaceMutation

NOW = "2026-08-17T10:00:00Z"


def initial_mutation(
    *,
    workspace_id: str = "workspace.workspace-test",
    idempotency_key: str = "design-workspace-test-0001",
    input_digest: str = f"sha256:{'1' * 64}",
) -> WorkspaceMutation:
    brief = Artifact(
        id="brief.workspace-test",
        version="0.1.0",
        kind="brief_source",
        media_type="text/plain",
        content=b"safe synthetic brief\n",
    )
    event_document = audit_event_document(
        sequence=1,
        previous_event_digest=None,
        case_id="design-case.workspace-test",
        case_version="0.1.0",
        event_type="brief_interpreted",
        actor="local-user",
        tenant_id="local",
        interface_origin="cli",
        correlation_id="correlation-workspace-test",
        idempotency_key=idempotency_key,
        input_digest=input_digest,
        occurred_at=NOW,
        intent_ref=None,
        source_record_ref=None,
    )
    event = json_artifact(
        artifact_id=str(event_document["id"]),
        version="1",
        kind="audit_event",
        media_type="application/vnd.oak.audit-event+json",
        document=event_document,
    )
    case = DesignCase(
        id="design-case.workspace-test",
        version="0.1.0",
        status=DesignCaseStatus.DRAFT,
        title="Workspace test",
        tenant_id="local",
        created_at=NOW,
        updated_at=NOW,
        interface_origin="cli",
        brief_refs=(brief.reference,),
        audit_head=event.digest,
    )
    case_artifact = json_artifact(
        artifact_id=case.id,
        version=case.version,
        kind="design_case",
        media_type="application/vnd.oak.design-case+json",
        document=case.to_document(),
    )
    return build_workspace_mutation(
        workspace_id=workspace_id,
        expected_case_version=None,
        idempotency_key=idempotency_key,
        input_digest=input_digest,
        artifacts=(brief, event, case_artifact),
        current_case_ref=case_artifact.reference,
        event_artifact=event,
        event_document=event_document,
        updated_at=NOW,
    )
