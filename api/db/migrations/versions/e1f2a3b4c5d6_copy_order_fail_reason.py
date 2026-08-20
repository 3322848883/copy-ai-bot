"""copy_orders fail_reason text column (failure detail for admin)

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-08-20

failure_category 只是 11 值枚举，具体原因（交易所报错原文/风控规则/校验消息）
此前只进日志不落库——后台跟单记录失败全部显示"其他"。
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("copy_orders", sa.Column("fail_reason", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("copy_orders", "fail_reason")
