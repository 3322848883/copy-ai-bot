"""trader hide_position (Gate config.is_hide) for admin listing mode decision

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-20

带单员是否隐藏当前持仓：True → 公开采集拿不到仓位（trader/position 返回空），
上架只能走模式B（绑定 API 镜像跟单）；NULL = 尚未采集（detail 未拉过）。
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "traders",
        sa.Column("hide_position", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("traders", "hide_position")
