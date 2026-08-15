"""add signal percent column (leader position weight for qty conversion)

Revision ID: b2c3d4e5f607
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f607'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ★ 带单员持仓占比（∈[0,1]），用于 CopyEngine 侧 qty 换算
    op.add_column('source_signals', sa.Column('percent', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('source_signals', 'percent')