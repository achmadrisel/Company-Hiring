# server

FastAPI user management system with role-based access control (Admin & Recruiter).

## Features
- User CRUD operations
- Role-based access control (admin, recruiter)
- JWT authentication
- PostgreSQL with SQLAlchemy async
- Alembic migrations
- Pytest test suite

## Setup

### Prerequisites
- Python 3.11+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

1. **Install dependencies:**
   ```bash
   cd server
   uv sync --all-extras
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

3. **Create PostgreSQL database:**
   ```bash
   psql -U postgres -c "CREATE DATABASE user_management;"
   ```

4. **Run migrations:**
   ```bash
   uv run alembic upgrade head
   ```

5. **Run the server:**
   ```bash
   uv run uvicorn app.main:app --reload
   ```

## API Endpoints

| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| /api/auth/register | POST | Open | First admin registration |
| /api/auth/login | POST | Open | Login and get JWT token |
| /api/users | GET | Admin | List all users |
| /api/users | POST | Admin | Create new user (recruiter) |
| /api/users/{id} | GET | Admin/Recruiter | Get user by ID |
| /api/users/{id} | PUT | Admin | Update user |
| /api/users/{id} | DELETE | Admin | Delete user |

## Testing

```bash
uv run pytest -v
```

## Project Structure

```
server/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application entry point
│   ├── config.py         # Application settings
│   ├── database.py       # Database connection
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── auth.py           # JWT authentication utilities
│   ├── dependencies.py   # FastAPI dependencies
│   └── routers/
│       ├── __init__.py
│       ├── auth.py       # Auth endpoints
│       └── users.py      # User endpoints
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   ├── README
│   └── versions/
│       └── (migrations)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   └── test_users.py
├── pyproject.toml
└── .env.example
```
