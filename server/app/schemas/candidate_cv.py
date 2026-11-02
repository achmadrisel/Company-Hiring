from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.schemas.candidate import CandidateResponse

class CVDetails(BaseModel):
    candidate_summary: str
    skills: List[str] = []
    education: List[str] = []
    work_experiences: List[str] = []
    projects: List[str] = []
    certifications: List[str] = []

class CandidateCVSchema(BaseModel):
    id: UUID
    candidate_id: UUID
    file_url: str
    resume_text: Optional[CVDetails]
    created_at: datetime

    class Config:
        from_attributes = True

class CandidateCVResponse(BaseModel):
    candidate: CandidateResponse
    candidate_cv: CandidateCVSchema

    class Config:
        from_attributes = True