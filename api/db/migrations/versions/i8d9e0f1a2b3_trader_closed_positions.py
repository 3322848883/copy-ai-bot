"""trader_closed_positions：带单员已平仓记录表（详情页交易记录数据源）

Revision ID: i8d9e0f1a2b3
Revises: h7c8d9e0f1a2
Create Date: 2026-08-22

Gate close_position 接口数据（含真实方向/已实现盈亏/开平仓均价），
纯展示不入信号管道；对隐藏持仓交易员同样采集。
"""
from alembic import op
import sqlalchemy as sa

revision = "i8d9e0f1a2b3"
down_revision = "h7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trader_closed_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trader_id", sa.Integer(), sa.ForeignKey("traders.id"), nullable=False),
        sa.Column("gate_order_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("profit", sa.Float(), nullable=True),
        sa.Column("profit_rate", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("leverage", sa.Float(), nullable=True),
        sa.Column("margin", sa.Float(), nullable=True),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("trader_id", "gate_order_id", name="uq_closed_pos_order"),
    )
    op.create_index("ix_trader_closed_positions_trader_id", "trader_closed_positions", ["trader_id"])
    op.create_index("ix_trader_closed_positions_close_time", "trader_closed_positions", ["close_time"])


def downgrade() -> None:
    op.drop_index("ix_trader_closed_positions_close_time", table_name="trader_closed_positions")
    op.drop_index("ix_trader_closed_positions_trader_id", table_name="trader_closed_positions")
    op.drop_table("trader_closed_positions")
