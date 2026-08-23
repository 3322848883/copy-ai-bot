"""strategies 加 follow_enabled：跟单是否开放（阀门上移后台管理员）

Revision ID: j9e0f1a2b3c4
Revises: i8d9e0f1a2b3
Create Date: 2026-08-24

此前用户端是否可跟单由 hide_position(隐藏仓位) 隐式推导——
隐藏仓位→"即将开放跟单"，把运营决策暴露给用户、体验差。
改造：阀门上移后台管理员，新增 follow_enabled 显式开关。
默认 true（上架即开放），隐藏仓位仅作后台数据标记不再影响用户端。
"""
from alembic import op
import sqlalchemy as sa

revision = "j9e0f1a2b3c4"
down_revision = "i8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("follow_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("strategies", "follow_enabled")