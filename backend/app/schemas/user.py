from datetime import datetime
from typing import Annotated, Optional
import uuid
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


def _validate_password_strength(value: str) -> str:
    """Requires passwords to mix letters and digits. Length is enforced by Field."""
    if not any(char.isalpha() for char in value):
        raise ValueError("Password must contain at least one letter")
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one digit")
    return value


# Reused by every schema that accepts a new password so the rules stay in one place.
Password = Annotated[
    str,
    Field(min_length=8, max_length=128),
    AfterValidator(_validate_password_strength),
]


class UserBase(BaseModel):
    """Base fields shared across User schemas."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False


class UserCreate(BaseModel):
    """Schema for user registration / signup."""

    email: EmailStr
    password: Password
    full_name: Optional[str] = Field(default=None, max_length=255)


class UserUpdateMe(BaseModel):
    """Fields the owner of an account is allowed to change about themselves.

    Deliberately excludes is_active / is_superuser / is_verified: exposing those
    here would let any authenticated user promote themselves to superuser.
    Password changes go through /auth/change-password instead.
    """

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=255)


class UserUpdateAdmin(BaseModel):
    """Fields a superuser may change on any account. Admin routes only."""

    email: Optional[EmailStr] = None
    password: Optional[Password] = None
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_verified: Optional[bool] = None


class UserRead(UserBase):
    """Schema returned when reading user details from the database."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class EmailRequest(BaseModel):
    """Payload carrying only an email address (resend verification, forgot password)."""

    email: EmailStr


class TokenRequest(BaseModel):
    """Payload carrying a single use token delivered by email."""

    token: str


class PasswordChange(BaseModel):
    """Payload for an authenticated password change."""

    current_password: str
    new_password: Password


class PasswordResetConfirm(BaseModel):
    """Payload completing a forgotten password reset."""

    token: str
    new_password: Password
