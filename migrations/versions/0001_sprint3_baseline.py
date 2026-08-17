# SPDX-License-Identifier: Apache-2.0
"""Create the first durable Community metadata schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_sprint3_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scope() -> list[sa.Column[object]]:
    return [
        sa.Column("tenant_id", sa.String(length=160), nullable=False),
        sa.Column("environment_id", sa.String(length=160), nullable=False),
    ]


def _workspace_scope() -> list[sa.Column[object]]:
    return [*_scope(), sa.Column("workspace_id", sa.String(length=240), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        *_workspace_scope(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_case_id", sa.String(length=240), nullable=True),
        sa.Column("current_case_version", sa.String(length=80), nullable=True),
        sa.Column("current_case_digest", sa.String(length=71), nullable=True),
        sa.CheckConstraint("revision >= 0", name="ck_workspaces_revision_nonnegative"),
        sa.CheckConstraint(
            "(current_case_id IS NULL AND current_case_version IS NULL AND "
            "current_case_digest IS NULL) OR "
            "(current_case_id IS NOT NULL AND current_case_version IS NOT NULL AND "
            "current_case_digest IS NOT NULL)",
            name="ck_workspaces_current_case_complete",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "environment_id", "workspace_id", name="pk_workspaces"
        ),
    )
    op.create_table(
        "artifact_versions",
        *_workspace_scope(),
        sa.Column("artifact_id", sa.String(length=240), nullable=False),
        sa.Column("artifact_version", sa.String(length=80), nullable=False),
        sa.Column("digest", sa.String(length=71), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "size_bytes >= 0 AND size_bytes <= 8388608",
            name="ck_artifact_versions_bounded_size",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "workspace_id"],
            ["workspaces.tenant_id", "workspaces.environment_id", "workspaces.workspace_id"],
            name="fk_artifact_scope_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "artifact_id",
            "artifact_version",
            name="pk_artifact_versions",
        ),
    )
    op.create_table(
        "design_case_versions",
        *_workspace_scope(),
        sa.Column("case_id", sa.String(length=240), nullable=False),
        sa.Column("case_version", sa.String(length=80), nullable=False),
        sa.Column("digest", sa.String(length=71), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("audit_head", sa.String(length=71), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "workspace_id", "case_id", "case_version"],
            [
                "artifact_versions.tenant_id",
                "artifact_versions.environment_id",
                "artifact_versions.workspace_id",
                "artifact_versions.artifact_id",
                "artifact_versions.artifact_version",
            ],
            name="fk_case_version_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "case_id",
            "case_version",
            name="pk_design_case_versions",
        ),
    )
    op.create_table(
        "design_case_heads",
        *_workspace_scope(),
        sa.Column("case_id", sa.String(length=240), nullable=False),
        sa.Column("current_version", sa.String(length=80), nullable=False),
        sa.Column("current_digest", sa.String(length=71), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "workspace_id", "case_id", "current_version"],
            [
                "design_case_versions.tenant_id",
                "design_case_versions.environment_id",
                "design_case_versions.workspace_id",
                "design_case_versions.case_id",
                "design_case_versions.case_version",
            ],
            name="fk_case_head_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "case_id",
            name="pk_design_case_heads",
        ),
    )
    _create_transition_tables()
    _create_outbox_tables()
    _create_operation_tables()
    op.create_table(
        "schema_metadata",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_schema_metadata"),
    )
    op.execute(
        sa.text(
            "INSERT INTO schema_metadata (key, value, recorded_at) "
            "VALUES ('baseline', '0001_sprint3_baseline', "
            "TIMESTAMPTZ '2026-08-17T18:34:00Z')"
        )
    )


def _create_transition_tables() -> None:
    op.create_table(
        "transitions",
        *_workspace_scope(),
        sa.Column("case_id", sa.String(length=240), nullable=False),
        sa.Column("aggregate_sequence", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=240), nullable=False),
        sa.Column("case_version", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("interface_origin", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("input_digest", sa.String(length=71), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_artifact_id", sa.String(length=240), nullable=False),
        sa.Column("event_artifact_version", sa.String(length=80), nullable=False),
        sa.Column("event_artifact_digest", sa.String(length=71), nullable=False),
        sa.CheckConstraint("aggregate_sequence > 0", name="ck_transitions_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "workspace_id", "case_id", "case_version"],
            [
                "design_case_versions.tenant_id",
                "design_case_versions.environment_id",
                "design_case_versions.workspace_id",
                "design_case_versions.case_id",
                "design_case_versions.case_version",
            ],
            name="fk_transition_case_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
            name="fk_transition_event_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "case_id",
            "aggregate_sequence",
            name="pk_transitions",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "event_id",
            name="uq_transition_event",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "aggregate_sequence",
            name="uq_transition_sequence",
        ),
    )
    op.create_table(
        "approvals",
        *_scope(),
        sa.Column("approval_id", sa.String(length=240), nullable=False),
        sa.Column("case_id", sa.String(length=240), nullable=False),
        sa.Column("object_digest", sa.String(length=71), nullable=False),
        sa.Column("target_id", sa.String(length=240), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "environment_id", "approval_id", name="pk_approvals"),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "object_digest",
            "target_id",
            "action",
            "actor",
            name="uq_approval_binding",
        ),
    )
    op.create_table(
        "idempotency_records",
        *_workspace_scope(),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("input_digest", sa.String(length=71), nullable=False),
        sa.Column("result_case_id", sa.String(length=240), nullable=False),
        sa.Column("result_case_version", sa.String(length=80), nullable=False),
        sa.Column("result_case_digest", sa.String(length=71), nullable=False),
        sa.Column("event_id", sa.String(length=240), nullable=False),
        sa.Column("aggregate_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
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
            name="fk_idempotency_case_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "idempotency_key",
            name="pk_idempotency_records",
        ),
    )


def _create_outbox_tables() -> None:
    op.create_table(
        "outbox_events",
        *_workspace_scope(),
        sa.Column("event_id", sa.String(length=240), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=240), nullable=False),
        sa.Column("aggregate_version", sa.String(length=80), nullable=False),
        sa.Column("aggregate_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_digest", sa.String(length=71), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by", sa.String(length=240), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "aggregate_sequence > 0", name="ck_outbox_events_aggregate_sequence_positive"
        ),
        sa.CheckConstraint(
            "delivery_attempts >= 0", name="ck_outbox_events_delivery_attempts_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "workspace_id", "event_id"],
            [
                "transitions.tenant_id",
                "transitions.environment_id",
                "transitions.workspace_id",
                "transitions.event_id",
            ],
            name="fk_outbox_transition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "event_id",
            name="pk_outbox_events",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "aggregate_id",
            "aggregate_sequence",
            name="uq_outbox_sequence",
        ),
    )
    op.create_index(
        "ix_outbox_events_claimable",
        "outbox_events",
        ["available_at", "claim_expires_at"],
        unique=False,
        postgresql_where=sa.text("delivered_at IS NULL"),
    )
    op.create_table(
        "outbox_consumer_receipts",
        *_scope(),
        sa.Column("consumer_name", sa.String(length=160), nullable=False),
        sa.Column("event_id", sa.String(length=240), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "consumer_name",
            "event_id",
            name="pk_outbox_consumer_receipts",
        ),
    )
    op.create_table(
        "projection_positions",
        *_scope(),
        sa.Column("projection_name", sa.String(length=160), nullable=False),
        sa.Column("aggregate_id", sa.String(length=240), nullable=False),
        sa.Column("indexed_through", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "indexed_through >= 0",
            name="ck_projection_positions_indexed_through_nonnegative",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "projection_name",
            "aggregate_id",
            name="pk_projection_positions",
        ),
    )


def _create_operation_tables() -> None:
    op.create_table(
        "operations",
        *_scope(),
        sa.Column("operation_id", sa.String(length=240), nullable=False),
        sa.Column("workspace_id", sa.String(length=240), nullable=False),
        sa.Column("case_id", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(length=71), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("problem", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_by", sa.String(length=240), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("cancel_requested_by", sa.String(length=160), nullable=True),
        sa.Column("cancel_idempotency_key", sa.String(length=240), nullable=True),
        sa.Column("cancel_correlation_id", sa.String(length=160), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version >= 0", name="ck_operations_version_nonnegative"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_operations_attempt_count_nonnegative"),
        sa.CheckConstraint(
            "max_attempts > 0 AND max_attempts <= 10",
            name="ck_operations_max_attempts_bounded",
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','succeeded','failed','cancelling','cancelled')",
            name="ck_operations_state_known",
        ),
        sa.CheckConstraint(
            "(cancel_requested = false AND cancel_requested_by IS NULL AND "
            "cancel_idempotency_key IS NULL AND cancel_correlation_id IS NULL AND "
            "cancel_requested_at IS NULL) OR (cancel_requested = true AND "
            "cancel_requested_by IS NOT NULL AND cancel_idempotency_key IS NOT NULL AND "
            "cancel_correlation_id IS NOT NULL AND cancel_requested_at IS NOT NULL)",
            name="ck_operations_cancellation_context_complete",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "environment_id", "operation_id", name="pk_operations"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "workspace_id",
            "idempotency_key",
            name="uq_operation_workspace_idempotency",
        ),
    )
    op.create_index(
        "ix_operations_claimable",
        "operations",
        ["next_attempt_at", "lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("state IN ('queued','running','cancelling')"),
    )
    op.create_table(
        "job_checkpoints",
        *_scope(),
        sa.Column("operation_id", sa.String(length=240), nullable=False),
        sa.Column("checkpoint_sequence", sa.Integer(), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "checkpoint_sequence > 0", name="ck_job_checkpoints_checkpoint_sequence_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "operation_id"],
            ["operations.tenant_id", "operations.environment_id", "operations.operation_id"],
            name="fk_checkpoint_operation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "environment_id",
            "operation_id",
            "checkpoint_sequence",
            name="pk_job_checkpoints",
        ),
    )


def downgrade() -> None:
    raise RuntimeError("OAK database migrations are forward-only; restore a backup instead")
