"""strategies 加 source 列（A=公开广场审核上架 / B=跟单同步自动上架）

Revision ID: c8d9e0f1a2b3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("source", sa.String(1), nullable=False, server_default="A"))
    # 现存策略全部由模式2 跟单同步（ensure_followed_strategy）创建——标 B，
    # 否则迁移后第一轮 delist_unfollowed 会把它们全部下架。
    op.execute("UPDATE strategies SET source = 'B'")


def downgrade() -> None:
    op.drop_column("strategies", "source")
