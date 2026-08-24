"""position_snapshots 加 face_value 列（合约面值，update_marks 直接读）。

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-08-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "position_snapshots",
        sa.Column("face_value", sa.Float(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("position_snapshots", "face_value")
