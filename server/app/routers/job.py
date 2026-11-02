from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.services.job_service import job_service
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.core.dependencies import require_role
from app.core.exceptions import JobNotFoundError, RecruiterNotFoundError
from app.services.ai_screening_service import ai_screening_service
from app.services.ai_screening_mlflow_service import AIScreeningMLFlowService
from app.eval.mlflow_tracker import get_tracker
from app.core.config import get_settings
from app.models.ai_screening_run import AIScreeningRun
from app.schemas.ai_screening_run import AIScreeningRunResponse
from app.models.job import Job
import logging
import traceback
from uuid import UUID
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(job: JobCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(require_role("recruiter"))):
    try:
        return await job_service.create_job(db, job, UUID(current_user["id"]))
    except RecruiterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@router.get("/", response_model=List[JobResponse])
async def list_jobs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    try:
        jobs = await job_service.list_jobs(db, skip, limit)
        return list(jobs)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@router.get("/recruiter", response_model=List[JobResponse])
async def get_jobs_by_recruiter(db: AsyncSession = Depends(get_db), current_user: dict = Depends(require_role("recruiter"))):
    try:
        jobs = await job_service.get_jobs_by_recruiter(db, UUID(current_user["id"]))
        return list(jobs)
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        job = await job_service.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
async def run_ai_screening(job_id: UUID):
    logger.info("Background AI screening task started for job %s", job_id)
    _settings = get_settings()
    try:
        from app.core.database import async_session_factory
        from app.services.job_service import job_service
        async with async_session_factory() as db_session:
            job = await job_service.get_job(db_session, job_id)
            if job:
                if _settings.MLFLOW_TRACKING_ENABLED:
                    tracker = get_tracker()
                    service = AIScreeningMLFlowService(tracker=tracker)
                else:
                    service = ai_screening_service
                run_id = await service.screen_application(db_session, job)
            else:
                logger.warning("Background AI screening: job %s not found", job_id)
    except Exception as e:
        logger.error("Background AI screening task failed for job %s: %s", job_id, e)
        logger.error(traceback.format_exc())
            
@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: UUID, 
    job_update: JobUpdate, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db), 
    current_user: dict = Depends(require_role("recruiter"))
):
    try:
        result = await job_service.update_job(db, job_id, job_update, UUID(current_user["id"]))
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or not authorized")
        
        job, trigger_ai = result
        if trigger_ai:
            background_tasks.add_task(run_ai_screening, job.id)
            
        return job
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@router.get("/{job_id}/ai-screening-runs", response_model=List[AIScreeningRunResponse])
async def get_ai_screening_runs(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("recruiter"))
):
    """Get the AI screening run history for a job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if str(job.recruiter_id) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view screening runs for this job")

    runs_result = await db.execute(
        select(AIScreeningRun)
        .where(AIScreeningRun.job_id == job_id)
        .order_by(AIScreeningRun.started_at.desc())
    )
    runs = runs_result.scalars().all()
    return list(runs)

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(require_role("recruiter"))):
    try:
        success = await job_service.delete_job(db, job_id, UUID(current_user["id"]))
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or not authorized to delete")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
