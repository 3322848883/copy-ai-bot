"""生产核查修复: 支付重放防护 + 奖励唯一约束

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ★ H1 修复：同一 tx_hash 不可激活多个订单（failed 除外，允许作废重试）
    # ★ 生产修复：where 用 sa.text 生成 SQL 表达式（op.f(...) != "..." 会求值为 Python bool 导致编译失败）
    op.create_index(
        "ix_payment_orders_tx_hash_active",
        "payment_orders",
        ["tx_hash"],
        unique=True,
        postgresql_where=sa.text("status != 'failed'"),
        sqlite_where=sa.text("status != 'failed'"),
    )
    # ★ H3 修复：同一订单只发一次奖励（DB 层兜底幂等）
    op.create_index(
        "ix_rewards_source_order",
        "rewards",
        ["source_payment_order_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_rewards_source_order", table_name="rewards")
    op.drop_index("ix_payment_orders_tx_hash_active", table_name="payment_orders")
