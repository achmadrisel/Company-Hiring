import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import User, UserRole
from app.services.auth import AuthUtils
from app.core.config import get_settings


async def create_admin_user(db_session):
    """Helper to create an admin user and return their token."""
    settings = get_settings()
    auth_utils = AuthUtils(settings)
    
    hashed_password = auth_utils.get_password_hash("adminpassword123")
    admin = User(
        username="testadmin",
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
    
    return admin, token


async def create_recruiter_user(db_session):
    """Helper to create a recruiter user and return their token."""
    settings = get_settings()
    auth_utils = AuthUtils(settings)
    
    hashed_password = auth_utils.get_password_hash("recruiterpassword123")
    recruiter = User(
        username="testrecruiter",
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
    
    return recruiter, token


class TestUserEndpoints:
    """Test user management endpoints."""

    @pytest.mark.asyncio
    async def test_create_recruiter_as_admin(self, app, db_session):
        """Test that admin can create a recruiter account."""
        admin, admin_token = await create_admin_user(db_session)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/users/",
                json={
                    "username": "newrecruiter",
                    "password": "recruiterpass123",
                    "full_name": "New Recruiter",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["username"] == "newrecruiter"
            assert data["full_name"] == "New Recruiter"
            assert data["role"] == "recruiter"
            assert "password" not in data
            
            # Verify in database
            result = await db_session.execute(
                select(User).where(User.username == "newrecruiter")
            )
            user = result.scalar_one_or_none()
            assert user is not None

    @pytest.mark.asyncio
    async def test_create_user_as_recruiter_forbidden(self, app, db_session):
        """Test that recruiters cannot create users."""
        recruiter, recruiter_token = await create_recruiter_user(db_session)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/users/",
                json={
                    "username": "anotheruser",
                    "password": "password123",
                    "full_name": "Another User",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {recruiter_token}"},
            )
            
            assert response.status_code == 403
            assert "Admin access required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_admin_as_admin_forbidden(self, app, db_session):
        """Test that admin cannot create another admin through the endpoint."""
        admin, admin_token = await create_admin_user(db_session)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/users/",
                json={
                    "username": "newadmin",
                    "password": "adminpass123",
                    "full_name": "New Admin",
                    "role": "admin",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 403
            assert "can only create recruiter" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_duplicate_user(self, app, db_session):
        """Test creating a user with existing username fails."""
        admin, admin_token = await create_admin_user(db_session)
        
        # Create first recruiter
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "Recruiter One",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            # Try to create duplicate
            response = await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "Recruiter One Duplicate",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 409
            assert "Username already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, app, db_session):
        """Test getting a user by ID."""
        admin, admin_token = await create_admin_user(db_session)
        
        # Create a recruiter
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "Recruiter One",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            user_id = create_response.json()["id"]
            
            # Get the user
            response = await client.get(
                f"/api/users/{user_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "recruiter1"
            assert data["full_name"] == "Recruiter One"

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, app, db_session):
        """Test getting a non-existent user returns 404."""
        admin, admin_token = await create_admin_user(db_session)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/users/00000000-0000-0000-0000-000000000000",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user(self, app, db_session):
        """Test updating a user."""
        admin, admin_token = await create_admin_user(db_session)
        
        # Create a recruiter
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "Original Name",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            user_id = create_response.json()["id"]
            
            # Update the user
            response = await client.put(
                f"/api/users/{user_id}",
                json={"full_name": "Updated Name"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["full_name"] == "Updated Name"
            assert data["username"] == "recruiter1"

    @pytest.mark.asyncio
    async def test_delete_user(self, app, db_session):
        """Test deleting a user."""
        admin, admin_token = await create_admin_user(db_session)
        
        # Create a recruiter
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "To Be Deleted",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            user_id = create_response.json()["id"]
            
            # Delete the user
            response = await client.delete(
                f"/api/users/{user_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 204
            
            # Verify user is deleted
            result = await db_session.execute(
                select(User).where(User.id == user_id)
            )
            deleted_user = result.scalar_one_or_none()
            assert deleted_user is None

    @pytest.mark.asyncio
    async def test_cannot_delete_self(self, app, db_session):
        """Test that admin cannot delete their own account."""
        admin, admin_token = await create_admin_user(db_session)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/users/{admin.id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 400
            assert "Cannot delete your own account" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_users(self, app, db_session):
        """Test listing all users."""
        admin, admin_token = await create_admin_user(db_session)
        
        # Create some recruiters
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/users/",
                json={
                    "username": "recruiter1",
                    "password": "password123",
                    "full_name": "Recruiter One",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            await client.post(
                "/api/users/",
                json={
                    "username": "recruiter2",
                    "password": "password123",
                    "full_name": "Recruiter Two",
                    "role": "recruiter",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            # List users
            response = await client.get(
                "/api/users/",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 3  # admin + 2 recruiters
            assert len(data["users"]) == 3
            
            # Verify response format
            for user in data["users"]:
                assert "id" in user
                assert "username" in user
                assert "full_name" in user
                assert "role" in user
                assert "created_at" in user
                assert "updated_at" in user
                assert "password" not in user
