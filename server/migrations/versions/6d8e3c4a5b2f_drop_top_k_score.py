"""Drop top_k_score from ai_screenings; rrf_score is the top-k value

Revision ID: 6d8e3c4a5b2f
Revises: 5c7d2a9b3f1e
Create Date: 2026-08-01 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6d8e3c4a5b2f'
down_revision: Union[str, None] = '5c7d2a9b3f1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('ai_screenings', 'top_k_score')


def downgrade() -> None:
    op.add_column(
        'ai_screenings',
        sa.Column('top_k_score', sa.Float(), nullable=True),
    )
