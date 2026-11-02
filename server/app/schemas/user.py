from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional
import uuid

from app.models import UserRole


# --- Request Schemas ---


class UserCreate(BaseModel):
    """Schema for creating a new user (admin only)."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole = UserRole.RECRUITER


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    role: Optional[UserRole] = None


class LoginRequest(BaseModel):
    """Schema for login request."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Schema for initial admin registration."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=100)


# --- Response Schemas ---


class TokenResponse(BaseModel):
    """Schema for token response."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Schema for user response (excludes password)."""

    id: uuid.UUID
    username: str
    full_name: str
    role: UserRole
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Schema for a list of users with count."""

    users: list[UserResponse]
    total: int
