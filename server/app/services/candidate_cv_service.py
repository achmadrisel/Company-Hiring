from sqlalchemy.ext.asyncio import AsyncSession
from app.models.candidate_cv import CandidateCV
from app.schemas.candidate_cv import CandidateCVSchema
from app.services.s3_service import s3_service
from app.services.cv_processing_service import cv_processing_service
import uuid

class CandidateCVService:
    async def upload_cv(self, db: AsyncSession, file_data: bytes, file_name: str, candidate_id: uuid.UUID) -> CandidateCV:
        """Upload a candidate's CV and create a CandidateCV record."""
        file_ext = file_name.split('.')[-1] if '.' in file_name else 'pdf'
        new_file_name = f"candidate_cvs/{uuid.uuid4().hex}.{file_ext}"
        file_url = s3_service.upload_file(file_data, new_file_name, content_type='application/pdf')
        if not file_url:
            raise ValueError("Failed to upload CV")

        # Process the CV to extract text and generate embedding
        resume_text, embedding, raw_text = await cv_processing_service.process_cv(file_data, file_name)

        candidate_cv = CandidateCV(
            candidate_id=candidate_id,
            file_url=file_url,
            resume_text=resume_text,
            raw_text=raw_text,
            embedding=embedding
        )
        db.add(candidate_cv)
        await db.flush()
        await db.refresh(candidate_cv)
        return candidate_cv
    
candidate_cv_service = CandidateCVService()
