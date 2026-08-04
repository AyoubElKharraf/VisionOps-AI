"""Add require_hardhat and ppe_violation alert type.

Revision ID: 0005_roi_ppe
Revises: 0004_roi_schedule
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_roi_ppe"
down_revision: Union[str, Sequence[str], None] = "0004_roi_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}
    if "require_hardhat" not in columns:
        op.add_column(
            "roi_zones",
            sa.Column("require_hardhat", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    op.execute(sa.text("ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'ppe_violation'"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("roi_zones")}
    if "require_hardhat" in columns:
        op.drop_column("roi_zones", "require_hardhat")
    # Postgres cannot easily remove enum values — leave ppe_violation in place.
