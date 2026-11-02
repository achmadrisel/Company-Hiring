from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.core.database import Base
from pgvector.sqlalchemy import Vector

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recruiter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_type = Column(String, nullable=False)
    job_model = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(JSONB, nullable=False)
    location = Column(String, nullable=True)
    embedding = Column(Vector(1024))
    top_k = Column(Integer, default=50)
    rerank = Column(Integer, default=5)
    status = Column(
        String,
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="check_job_status"
        ),
        default='open'
    )
    closed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())