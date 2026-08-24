"""position_snapshots 加 realized_pnl：减仓/平仓记录已实现盈亏

Revision ID: m4n5o6p7q8r9
Revises: l3c4d5e6f7a8
Create Date: 2026-08-24

此前平仓只置 is_open=False，不记录已实现盈亏；snapshot_pnl 以
SUM(unrealized_pnl) WHERE is_open=False 兜底——而 mark_price 从不刷新，
unrealized_pnl 恒为 0，导致已实现盈亏恒为 0（模拟盘/实盘均失真）。
新增 realized_pnl 列，减仓/平仓时按 (close-entry)×qty×方向 累计。
"""
from alembic import op
import sqlalchemy as sa

revision = "m4n5o6p7q8r9"
down_revision = "l3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "position_snapshots",
        sa.Column("realized_pnl", sa.Float(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("position_snapshots", "realized_pnl")
