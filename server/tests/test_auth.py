import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models import User, UserRole


class TestAuth:
    """Test authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_first_admin_success(self, app, db_session):
        """Test successful first admin registration."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "username": "firstadmin",
                    "password": "securepassword123",
                    "full_name": "First Admin",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["username"] == "firstadmin"
            assert data["full_name"] == "First Admin"
            assert data["role"] == "admin"
            assert "password" not in data

            # Verify in database
            result = await db_session.execute(
                db_session.query(User).filter_by(username="firstadmin")
            )
            user = result.scalar_one_or_none()
            assert user is not None
            assert user.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_register_first_admin_duplicate(self, app, db_session):
        """Test that duplicate admin registration fails."""
        # First registration should succeed
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "username": "admin1",
                    "password": "password123",
                    "full_name": "Admin One",
                },
            )

            # Second registration should fail
            response = await client.post(
                "/api/auth/register",
                json={
                    "username": "admin2",
                    "password": "password123",
                    "full_name": "Admin Two",
                },
            )

            assert response.status_code == 400
            assert "Admin already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_success(self, app, db_session, auth_utils):
        """Test successful login."""
        # Create a user
        hashed_password = auth_utils.get_password_hash("testpassword123")
        user = User(
            username="testuser",
            password=hashed_password,
            full_name="Test User",
            role=UserRole.ADMIN,
        )
        db_session.add(user)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpassword123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, app, db_session):
        """Test login with invalid credentials."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "wronguser", "password": "wrongpassword"},
            )

            assert response.status_code == 401
            assert "Incorrect username or password" in response.json()["detail"]
