"""Change AI screening feedback to JSONB

Revision ID: 7f4d0e7c9b21
Revises: 38cad2963d4e
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7f4d0e7c9b21'
down_revision: Union[str, None] = '38cad2963d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'ai_screenings',
        'feedback',
        existing_type=sa.TEXT(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using=(
            "jsonb_build_object("
            "'matched', '[]'::jsonb, "
            "'missing', '[]'::jsonb, "
            "'strengths', '[]'::jsonb, "
            "'concerns', '[]'::jsonb, "
            "'interview_questions', '[]'::jsonb, "
            "'recommendation', jsonb_build_object("
            "'decision', 'Proceed', "
            "'reason', coalesce(feedback, '')"
            ")"
            ")"
        ),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'ai_screenings',
        'feedback',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.TEXT(),
        postgresql_using="feedback->'recommendation'->>'reason'",
        existing_nullable=True,
    )
