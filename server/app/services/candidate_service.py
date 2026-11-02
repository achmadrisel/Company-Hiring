from sqlalchemy.ext.asyncio import AsyncSession
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateCreate
from app.services.s3_service import s3_service
import uuid

class CandidateService:
    async def create_candidate(self, db: AsyncSession, candidate_data: CandidateCreate, file_data: bytes, file_name: str, content_type: str | None) -> Candidate:
        """Create a new candidate."""
        file_ext = file_name.split('.')[-1] if '.' in file_name else 'jpg'
        new_file_name = f"candidates/{uuid.uuid4().hex}.{file_ext}"
        image_url = s3_service.upload_file(file_data, new_file_name, content_type)
        if not image_url:
            raise ValueError("Failed to upload file")

        candidate = Candidate(
            profile_url=image_url,
            full_name=candidate_data.full_name,
            email=candidate_data.email,
            phone_number=candidate_data.phone_number,
            date_of_birth=candidate_data.date_of_birth,
            last_education=candidate_data.last_education.value,
            years_of_experience=candidate_data.years_of_experience.value
        )
        db.add(candidate)
        await db.flush()
        await db.refresh(candidate)
        return candidate
    
candidate_service = CandidateService()
