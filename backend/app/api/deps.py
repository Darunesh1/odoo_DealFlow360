from dataclasses import dataclass
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import ACCESS_TOKEN_TYPE, decode_token, parse_uuid
from app.models.user import User
from app.schemas.token import TokenPayload
from app.services import get_user_by_id

# OAuth2 scheme config (points at the absolute login route path)
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    """FastAPI dependency to retrieve, validate, and authorize the current user based on the JWT token."""
    payload_dict = decode_token(token)
    if not payload_dict:
        raise CREDENTIALS_ERROR

    try:
        token_data = TokenPayload(**payload_dict)
    except Exception:
        raise CREDENTIALS_ERROR

    if token_data.type != ACCESS_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type, access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_uuid = parse_uuid(token_data.sub)
    if user_uuid is None:
        raise CREDENTIALS_ERROR

    user = await get_user_by_id(db, user_id=user_uuid)
    if not user:
        # The token is well formed but the account behind it is gone.
        raise CREDENTIALS_ERROR

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency requiring the current user to have confirmed their email address."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
        )
    return current_user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency to verify that the logged-in user is a superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges",
        )
    return current_user


@dataclass
class Pagination:
    """Resolved pagination window shared by every list endpoint."""

    page: int
    size: int

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size

    def pages(self, total: int) -> int:
        """Total number of pages for a given result count."""
        return (total + self.size - 1) // self.size if self.size else 0


def get_pagination(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> Pagination:
    """FastAPI dependency providing validated pagination parameters."""
    return Pagination(page=page, size=size)


__all__ = [
    "Pagination",
    "get_current_active_superuser",
    "get_current_user",
    "get_current_verified_user",
    "get_db",
    "get_pagination",
    "get_redis",
]
