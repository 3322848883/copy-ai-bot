"""H4 支付加固：paid_amount_usdt 列 + tx_hash 唯一部分索引

Revision ID: b2c3d4e5f6a7
Revises: f5a6b7c8d9e0
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_orders", sa.Column("paid_amount_usdt", sa.Float(), nullable=True))
    # ★ H1/H4 唯一部分索引：非 failed 订单的 tx_hash 数据库层唯一，
    #   应用层查重（check-then-act）之外的第二道防线，防并发重放穿透
    op.create_index(
        "uq_payment_orders_tx_hash_active",
        "payment_orders",
        ["tx_hash"],
        unique=True,
        postgresql_where=sa.text("tx_hash IS NOT NULL AND status <> 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_payment_orders_tx_hash_active", table_name="payment_orders")
    op.drop_column("payment_orders", "paid_amount_usdt")
