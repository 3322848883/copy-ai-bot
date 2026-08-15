"""上线就绪: 平台 USDT 收款地址表（后台管理）

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f607
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b2c3d4e5f607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("network", sa.String(8), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    )
    op.create_index("ix_platform_addresses_network", "platform_addresses", ["network"])


def downgrade() -> None:
    op.drop_index("ix_platform_addresses_network", table_name="platform_addresses")
    op.drop_table("platform_addresses")
