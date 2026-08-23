"""identities 加 exchange_invite_status：交易所邀请码绑定复核状态

Revision ID: k2b3c4d5e6f7
Revises: j9e0f1a2b3c4
Create Date: 2026-08-24

绑定交易所邀请码后不再直接免订阅——进入 pending 待复核，
后台管理员批准（approved）后才获得合作归属免订阅资格；驳回（rejected）可重新绑定。
存量已绑定记录回填为 pending，需管理员复核。
"""
from alembic import op
import sqlalchemy as sa

revision = "k2b3c4d5e6f7"
down_revision = "j9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identities",
        sa.Column("exchange_invite_status", sa.String(length=16), nullable=True),
    )
    op.execute(
        "UPDATE identities SET exchange_invite_status = 'pending' "
        "WHERE exchange_invite_code IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("identities", "exchange_invite_status")
