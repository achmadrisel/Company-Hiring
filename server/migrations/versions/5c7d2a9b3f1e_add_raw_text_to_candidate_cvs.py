"""Add raw_text to candidate_cvs and index it for full-text search

Revision ID: 5c7d2a9b3f1e
Revises: 4b6f0a1c9d2e
Create Date: 2026-08-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5c7d2a9b3f1e'
down_revision: Union[str, None] = '4b6f0a1c9d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_SEARCH_VECTOR_EXPR = (
    "to_tsvector('english', "
    "COALESCE(resume_text->>'candidate_summary', '') || ' ' || "
    "COALESCE((resume_text->'skills')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'education')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'work_experiences')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'projects')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'certifications')::text, '[]')"
    ")"
)

NEW_SEARCH_VECTOR_EXPR = (
    "to_tsvector('english', COALESCE(raw_text, "
    "COALESCE(resume_text->>'candidate_summary', '') || ' ' || "
    "COALESCE((resume_text->'skills')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'education')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'work_experiences')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'projects')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'certifications')::text, '[]')"
    "))"
)


def upgrade() -> None:
    op.add_column(
        'candidate_cvs',
        sa.Column('raw_text', sa.Text(), nullable=True),
    )
    op.drop_index('ix_candidate_cvs_search_vector', table_name='candidate_cvs')
    op.drop_column('candidate_cvs', 'search_vector')
    op.add_column(
        'candidate_cvs',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(NEW_SEARCH_VECTOR_EXPR, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_candidate_cvs_search_vector',
        'candidate_cvs',
        ['search_vector'],
        unique=False,
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_candidate_cvs_search_vector', table_name='candidate_cvs')
    op.drop_column('candidate_cvs', 'search_vector')
    op.drop_column('candidate_cvs', 'raw_text')
    op.add_column(
        'candidate_cvs',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(OLD_SEARCH_VECTOR_EXPR, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_candidate_cvs_search_vector',
        'candidate_cvs',
        ['search_vector'],
        unique=False,
        postgresql_using='gin',
    )
