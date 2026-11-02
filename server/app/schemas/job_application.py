from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.schemas.candidate_cv import CVDetails

class JobApplicationBase(BaseModel):
    candidate_id: UUID
    job_id: UUID

class JobApplicationCreate(JobApplicationBase):
    pass

class JobApplicationResponse(JobApplicationBase):
    id: UUID
    status: str
    applied_at: datetime
    
    class Config:
        from_attributes = True

class JobApplicationSchema(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID
    status: str
    applied_at: datetime

    class Config:
        from_attributes = True

class JobApplicationStatusUpdate(BaseModel):
    status: str

class CandidateInfoSchema(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone_number: str
    date_of_birth: str
    last_education: str
    years_of_experience: str
    profile_url: str

class CVInfoSchema(BaseModel):
    id: UUID
    file_url: str
    resume_text: Optional[CVDetails]
    created_at: datetime

class AIScreeningInfoSchema(BaseModel):
    id: UUID
    rrf_score: Optional[float]
    rerank_score: Optional[float]
    feedback: Optional[dict]
    created_at: datetime

class JobApplicationDetail(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    applied_at: datetime
    candidate: CandidateInfoSchema
    cv: CVInfoSchema
    ai_screening: Optional[AIScreeningInfoSchema]

    class Config:
        from_attributes = True