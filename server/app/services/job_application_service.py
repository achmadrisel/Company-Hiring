from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.job_application import JobApplication
from app.models.candidate_cv import CandidateCV
from app.models.ai_screening import AIScreening
from uuid import UUID

class JobApplicationService:
    async def create_application(self, db: AsyncSession, job_id: UUID, candidate_id: UUID, cv_id: UUID) -> JobApplication:
        """Create a new job application."""
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError("Job not found")
        if job.status == "closed":
            raise ValueError("Cannot apply to a closed job")
        
        result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise ValueError("Candidate not found")
        
        result = await db.execute(select(CandidateCV).where(CandidateCV.id == cv_id, CandidateCV.candidate_id == candidate_id))
        candidate_cv = result.scalar_one_or_none()
        if not candidate_cv:
            raise ValueError("Candidate CV not found or does not belong to the candidate")
        
        application = JobApplication(
            job_id=job_id,
            candidate_id=candidate_id,
            cv_id=cv_id
        )
        db.add(application)
        await db.flush()
        await db.refresh(application)
        return application
    
    async def update_application_status(self, db: AsyncSession, application_id: UUID, new_status: str) -> JobApplication:
        """Update the status of a job application."""
        valid_statuses = ["applied", "screened", "shortlisted", "rejected"]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

        result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
        application = result.scalar_one_or_none()
        if not application:
            raise ValueError("Application not found")

        application.status = new_status
        await db.commit()
        await db.refresh(application)
        return application

    async def get_application_detail(
        self, db: AsyncSession, job_id: UUID, application_id: UUID
    ) -> tuple | None:
        """Retrieve a single application joined with candidate, CV, and AI screening."""
        stmt = (
            select(JobApplication, Candidate, CandidateCV, AIScreening)
            .join(Candidate, JobApplication.candidate_id == Candidate.id)
            .join(CandidateCV, JobApplication.cv_id == CandidateCV.id)
            .outerjoin(AIScreening, JobApplication.id == AIScreening.job_application_id)
            .where(
                JobApplication.job_id == job_id,
                JobApplication.id == application_id,
            )
        )
        result = await db.execute(stmt)
        return result.first()

job_application_service = JobApplicationService()
