"""strategies 加 description + name_customized：已添加池编辑名称/介绍

Revision ID: l3c4d5e6f7a8
Revises: k2b3c4d5e6f7
Create Date: 2026-08-24

- description：策略介绍（管理员自定义，策略广场详情页展示）
- name_customized：名称是否被管理员自定义过——模式B（自动跟单同步）每次
  同步会把 display_name 重置为「昵称（id）」，管理员改过后置 True，同步不再覆盖。
"""
from alembic import op
import sqlalchemy as sa

revision = "l3c4d5e6f7a8"
down_revision = "k2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "strategies",
        sa.Column("name_customized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("strategies", "name_customized")
    op.drop_column("strategies", "description")
