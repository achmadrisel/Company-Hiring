from sqlalchemy import Column, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class AIScreening(Base):
    __tablename__ = "ai_screenings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_application_id = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="CASCADE"))
    rerank_score = Column(Float, nullable=True)
    rrf_score = Column(Float, nullable=True)
    feedback = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=func.now())
