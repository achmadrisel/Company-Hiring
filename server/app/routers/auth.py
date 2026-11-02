from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta, datetime

from app.core.database import get_db
from app.models import User, UserRole
from app.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthUtils
from app.core.config import get_settings
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register the first admin account",
)
async def register_first_admin(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register the first admin account.
    This endpoint only works if no users exist in the database yet.
    """
    settings = get_settings()
    auth_utils = AuthUtils(settings)

    # Check if any users exist
    result = await db.execute(select(User).limit(1))
    user_exists = result.scalar_one_or_none()

    if user_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin already registered. Use the /users endpoint to create new users.",
        )

    # Check if username is taken
    existing_user = await db.execute(
        select(User).where(User.username == data.username)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    # Create admin user
    hashed_password = auth_utils.get_password_hash(data.password)
    new_user = User(
        username=data.username,
        password=hashed_password,
        full_name=data.full_name,
        role=UserRole.ADMIN,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=TokenResponse, summary="Login and get JWT token")
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return a JWT token."""
    settings = get_settings()
    auth_utils = AuthUtils(settings)

    # Find user by username
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if user is None or not auth_utils.verify_password(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create token
    access_token = auth_utils.create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    return TokenResponse(access_token=access_token)


@router.post("/verify-token")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify the current token is valid and return user info."""
    return current_user
