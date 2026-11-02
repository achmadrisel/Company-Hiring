"""Add hybrid search support: tsvector, HNSW, rrf_score

Revision ID: 4b6f0a1c9d2e
Revises: a1b2c3d4e5f6
Create Date: 2026-07-31 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4b6f0a1c9d2e'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEARCH_VECTOR_EXPR = (
    "to_tsvector('english', "
    "COALESCE(resume_text->>'candidate_summary', '') || ' ' || "
    "COALESCE((resume_text->'skills')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'education')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'work_experiences')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'projects')::text, '[]') || ' ' || "
    "COALESCE((resume_text->'certifications')::text, '[]')"
    ")"
)


def upgrade() -> None:
    op.add_column(
        'candidate_cvs',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPR, persisted=True),
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidate_cvs_embedding "
        "ON candidate_cvs USING hnsw (embedding vector_cosine_ops)"
    )
    op.add_column(
        'ai_screenings',
        sa.Column('rrf_score', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ai_screenings', 'rrf_score')
    op.execute("DROP INDEX IF EXISTS ix_candidate_cvs_embedding")
    op.drop_index('ix_candidate_cvs_search_vector', table_name='candidate_cvs')
    op.drop_column('candidate_cvs', 'search_vector')
