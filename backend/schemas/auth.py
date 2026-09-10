"""Authentication Schemas for MDT"""
from pydantic import BaseModel, Field
from typing import Optional


class UserLogin(BaseModel):
    """Payload for user login."""
    username: str = Field(..., min_length=1, max_length=100, description="Username or email")
    password: str = Field(..., min_length=1, description="Account password")


class UserRegistration(BaseModel):
    """Self-service account creation payload. New accounts are viewer-only."""
    username: str = Field(..., min_length=3, max_length=100, description="Unique operator username")
    password: str = Field(..., min_length=8, max_length=128, description="Password for the new account")


class UserOut(BaseModel):
    """Public user identity response."""
    username: str
    role: str = "admin"
    is_active: bool = True


class Token(BaseModel):
    """JWT bearer token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class TokenPayload(BaseModel):
    """Parsed JWT token claims."""
    sub: str  # username
    role: str = "admin"
    exp: int
    iat: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    """Optional payload for refreshing expired/near-expiry token."""
    refresh_token: Optional[str] = None
