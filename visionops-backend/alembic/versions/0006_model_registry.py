"""Add model_artifacts registry table.

Revision ID: 0006_model_registry
Revises: 0005_roi_ppe
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_model_registry"
down_revision: Union[str, Sequence[str], None] = "0005_roi_ppe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

model_role = postgresql.ENUM("detector", "ppe", name="model_role", create_type=False)
model_format = postgresql.ENUM("onnx", "pytorch", name="model_format", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    op.execute("DO $$ BEGIN CREATE TYPE model_role AS ENUM ('detector', 'ppe'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE model_format AS ENUM ('onnx', 'pytorch'); EXCEPTION WHEN duplicate_object THEN null; END $$;")

    if "model_artifacts" not in tables:
        op.create_table(
            "model_artifacts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("role", model_role, nullable=False),
            sa.Column("format", model_format, nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("role", "name", "version", name="uq_model_role_name_version"),
        )
        op.create_index("ix_model_artifacts_name", "model_artifacts", ["name"])
        op.create_index("ix_model_artifacts_role", "model_artifacts", ["role"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "model_artifacts" in tables:
        op.drop_index("ix_model_artifacts_role", table_name="model_artifacts")
        op.drop_index("ix_model_artifacts_name", table_name="model_artifacts")
        op.drop_table("model_artifacts")
    op.execute("DROP TYPE IF EXISTS model_format")
    op.execute("DROP TYPE IF EXISTS model_role")
