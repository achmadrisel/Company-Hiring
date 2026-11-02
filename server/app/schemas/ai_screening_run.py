from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional


class AIScreeningRunResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    candidates_screened: int

    class Config:
        from_attributes = True
