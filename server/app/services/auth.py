import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt

from app.core.config import Settings


class AuthUtils:
    """Authentication utilities for password hashing and JWT tokens."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password."""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), 
            hashed_password.encode("utf-8")
        )

    def get_password_hash(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.settings.access_token_expire_minutes
            )
        to_encode.update({"exp": expire})
        return jwt.encode(
            to_encode, self.settings.secret_key, algorithm=self.settings.algorithm
        )

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token, self.settings.secret_key, algorithms=[self.settings.algorithm]
            )
            return payload
        except JWTError:
            return None
