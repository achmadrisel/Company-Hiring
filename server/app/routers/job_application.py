from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.schemas.job_application import JobApplicationCreate, JobApplicationResponse, JobApplicationStatusUpdate, JobApplicationDetail
from app.schemas.candidate import CandidateCreate, LastEducationEnum, YearsOfExperienceEnum
from app.schemas.candidate_cv import CandidateCVSchema
from app.services.job_application_service import job_application_service
from app.services.candidate_service import candidate_service
from app.services.candidate_cv_service import candidate_cv_service
from app.models.job_application import JobApplication
from app.models.ai_screening import AIScreening
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.candidate_cv import CandidateCV
from app.core.dependencies import require_role
from typing import List
from uuid import UUID

router = APIRouter(prefix="/jobs/{job_id}/applications", tags=["Job Applications"])

def _serialize_application(app: JobApplication, cand: Candidate, cv: CandidateCV, ai: AIScreening | None) -> dict:
    app_dict = {
        "id": app.id,
        "job_id": app.job_id,
        "status": app.status,
        "applied_at": app.applied_at,
        "candidate": {
            "id": cand.id,
            "full_name": cand.full_name,
            "email": cand.email,
            "phone_number": cand.phone_number,
            "date_of_birth": cand.date_of_birth,
            "last_education": cand.last_education,
            "years_of_experience": cand.years_of_experience,
            "profile_url": cand.profile_url
        },
        "cv": {
            "id": cv.id,
            "file_url": cv.file_url,
            "resume_text": cv.resume_text,
            "created_at": cv.created_at
        }
    }

    if ai:
        app_dict["ai_screening"] = {
            "id": ai.id,
            "rrf_score": ai.rrf_score,
            "rerank_score": ai.rerank_score,
            "feedback": ai.feedback,
            "created_at": ai.created_at
        }
    else:
        app_dict["ai_screening"] = None

    return app_dict

async def _verify_job_ownership(job_id: UUID, current_user: dict, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(job.recruiter_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    return job

@router.get("/", response_model=List[JobApplicationDetail])
async def get_job_applicants(job_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(require_role(["recruiter"]))):
    """Get all applicants and their CVs for a specific job."""
    await _verify_job_ownership(job_id, current_user, db)

    stmt = (
        select(JobApplication, Candidate, CandidateCV, AIScreening)
        .join(Candidate, JobApplication.candidate_id == Candidate.id)
        .join(CandidateCV, JobApplication.cv_id == CandidateCV.id)
        .outerjoin(AIScreening, JobApplication.id == AIScreening.job_application_id)
        .where(JobApplication.job_id == job_id)
    )
    applications_result = await db.execute(stmt)
    applications = applications_result.all()

    return [_serialize_application(app, cand, cv, ai) for app, cand, cv, ai in applications]

@router.get("/{application_id}", response_model=JobApplicationDetail)
async def get_job_application(
    job_id: UUID,
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role(["recruiter"])),
):
    """Get a single applicant and their CV for a specific job."""
    await _verify_job_ownership(job_id, current_user, db)

    row = await job_application_service.get_application_detail(db, job_id, application_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")

    app, cand, cv, ai = row
    return _serialize_application(app, cand, cv, ai)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def apply_to_job(
    job_id: UUID,
    full_name: str = Form(...),
    email: str = Form(...),
    phone_number: str = Form(...),
    date_of_birth: str = Form(...),
    last_education: LastEducationEnum = Form(...),
    years_of_experience: YearsOfExperienceEnum = Form(...),
    image: UploadFile = File(...),
    cv: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Endpoint for candidates to apply to a job."""
    
    candidate_data = CandidateCreate(
        full_name=full_name,
        email=email,
        phone_number=phone_number,
        date_of_birth=date_of_birth,
        last_education=last_education,
        years_of_experience=years_of_experience
    )

    try:
        # Step 1: Create candidate profile
        if not image.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            raise HTTPException(status_code=400, detail="Profile image must be a JPG or PNG file")
        
        file_data = await image.read()
        content_type = image.content_type
        candidate = await candidate_service.create_candidate(db, candidate_data, file_data, image.filename, content_type)

        # Step 2: Upload CV and create CandidateCV record
        if not cv.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        cv_data = await cv.read()
        cv_record = await candidate_cv_service.upload_cv(db, cv_data, cv.filename, candidate.id)

        # Step 3: Create job application
        application = await job_application_service.create_application(db, job_id, candidate.id, cv_record.id)

        return JobApplicationResponse(
            id=application.id,
            job_id=application.job_id,
            candidate_id=application.candidate_id,
            status=application.status,
            applied_at=application.applied_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {str(e)}")

@router.patch("/{application_id}/status")
async def update_application_status(
    job_id: UUID,
    application_id: UUID,
    update: JobApplicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role(["recruiter"]))
):
    """Update the status of a job application."""
    result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.recruiter_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this application")

    try:
        updated = await job_application_service.update_application_status(db, application_id, update.status)
        return JobApplicationResponse(
            id=updated.id,
            job_id=updated.job_id,
            candidate_id=updated.candidate_id,
            status=updated.status,
            applied_at=updated.applied_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

