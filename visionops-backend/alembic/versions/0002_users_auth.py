"""Add users table for JWT authentication.

Revision ID: 0002_users_auth
Revises: 0001_initial_schema
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_users_auth"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE user_role AS ENUM ('admin', 'operator');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )

    if "users" not in tables:
        user_role = postgresql.ENUM("admin", "operator", name="user_role", create_type=False)
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("username", sa.String(length=80), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=160), nullable=True),
            sa.Column("role", user_role, nullable=False, server_default="operator"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            sa.UniqueConstraint("username"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" in set(inspector.get_table_names()):
        op.drop_index("ix_users_username", table_name="users")
        op.drop_table("users")
    op.execute(sa.text("DROP TYPE IF EXISTS user_role"))
