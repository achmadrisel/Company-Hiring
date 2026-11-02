import pytest
import pytest_asyncio
from asyncpg.connection import Connection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session_factory, engine
from app.core.config import get_settings
from app.models import User, UserRole
from app.services.auth import AuthUtils
from app.main import create_app


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def verify_schema():
    """Verify the database schema exists. Do NOT destroy any data.

    The target database must already be migrated via `alembic upgrade head` before
    running tests. If the schema is missing, abort with a clear, actionable message
    instead of silently dropping and recreating tables (which would wipe real data).
    """
    settings = get_settings()
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"
        ))
        if result.scalar() is None:
            pytest.exit(
                "Schema not found in the target database. "
                "Run `alembic upgrade head` to apply migrations before running tests. "
                f"Target DATABASE_URL: {settings.database_url}"
            )
    yield


@pytest.fixture
def app():
    """Create a FastAPI test application."""
    return create_app()


@pytest_asyncio.fixture
async def db_session():
    """Provide a transactional database session for each test."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def auth_utils():
    """Provide an AuthUtils instance."""
    settings = get_settings()
    return AuthUtils(settings)


@pytest.fixture(autouse=True)
def test_client(app):
    """Provide a test client."""
    return app


@pytest_asyncio.fixture
async def admin_token(app, db_session, auth_utils):
    """Create an admin user and return their token."""
    hashed_password = auth_utils.get_password_hash("adminpassword123")
    admin = User(
        username="admin_user",
        password=hashed_password,
        full_name="Test Admin",
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = auth_utils.create_access_token({
        "sub": str(admin.id),
        "role": admin.role,
    })

    return token


@pytest_asyncio.fixture
async def recruiter_token(app, db_session, auth_utils):
    """Create a recruiter user and return their token."""
    hashed_password = auth_utils.get_password_hash("recruiterpassword123")
    recruiter = User(
        username="recruiter_user",
        password=hashed_password,
        full_name="Test Recruiter",
        role=UserRole.RECRUITER,
    )
    db_session.add(recruiter)
    await db_session.commit()
    await db_session.refresh(recruiter)

    token = auth_utils.create_access_token({
        "sub": str(recruiter.id),
        "role": recruiter.role,
    })

    return token
