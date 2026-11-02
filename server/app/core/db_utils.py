import sys
from pathlib import Path

# Add the server directory to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from app.core.database import engine  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402
import asyncio


async def create_database():
    """Create the database if it doesn't exist (PostgreSQL)."""
    from sqlalchemy import text
    import asyncpg

    settings = get_settings()

    # Connect to the default 'postgres' database to create our target database
    admin_url = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/postgres"

    try:
        async_conn = await asyncpg.connect(
            user=settings.postgres_user,
            password=settings.postgres_password,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database="postgres",
        )

        # Check if database exists
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", settings.postgres_db
        )

        if not exists:
            await admin_conn.execute(f'CREATE DATABASE "{settings.postgres_db}"')
            print(f"Database '{settings.postgres_db}' created successfully.")
        else:
            print(f"Database '{settings.postgres_db}' already exists.")

        await admin_conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")
        raise


async def create_tables():
    """Create all tables defined in the models."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully.")


async def drop_tables():
    """Drop all tables (use with caution!)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("Tables dropped successfully.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database management script")
    parser.add_argument(
        "command", choices=["create-db", "create-tables", "drop-tables"],
        help="Command to execute"
    )
    args = parser.parse_args()

    if args.command == "create-db":
        asyncio.run(create_database())
    elif args.command == "create-tables":
        asyncio.run(create_tables())
    elif args.command == "drop-tables":
        asyncio.run(drop_tables())
