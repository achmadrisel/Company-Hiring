from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class AIScreeningRun(Base):
    __tablename__ = "ai_screening_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        String,
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="check_ai_screening_run_status",
        ),
        nullable=False,
        default="running",
    )
    started_at = Column(DateTime, nullable=False, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    candidates_screened = Column(Integer, nullable=False, default=0)
