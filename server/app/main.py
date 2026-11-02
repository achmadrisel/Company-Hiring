from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.config import get_settings
from app.core.database import engine
from app.models import Base
from app.routers import auth, users, job, job_application

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    settings = get_settings()
    # Only auto-create tables in non-production environments. In production, schema
    # changes must be applied via `alembic upgrade head` so we never run a
    # mutation against the production database from app startup.
    if settings.environment == "production":
        logger.warning(
            "ENVIRONMENT=production: skipping Base.metadata.create_all. "
            "Apply schema changes via `alembic upgrade head`."
        )
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="User Management API",
        description="FastAPI based user management with role-based access control",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(job.router)
    app.include_router(job_application.router)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


app = create_app()
