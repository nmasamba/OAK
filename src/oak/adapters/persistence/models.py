# SPDX-License-Identifier: Apache-2.0
"""Normalized PostgreSQL metadata model for the Community control plane."""

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


def _scope_columns() -> tuple[Column[Any], ...]:
    return (
        Column("tenant_id", String(160), nullable=False),
        Column("environment_id", String(160), nullable=False),
    )


def _workspace_scope_columns() -> tuple[Column[Any], ...]:
    return (*_scope_columns(), Column("workspace_id", String(240), nullable=False))


workspaces = Table(
    "workspaces",
    metadata,
    *_workspace_scope_columns(),
    Column("revision", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("current_case_id", String(240)),
    Column("current_case_version", String(80)),
    Column("current_case_digest", String(71)),
    CheckConstraint("revision >= 0", name="ck_workspaces_revision_nonnegative"),
    CheckConstraint(
        "(current_case_id IS NULL AND current_case_version IS NULL AND "
        "current_case_digest IS NULL) OR "
        "(current_case_id IS NOT NULL AND current_case_version IS NOT NULL AND "
        "current_case_digest IS NOT NULL)",
        name="ck_workspaces_current_case_complete",
    ),
    PrimaryKeyConstraint("tenant_id", "environment_id", "workspace_id"),
)

artifact_versions = Table(
    "artifact_versions",
    metadata,
    *_workspace_scope_columns(),
    Column("artifact_id", String(240), nullable=False),
    Column("artifact_version", String(80), nullable=False),
    Column("digest", String(71), nullable=False),
    Column("kind", String(80), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("storage_key", String(64), nullable=False),
    Column("canonical_document", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "size_bytes >= 0 AND size_bytes <= 8388608",
        name="ck_artifact_versions_bounded_size",
    ),
    PrimaryKeyConstraint(
        "tenant_id", "environment_id", "workspace_id", "artifact_id", "artifact_version"
    ),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "workspace_id"],
        ["workspaces.tenant_id", "workspaces.environment_id", "workspaces.workspace_id"],
        ondelete="RESTRICT",
    ),
)

design_case_versions = Table(
    "design_case_versions",
    metadata,
    *_workspace_scope_columns(),
    Column("case_id", String(240), nullable=False),
    Column("case_version", String(80), nullable=False),
    Column("digest", String(71), nullable=False),
    Column("status", String(80), nullable=False),
    Column("audit_head", String(71), nullable=False),
    Column("document", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("tenant_id", "environment_id", "workspace_id", "case_id", "case_version"),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "workspace_id", "case_id", "case_version"],
        [
            "artifact_versions.tenant_id",
            "artifact_versions.environment_id",
            "artifact_versions.workspace_id",
            "artifact_versions.artifact_id",
            "artifact_versions.artifact_version",
        ],
        ondelete="RESTRICT",
    ),
)

design_case_heads = Table(
    "design_case_heads",
    metadata,
    *_workspace_scope_columns(),
    Column("case_id", String(240), nullable=False),
    Column("current_version", String(80), nullable=False),
    Column("current_digest", String(71), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("tenant_id", "environment_id", "workspace_id", "case_id"),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "workspace_id", "case_id", "current_version"],
        [
            "design_case_versions.tenant_id",
            "design_case_versions.environment_id",
            "design_case_versions.workspace_id",
            "design_case_versions.case_id",
            "design_case_versions.case_version",
        ],
        ondelete="RESTRICT",
    ),
)

transitions = Table(
    "transitions",
    metadata,
    *_workspace_scope_columns(),
    Column("case_id", String(240), nullable=False),
    Column("aggregate_sequence", Integer, nullable=False),
    Column("event_id", String(240), nullable=False),
    Column("case_version", String(80), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("actor", String(160), nullable=False),
    Column("interface_origin", String(40), nullable=False),
    Column("correlation_id", String(160), nullable=False),
    Column("idempotency_key", String(240), nullable=False),
    Column("input_digest", String(71), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("event_artifact_id", String(240), nullable=False),
    Column("event_artifact_version", String(80), nullable=False),
    Column("event_artifact_digest", String(71), nullable=False),
    CheckConstraint("aggregate_sequence > 0", name="ck_transitions_sequence_positive"),
    PrimaryKeyConstraint(
        "tenant_id",
        "environment_id",
        "workspace_id",
        "case_id",
        "aggregate_sequence",
    ),
    UniqueConstraint(
        "tenant_id",
        "environment_id",
        "workspace_id",
        "event_id",
        name="uq_transition_event",
    ),
    UniqueConstraint(
        "tenant_id",
        "environment_id",
        "workspace_id",
        "aggregate_sequence",
        name="uq_transition_sequence",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "workspace_id", "case_id", "case_version"],
        [
            "design_case_versions.tenant_id",
            "design_case_versions.environment_id",
            "design_case_versions.workspace_id",
            "design_case_versions.case_id",
            "design_case_versions.case_version",
        ],
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        [
            "tenant_id",
            "environment_id",
            "workspace_id",
            "event_artifact_id",
            "event_artifact_version",
        ],
        [
            "artifact_versions.tenant_id",
            "artifact_versions.environment_id",
            "artifact_versions.workspace_id",
            "artifact_versions.artifact_id",
            "artifact_versions.artifact_version",
        ],
        ondelete="RESTRICT",
    ),
)

approvals = Table(
    "approvals",
    metadata,
    *_scope_columns(),
    Column("approval_id", String(240), nullable=False),
    Column("case_id", String(240), nullable=False),
    Column("object_digest", String(71), nullable=False),
    Column("target_id", String(240), nullable=False),
    Column("action", String(80), nullable=False),
    Column("actor", String(160), nullable=False),
    Column("status", String(40), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    PrimaryKeyConstraint("tenant_id", "environment_id", "approval_id"),
    UniqueConstraint(
        "tenant_id",
        "environment_id",
        "object_digest",
        "target_id",
        "action",
        "actor",
        name="uq_approval_binding",
    ),
)

idempotency_records = Table(
    "idempotency_records",
    metadata,
    *_workspace_scope_columns(),
    Column("idempotency_key", String(240), nullable=False),
    Column("input_digest", String(71), nullable=False),
    Column("result_case_id", String(240), nullable=False),
    Column("result_case_version", String(80), nullable=False),
    Column("result_case_digest", String(71), nullable=False),
    Column("event_id", String(240), nullable=False),
    Column("aggregate_sequence", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("tenant_id", "environment_id", "workspace_id", "idempotency_key"),
    ForeignKeyConstraint(
        [
            "tenant_id",
            "environment_id",
            "workspace_id",
            "result_case_id",
            "result_case_version",
        ],
        [
            "design_case_versions.tenant_id",
            "design_case_versions.environment_id",
            "design_case_versions.workspace_id",
            "design_case_versions.case_id",
            "design_case_versions.case_version",
        ],
        ondelete="RESTRICT",
    ),
)

outbox_events = Table(
    "outbox_events",
    metadata,
    *_workspace_scope_columns(),
    Column("event_id", String(240), nullable=False),
    Column("aggregate_type", String(80), nullable=False),
    Column("aggregate_id", String(240), nullable=False),
    Column("aggregate_version", String(80), nullable=False),
    Column("aggregate_sequence", Integer, nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("payload_digest", String(71), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("claimed_by", String(240)),
    Column("claim_expires_at", DateTime(timezone=True)),
    Column("delivery_attempts", Integer, nullable=False),
    Column("delivered_at", DateTime(timezone=True)),
    Column("last_error_code", String(120)),
    CheckConstraint(
        "aggregate_sequence > 0",
        name="ck_outbox_events_aggregate_sequence_positive",
    ),
    CheckConstraint(
        "delivery_attempts >= 0",
        name="ck_outbox_events_delivery_attempts_nonnegative",
    ),
    PrimaryKeyConstraint("tenant_id", "environment_id", "workspace_id", "event_id"),
    UniqueConstraint(
        "tenant_id",
        "environment_id",
        "workspace_id",
        "aggregate_id",
        "aggregate_sequence",
        name="uq_outbox_sequence",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "workspace_id", "event_id"],
        [
            "transitions.tenant_id",
            "transitions.environment_id",
            "transitions.workspace_id",
            "transitions.event_id",
        ],
        ondelete="RESTRICT",
    ),
)

Index(
    "ix_outbox_events_claimable",
    outbox_events.c.available_at,
    outbox_events.c.claim_expires_at,
    postgresql_where=outbox_events.c.delivered_at.is_(None),
)

outbox_consumer_receipts = Table(
    "outbox_consumer_receipts",
    metadata,
    *_scope_columns(),
    Column("consumer_name", String(160), nullable=False),
    Column("event_id", String(240), nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("tenant_id", "environment_id", "consumer_name", "event_id"),
)

projection_positions = Table(
    "projection_positions",
    metadata,
    *_scope_columns(),
    Column("projection_name", String(160), nullable=False),
    Column("aggregate_id", String(240), nullable=False),
    Column("indexed_through", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "indexed_through >= 0",
        name="ck_projection_positions_indexed_through_nonnegative",
    ),
    PrimaryKeyConstraint("tenant_id", "environment_id", "projection_name", "aggregate_id"),
)

operations = Table(
    "operations",
    metadata,
    *_scope_columns(),
    Column("operation_id", String(240), nullable=False),
    Column("workspace_id", String(240), nullable=False),
    Column("case_id", String(240), nullable=False),
    Column("kind", String(80), nullable=False),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("request_digest", String(71), nullable=False),
    Column("request", JSONB, nullable=False),
    Column("result", JSONB),
    Column("problem", JSONB),
    Column("correlation_id", String(160), nullable=False),
    Column("idempotency_key", String(240), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("leased_by", String(240)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("heartbeat_at", DateTime(timezone=True)),
    Column("cancel_requested", Boolean, nullable=False),
    Column("cancel_requested_by", String(160)),
    Column("cancel_idempotency_key", String(240)),
    Column("cancel_correlation_id", String(160)),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("checkpoint", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    CheckConstraint("version >= 0", name="ck_operations_version_nonnegative"),
    CheckConstraint("attempt_count >= 0", name="ck_operations_attempt_count_nonnegative"),
    CheckConstraint(
        "max_attempts > 0 AND max_attempts <= 10",
        name="ck_operations_max_attempts_bounded",
    ),
    CheckConstraint(
        "state IN ('queued','running','succeeded','failed','cancelling','cancelled')",
        name="ck_operations_state_known",
    ),
    CheckConstraint(
        "(cancel_requested = false AND cancel_requested_by IS NULL AND "
        "cancel_idempotency_key IS NULL AND cancel_correlation_id IS NULL AND "
        "cancel_requested_at IS NULL) OR (cancel_requested = true AND "
        "cancel_requested_by IS NOT NULL AND cancel_idempotency_key IS NOT NULL AND "
        "cancel_correlation_id IS NOT NULL AND cancel_requested_at IS NOT NULL)",
        name="ck_operations_cancellation_context_complete",
    ),
    PrimaryKeyConstraint("tenant_id", "environment_id", "operation_id"),
    UniqueConstraint(
        "tenant_id",
        "environment_id",
        "workspace_id",
        "idempotency_key",
        name="uq_operation_workspace_idempotency",
    ),
)

Index(
    "ix_operations_claimable",
    operations.c.next_attempt_at,
    operations.c.lease_expires_at,
    postgresql_where=operations.c.state.in_(("queued", "running", "cancelling")),
)

job_checkpoints = Table(
    "job_checkpoints",
    metadata,
    *_scope_columns(),
    Column("operation_id", String(240), nullable=False),
    Column("checkpoint_sequence", Integer, nullable=False),
    Column("checkpoint", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "checkpoint_sequence > 0",
        name="ck_job_checkpoints_checkpoint_sequence_positive",
    ),
    PrimaryKeyConstraint("tenant_id", "environment_id", "operation_id", "checkpoint_sequence"),
    ForeignKeyConstraint(
        ["tenant_id", "environment_id", "operation_id"],
        ["operations.tenant_id", "operations.environment_id", "operations.operation_id"],
        ondelete="RESTRICT",
    ),
)

schema_metadata = Table(
    "schema_metadata",
    metadata,
    Column("key", String(120), primary_key=True),
    Column("value", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("evidence", LargeBinary),
)
