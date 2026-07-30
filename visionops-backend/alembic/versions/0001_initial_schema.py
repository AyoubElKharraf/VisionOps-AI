"""Initial VisionOps schema (cameras, roi_zones, alerts, alert_events).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-29

Idempotent enough for existing demo volumes previously created with create_all().
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

alert_type = postgresql.ENUM(
    "roi_intrusion",
    "tripwire",
    "loitering",
    "custom",
    name="alert_type",
    create_type=False,
)
alert_status = postgresql.ENUM(
    "pending",
    "processing",
    "ready",
    "failed",
    name="alert_status",
    create_type=False,
)


def _existing_tables(bind) -> set[str]:
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _existing_columns(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_indexes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # Enums (Postgres). Ignore if already created by previous create_all().
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE alert_type AS ENUM (
                    'roi_intrusion', 'tripwire', 'loitering', 'custom'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE alert_status AS ENUM (
                    'pending', 'processing', 'ready', 'failed'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )

    tables = _existing_tables(bind)

    if "cameras" not in tables:
        op.create_table(
            "cameras",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("source_url", sa.String(length=512), nullable=False),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint("name"),
        )

    if "roi_zones" not in tables:
        op.create_table(
            "roi_zones",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("color", sa.String(length=32), nullable=False, server_default="#ef4444"),
            sa.Column("max_allowed_objects", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("forbidden_classes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        )

    if "alerts" not in tables:
        op.create_table(
            "alerts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("alert_type", alert_type, nullable=False),
            sa.Column("status", alert_status, nullable=False, server_default="pending"),
            sa.Column(
                "incident_status",
                sa.String(length=32),
                nullable=False,
                server_default="open",
            ),
            sa.Column("zone_name", sa.String(length=120), nullable=True),
            sa.Column("class_name", sa.String(length=80), nullable=True),
            sa.Column("track_id", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("assigned_to", sa.String(length=120), nullable=True),
            sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", sa.String(length=120), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("source_video_path", sa.String(length=1024), nullable=True),
            sa.Column("frame_index", sa.Integer(), nullable=True),
            sa.Column("snapshot_object_key", sa.String(length=512), nullable=True),
            sa.Column("clip_object_key", sa.String(length=512), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
        )
    else:
        alert_cols = _existing_columns(bind, "alerts")
        additive = [
            ("incident_status", sa.Column("incident_status", sa.String(32), nullable=False, server_default="open")),
            ("assigned_to", sa.Column("assigned_to", sa.String(120), nullable=True)),
            ("acknowledged_by", sa.Column("acknowledged_by", sa.String(120), nullable=True)),
            ("acknowledged_at", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)),
            ("resolved_by", sa.Column("resolved_by", sa.String(120), nullable=True)),
            ("resolved_at", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)),
            ("resolution_note", sa.Column("resolution_note", sa.Text(), nullable=True)),
        ]
        for name, column in additive:
            if name not in alert_cols:
                op.add_column("alerts", column)

    tables = _existing_tables(bind)
    if "alert_events" not in tables:
        op.create_table(
            "alert_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        )

    indexes = _existing_indexes(bind, "alert_events")
    if "ix_alert_events_alert_id" not in indexes and "alert_events" in _existing_tables(bind):
        op.create_index("ix_alert_events_alert_id", "alert_events", ["alert_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_events_alert_id", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_table("alerts")
    op.drop_table("roi_zones")
    op.drop_table("cameras")
    op.execute(sa.text("DROP TYPE IF EXISTS alert_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS alert_type"))
