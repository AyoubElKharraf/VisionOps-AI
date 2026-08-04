"""Add optional active schedule fields to roi_zones.

Revision ID: 0004_roi_schedule
Revises: 0003_roi_loitering
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_roi_schedule"
down_revision: Union[str, Sequence[str], None] = "0003_roi_loitering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}

    if "schedule_enabled" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "schedule_start" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("schedule_start", sa.String(5), nullable=False, server_default="00:00"),
        )
    if "schedule_end" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("schedule_end", sa.String(5), nullable=False, server_default="23:59"),
        )
    if "schedule_days" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column(
                "schedule_days",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[0,1,2,3,4,5,6]'::jsonb"),
            ),
        )
    if "schedule_timezone" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("schedule_timezone", sa.String(64), nullable=False, server_default="UTC"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}
    for name in (
        "schedule_timezone",
        "schedule_days",
        "schedule_end",
        "schedule_start",
        "schedule_enabled",
    ):
        if name in columns:
            op.drop_column("roi_zones", name)
