from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Computed
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.sql import func
import uuid
from app.core.database import Base
from pgvector.sqlalchemy import Vector

class CandidateCV(Base):
    __tablename__ = "candidate_cvs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    file_url = Column(String, nullable=False)
    resume_text = Column(JSONB)
    raw_text = Column(Text)
    embedding = Column(Vector(1024))
    search_vector = Column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', COALESCE(raw_text, "
            "COALESCE(resume_text->>'candidate_summary', '') || ' ' || "
            "COALESCE((resume_text->'skills')::text, '[]') || ' ' || "
            "COALESCE((resume_text->'education')::text, '[]') || ' ' || "
            "COALESCE((resume_text->'work_experiences')::text, '[]') || ' ' || "
            "COALESCE((resume_text->'projects')::text, '[]') || ' ' || "
            "COALESCE((resume_text->'certifications')::text, '[]')"
            "))",
            persisted=True,
        ),
        nullable=True,
    )
    created_at = Column(DateTime, default=func.now())