from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    """Schema for authentication responses containing JWT access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload carrying a refresh token."""

    refresh_token: str


class TokenPayload(BaseModel):
    """Schema for validating JWT payload contents."""

    sub: Optional[str] = None
    exp: Optional[int] = None
    type: Optional[str] = None
    jti: Optional[str] = None
