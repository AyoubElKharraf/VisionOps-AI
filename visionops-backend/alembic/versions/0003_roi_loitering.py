"""Add loitering_seconds to roi_zones.

Revision ID: 0003_roi_loitering
Revises: 0002_users_auth
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_roi_loitering"
down_revision: Union[str, Sequence[str], None] = "0002_users_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}
    if "loitering_seconds" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("loitering_seconds", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}
    if "loitering_seconds" in columns:
        op.drop_column("roi_zones", "loitering_seconds")
