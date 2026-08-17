# SPDX-License-Identifier: Apache-2.0
"""Append-only audit event construction."""

from typing import Any

from oak.domain.artifacts import ArtifactReference


def audit_event_document(
    *,
    sequence: int,
    previous_event_digest: str | None,
    case_id: str,
    case_version: str,
    event_type: str,
    actor: str,
    tenant_id: str,
    interface_origin: str,
    correlation_id: str,
    idempotency_key: str,
    input_digest: str,
    occurred_at: str,
    intent_ref: ArtifactReference | None,
    source_record_ref: ArtifactReference | None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "0.4.0",
        "id": f"audit.{case_id}.{sequence}",
        "sequence": sequence,
        "previous_event_digest": previous_event_digest,
        "case_id": case_id,
        "case_version": case_version,
        "event_type": event_type,
        "actor": actor,
        "tenant_id": tenant_id,
        "interface_origin": interface_origin,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "input_digest": input_digest,
        "occurred_at": occurred_at,
        "result": {
            "case_id": case_id,
            "case_version": case_version,
            "intent_ref": intent_ref.to_document() if intent_ref else None,
            "source_record_ref": source_record_ref.to_document() if source_record_ref else None,
        },
        "extensions": extensions or {},
    }
