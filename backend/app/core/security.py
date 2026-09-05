from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import uuid
import bcrypt
import jwt

from app.core.config import settings

# Token "type" claim values. Every token records what it may be used for so a
# refresh token can never be replayed as an access token, and vice versa.
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
VERIFICATION_TOKEN_TYPE = "verification"
RESET_TOKEN_TYPE = "reset"


def hash_password(password: str) -> str:
    """Generates a secure bcrypt hash of a password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def _encode(claims: dict) -> str:
    """Signs a claims dictionary with the configured secret and algorithm."""
    return jwt.encode(
        claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Generates an access JWT token for a given user identifier (subject)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return _encode({"exp": expire, "sub": str(subject), "type": ACCESS_TOKEN_TYPE})


def create_refresh_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Generates a long-lived refresh JWT token carrying a unique id (jti) so it can be revoked."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    return _encode(
        {
            "exp": expire,
            "sub": str(subject),
            "type": REFRESH_TOKEN_TYPE,
            "jti": str(uuid.uuid4()),
        }
    )


def create_email_token(
    subject: Union[str, Any], token_type: str, expires_delta: timedelta
) -> str:
    """Generates a short-lived single purpose token delivered by email (verification, password reset)."""
    expire = datetime.now(timezone.utc) + expires_delta
    return _encode({"exp": expire, "sub": str(subject), "type": token_type})


def create_verification_token(subject: Union[str, Any]) -> str:
    """Generates an email verification token."""
    return create_email_token(
        subject,
        VERIFICATION_TOKEN_TYPE,
        timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
    )


def create_password_reset_token(subject: Union[str, Any]) -> str:
    """Generates a password reset token."""
    return create_email_token(
        subject,
        RESET_TOKEN_TYPE,
        timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
    )


def decode_token(token: str) -> Optional[dict]:
    """Decodes a JWT token using the configured secret and algorithm."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None


def parse_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    """Safely converts a token subject into a UUID, returning None when malformed."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return None
