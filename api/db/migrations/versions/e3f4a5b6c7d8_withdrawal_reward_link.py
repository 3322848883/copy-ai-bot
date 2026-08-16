"""生产核查修复: 提现资金锁定绑定具体提现单

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reward.withdrawal_id: 锁定资金归属于具体提现单，避免并发提现互相解锁/误发
    op.add_column("rewards", sa.Column("withdrawal_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rewards_withdrawal_id_withdrawals",
        "rewards",
        "withdrawals",
        ["withdrawal_id"],
        ["id"],
    )
    op.create_index("ix_rewards_withdrawal_id", "rewards", ["withdrawal_id"])


def downgrade() -> None:
    op.drop_index("ix_rewards_withdrawal_id", table_name="rewards")
    op.drop_constraint("fk_rewards_withdrawal_id_withdrawals", "rewards", type_="foreignkey")
    op.drop_column("rewards", "withdrawal_id")