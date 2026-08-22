"""copy_orders 加 created_at：失败订单也要有时间

Revision ID: h7c8d9e0f1a2
Revises: g6b7c8d9e0f1
Create Date: 2026-08-22

此前 executed_at 仅成交时写入，失败/待定订单无任何时间字段——
后台订单页与用户端"最近订单"里失败行显示"—"。
created_at = 订单落库（下单尝试）时刻，NOT NULL 兜底回填 executed_at。
"""
from alembic import op
import sqlalchemy as sa

revision = "h7c8d9e0f1a2"
down_revision = "g6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "copy_orders",
        # ★ server_default 必须落库为 DEFAULT now()：模型 server_default=func.now() 时
        #   SQLAlchemy INSERT 会省略该列，列级无默认值将直接 NOT NULL 违规
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    # 回填：历史行优先用成交时间，无成交时间的用当前时刻
    op.execute(
        "UPDATE copy_orders SET created_at = COALESCE(executed_at, NOW()) WHERE created_at IS NULL"
    )
    op.alter_column("copy_orders", "created_at", nullable=False)
    op.create_index("ix_copy_orders_created_at", "copy_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_copy_orders_created_at", table_name="copy_orders")
    op.drop_column("copy_orders", "created_at")
