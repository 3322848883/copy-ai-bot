"""M6: 灰度发布 + 沙箱模拟盘列

Revision ID: a1b2c3d4e5f6
Revises: cfbdf6563a03
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "cfbdf6563a03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # T6.1 策略灰度比例（默认 100% 全量）
    op.add_column("strategies", sa.Column("gray_pct", sa.Integer(), nullable=False, server_default="100"))
    # T6.2 沙箱模拟盘标记
    op.add_column("copy_bots", sa.Column("paper", sa.Boolean(), nullable=False, server_default=sa.false()))
    # 真实信号源：带单员昵称 + 跟单人数（M2 生产采集）
    op.add_column("traders", sa.Column("name", sa.String(64), nullable=True))
    op.add_column("traders", sa.Column("followers", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("traders", "followers")
    op.drop_column("traders", "name")
    op.drop_column("copy_bots", "paper")
    op.drop_column("strategies", "gray_pct")
