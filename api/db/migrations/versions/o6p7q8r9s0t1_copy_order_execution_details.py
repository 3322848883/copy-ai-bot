"""copy_orders 保存交易所真实成交明细

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-08-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o6p7q8r9s0t1"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "copy_orders",
        sa.Column("filled_qty", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column("copy_orders", sa.Column("avg_price", sa.Float(), nullable=True))
    op.add_column(
        "copy_orders", sa.Column("exchange_order_id", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "copy_orders", sa.Column("client_order_id", sa.String(length=32), nullable=True)
    )
    op.create_index(
        "ix_copy_orders_client_order_id", "copy_orders", ["client_order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_copy_orders_client_order_id", table_name="copy_orders")
    op.drop_column("copy_orders", "client_order_id")
    op.drop_column("copy_orders", "exchange_order_id")
    op.drop_column("copy_orders", "avg_price")
    op.drop_column("copy_orders", "filled_qty")
