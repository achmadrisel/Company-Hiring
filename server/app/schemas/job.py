from pydantic import BaseModel
from typing import Optional, List
import enum

class JobTypeEnum(str, enum.Enum):
    """Enumeration for job types."""

    internship = "internship"
    apprenticeship = "apprenticeship"
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    freelance = "freelance"

class JobModelEnum(str, enum.Enum):
    """Enumeration for job models."""

    remote = "remote"
    hybrid = "hybrid"
    on_site = "on_site"

class JobDescriptionDetails(BaseModel):
    description: str
    requirements: List[str]
    jobdesk: List[str]
    benefits: List[str]

class JobBase(BaseModel):
    """Base model for job creation and update."""

    job_type: JobTypeEnum
    job_model: JobModelEnum
    title: str
    description: JobDescriptionDetails
    location: Optional[str] = None
    top_k: Optional[int] = 50
    rerank: Optional[int] = 5

class JobCreate(JobBase):
    """Model for creating a new job."""

    pass

class JobUpdate(BaseModel):
    """Model for updating an existing job."""

    job_type: Optional[JobTypeEnum] = None
    job_model: Optional[JobModelEnum] = None
    title: Optional[str] = None
    description: Optional[JobDescriptionDetails] = None
    location: Optional[str] = None
    top_k: Optional[int] = None
    rerank: Optional[int] = None
    status: Optional[str] = None

from datetime import datetime
from uuid import UUID

class JobResponse(JobBase):
    id: UUID
    recruiter_id: UUID
    status: str
    closed_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True