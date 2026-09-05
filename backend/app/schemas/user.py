from datetime import datetime
from typing import Annotated, Optional
import uuid
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


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


def _unique_roles(values: list[Role]) -> list[Role]:
    """Drops repeats while preserving order; a duplicate would break the composite key."""
    return list(dict.fromkeys(values))


# Every role grant goes through here, so a user can never end up with none.
Roles = Annotated[list[Role], Field(min_length=1), AfterValidator(_unique_roles)]


class UserBase(BaseModel):
    """Base fields shared across User schemas."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True
    is_verified: bool = False
    roles: list[Role] = Field(default_factory=list)


class UserInvite(BaseModel):
    """Schema an administrator submits to create an account and invite its owner."""

    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)
    roles: Roles


class InviteAccept(BaseModel):
    """Payload an invitee submits to set their first password."""

    token: str
    new_password: Password


class UserUpdateMe(BaseModel):
    """Fields the owner of an account is allowed to change about themselves.

    Deliberately excludes roles / is_active / is_verified: exposing any of them
    here would let any authenticated user grant themselves the admin role.
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
    is_verified: Optional[bool] = None
    # A full replacement, not a merge: whatever is sent becomes the user's roles.
    roles: Optional[Roles] = None


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
