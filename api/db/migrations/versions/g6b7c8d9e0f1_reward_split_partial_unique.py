"""提现拆分修复: rewards.source_payment_order_id 唯一索引改部分索引

拆分锁定产生的 withdrawing 行复用原 source_payment_order_id，
违反全表唯一约束导致提现 500。索引本意是支付回调幂等兜底，
改为仅约束非终态拆分行。

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-08-21
"""
from __future__ import annotations

from alembic import op

revision = "g6b7c8d9e0f1"
down_revision = ("e1f2a3b4c5d6", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_rewards_source_order", table_name="rewards")
    op.create_index(
        "ix_rewards_source_order",
        "rewards",
        ["source_payment_order_id"],
        unique=True,
        postgresql_where="status IN ('verifying', 'available', 'frozen')",
    )


def downgrade() -> None:
    op.drop_index("ix_rewards_source_order", table_name="rewards")
    op.create_index("ix_rewards_source_order", "rewards", ["source_payment_order_id"], unique=True)
