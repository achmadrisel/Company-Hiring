"""Seed script to create the initial admin user.

Usage:
    python -m app.seed_admin
"""

import asyncio
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models import User, UserRole
from app.services.auth import AuthUtils
from app.core.config import get_settings


async def seed_admin():
    settings = get_settings()
    auth_utils = AuthUtils(settings)

    async with async_session_factory() as db:
        # Check if admin already exists
        result = await db.execute(
            select(User).where(User.username == "admin")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin user already exists, skipping.")
            return

        # Create admin user
        hashed_pw = auth_utils.get_password_hash("admin123")
        admin = User(
            username="admin",
            password=hashed_pw,
            full_name="Administrator",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        print(f"Admin user created: {admin.username} (id={admin.id})")


if __name__ == "__main__":
    asyncio.run(seed_admin())
