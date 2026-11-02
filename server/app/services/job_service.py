from typing import List, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.job import Job
from app.models.user import User
from app.models.job_application import JobApplication
from app.models.candidate import Candidate
from app.models.candidate_cv import CandidateCV
from uuid import UUID
from datetime import datetime, timezone
from app.schemas.job import JobCreate, JobUpdate
from app.services.embedding_service import embedding_service

def build_job_embedding_text(description: dict) -> str:
    requirements = description.get("requirements", []) or []
    jobdesk = description.get("jobdesk", []) or []
    parts = [str(item).strip() for item in list(requirements) + list(jobdesk)]
    return " ".join(parts)

class JobService:
    """Service class for managing job postings."""

    async def create_job(self, db: AsyncSession, job_data: JobCreate, recruiter_id: UUID) -> Job:
        """Create a new job posting."""
        result = await db.execute(select(User).where(User.id == recruiter_id))
        recruiter = result.scalar_one_or_none()
        
        if not recruiter:
            raise ValueError("Recruiter not found")
        
        desc_text = build_job_embedding_text(job_data.description.model_dump())
        embedding = embedding_service.encode(desc_text)
        closed_at = datetime.now(timezone.utc).replace(tzinfo=None) if getattr(job_data, 'status', 'open') == 'closed' else None

        job = Job(
            recruiter_id=recruiter_id,
            job_type=job_data.job_type.value,
            job_model=job_data.job_model.value,
            title=job_data.title,
            description=job_data.description.model_dump(),
            location=job_data.location,
            top_k=job_data.top_k,
            rerank=job_data.rerank,
            embedding=embedding,
            closed_at=closed_at
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job
    
    async def list_jobs(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> Sequence[Job]:
        """List job postings with pagination."""
        result = await db.execute(select(Job).offset(skip).limit(limit))
        return result.scalars().all()
    
    async def get_jobs_by_recruiter(self, db: AsyncSession, recruiter_id: UUID) -> Sequence[Job]:
        """Get all job postings for a specific recruiter."""
        result = await db.execute(select(Job).where(Job.recruiter_id == recruiter_id))
        return result.scalars().all()
    
    async def get_job(self, db: AsyncSession, job_id: UUID) -> Job | None:
        """Retrieve a job posting by ID."""
        result = await db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()
    
    async def update_job(self, db: AsyncSession, job_id: UUID, job_data: JobUpdate, recruiter_id: UUID) -> Job | None:
        """Update a job posting."""
        result = await db.execute(select(Job).where(Job.id == job_id, Job.recruiter_id == recruiter_id))
        job = result.scalar_one_or_none()
        
        if not job:
            return None
            
        update_data = job_data.model_dump(exclude_unset=True)
        status_updated_to_closed = False
        
        if "status" in update_data:
            if update_data["status"] == "closed" and job.status != "closed":
                status_updated_to_closed = True
                update_data["closed_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
                
        if "description" in update_data and update_data["description"] != job.description:
            desc = update_data["description"]
            desc_text = build_job_embedding_text(desc)
            update_data["embedding"] = embedding_service.encode(desc_text)
            
        for key, value in update_data.items():
            if hasattr(value, "value"):
                setattr(job, key, value.value)
            else:
                setattr(job, key, value)
                
        await db.commit()
        await db.refresh(job)
        
        if status_updated_to_closed:
            from app.services.ai_screening_service import ai_screening_service
            # Wait for screening or spawn backward? Let's assume we do it inline for now, or preferably not block
            # Actually, to trigger it without blocking in the same session, better to do it inline or router background task.
            # As a service method, it might be better to return a flag if screening is needed. Let's do it in the router background tasks.
            
        return job, status_updated_to_closed
    
    async def delete_job(self, db: AsyncSession, job_id: UUID, recruiter_id: UUID) -> bool:
        """Delete a job posting and all related candidates and applications."""
        result = await db.execute(select(Job).where(Job.id == job_id, Job.recruiter_id == recruiter_id))
        job = result.scalar_one_or_none()
        if not job:
            return False
            
        # Get all applications for this job
        app_result = await db.execute(select(JobApplication).where(JobApplication.job_id == job_id))
        applications = app_result.scalars().all()
        candidate_ids = [app.candidate_id for app in applications]
        cv_ids = [app.cv_id for app in applications]
        
        # Delete Job Applications
        await db.execute(delete(JobApplication).where(JobApplication.job_id == job_id))
        
        # Delete Candidate CVs
        if cv_ids:
            await db.execute(delete(CandidateCV).where(CandidateCV.id.in_(cv_ids)))
            
        # Delete Candidates
        if candidate_ids:
            await db.execute(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
            
        await db.delete(job)
        await db.commit()
        return True

job_service = JobService()
