from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from uuid import UUID
import enum

class LastEducationEnum(str, enum.Enum):
    high_school = "high_school"
    associate_degree = "associate_degree"
    bachelor_degree = "bachelor_degree"
    master_degree = "master_degree"
    doctorate_degree = "doctorate_degree"

class YearsOfExperienceEnum(str, enum.Enum):
    no_experience = "no_experience"
    less_than_1_year = "less_than_1_year"
    one_to_three_years = "one_to_three_years"
    three_to_five_years = "three_to_five_years"
    more_than_five_years = "more_than_five_years"

class CandidateBase(BaseModel):

    full_name: str
    email: str
    phone_number: str
    date_of_birth: str
    last_education: LastEducationEnum
    years_of_experience: YearsOfExperienceEnum

class CandidateCreate(CandidateBase):
    pass

class CandidateUpdate(BaseModel):
    profile_url: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    last_education: Optional[LastEducationEnum] = None
    years_of_experience: Optional[YearsOfExperienceEnum] = None

class CandidateResponse(BaseModel):
    id: UUID
    profile_url: str

    full_name: str
    email: str
    phone_number: str
    date_of_birth: str
    last_education: LastEducationEnum
    years_of_experience: YearsOfExperienceEnum
    created_at: datetime

    class Config:
        from_attributes = True