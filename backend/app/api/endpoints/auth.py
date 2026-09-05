from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.redis import is_token_revoked, revoke_token
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    RESET_TOKEN_TYPE,
    VERIFICATION_TOKEN_TYPE,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
    parse_uuid,
    verify_password,
)
from app.models.user import User
from app.schemas.common import Message
from app.schemas.token import RefreshRequest, Token, TokenPayload
from app.schemas.user import (
    EmailRequest,
    PasswordChange,
    PasswordResetConfirm,
    TokenRequest,
    UserCreate,
    UserRead,
)
from app.services import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    set_password,
    verify_user_email,
)
from app.tasks.email_tasks import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

router = APIRouter()

# Returned by every "did you forget your password / resend my link" route so the
# response never reveals whether an address is registered.
GENERIC_EMAIL_RESPONSE = Message(
    message="If an account exists for that address, an email is on its way."
)


def _issue_tokens(user: User) -> dict:
    """Builds a fresh access + refresh token pair for a user."""
    return {
        "access_token": create_access_token(subject=str(user.id)),
        "refresh_token": create_refresh_token(subject=str(user.id)),
        "token_type": "bearer",
    }


def _remaining_seconds(exp: Optional[int]) -> int:
    """Seconds until a token's exp claim, floored at zero."""
    if not exp:
        return 0
    delta = exp - int(datetime.now(timezone.utc).timestamp())
    return max(delta, 0)


async def _load_user_from_email_token(
    db: AsyncSession, token: str, expected_type: str
) -> User:
    """Decodes a single use email token and returns the user it belongs to."""
    payload_dict = decode_token(token)
    if not payload_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    try:
        token_data = TokenPayload(**payload_dict)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token structure",
        )

    if token_data.type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token type",
        )

    user_uuid = parse_uuid(token_data.sub)
    if user_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    user = await get_user_by_id(db, user_id=user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)) -> Any:
    """Registers a new user and triggers email verification."""
    if await get_user_by_email(db, email=user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists in the system.",
        )

    new_user = await create_user(db, obj_in=user_in)

    send_verification_email.delay(
        email=new_user.email,
        token=create_verification_token(new_user.id),
        full_name=new_user.full_name or "",
    )

    return new_user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """OAuth2 compatible token login, retrieve access and refresh tokens."""
    user = await get_user_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return _issue_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Any:
    """Exchanges a refresh token for a new token pair, rotating the refresh token."""
    payload_dict = decode_token(body.refresh_token)
    if not payload_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    try:
        token_data = TokenPayload(**payload_dict)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    if token_data.type != REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type, refresh token required",
        )

    if await is_token_revoked(redis, token_data.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    user_uuid = parse_uuid(token_data.sub)
    user = await get_user_by_id(db, user_id=user_uuid) if user_uuid else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Rotation: the presented token cannot be used again.
    if token_data.jti:
        await revoke_token(redis, token_data.jti, _remaining_seconds(token_data.exp))

    return _issue_tokens(user)


@router.post("/logout", response_model=Message)
async def logout(
    body: RefreshRequest,
    redis: Redis = Depends(get_redis),
) -> Any:
    """Revokes a refresh token so it can no longer be exchanged.

    Deliberately does not require an access token: logging out must work even
    once the short lived access token has already expired.
    """
    payload_dict = decode_token(body.refresh_token)
    if payload_dict:
        token_data = TokenPayload(**payload_dict)
        if token_data.type == REFRESH_TOKEN_TYPE and token_data.jti:
            await revoke_token(
                redis, token_data.jti, _remaining_seconds(token_data.exp)
            )

    # Always reports success: an unusable token is an acceptable logout too.
    return Message(message="Logged out successfully.")


@router.post("/verify-email", response_model=Message)
async def verify_email(
    body: TokenRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """Confirms a user's email address using the token from their verification email."""
    user = await _load_user_from_email_token(db, body.token, VERIFICATION_TOKEN_TYPE)

    if user.is_verified:
        return Message(message="Email address already verified.")

    await verify_user_email(db, db_obj=user)
    send_welcome_email.delay(email=user.email, full_name=user.full_name or "")

    return Message(message="Email verified successfully. Welcome onboard!")


@router.post("/resend-verification", response_model=Message)
async def resend_verification(
    body: EmailRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """Sends a fresh verification email, without disclosing whether the address exists."""
    user = await get_user_by_email(db, email=body.email)
    if user and not user.is_verified:
        send_verification_email.delay(
            email=user.email,
            token=create_verification_token(user.id),
            full_name=user.full_name or "",
        )
    return GENERIC_EMAIL_RESPONSE


@router.post("/forgot-password", response_model=Message)
async def forgot_password(
    body: EmailRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """Starts a password reset, without disclosing whether the address exists."""
    user = await get_user_by_email(db, email=body.email)
    if user and user.is_active:
        send_password_reset_email.delay(
            email=user.email,
            token=create_password_reset_token(user.id),
            full_name=user.full_name or "",
        )
    return GENERIC_EMAIL_RESPONSE


@router.post("/reset-password", response_model=Message)
async def reset_password(
    body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)
) -> Any:
    """Completes a password reset using the token from the reset email."""
    user = await _load_user_from_email_token(db, body.token, RESET_TOKEN_TYPE)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    await set_password(db, db_obj=user, new_password=body.new_password)
    return Message(message="Password updated. You can now sign in.")


@router.post("/change-password", response_model=Message)
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Changes the password of the authenticated user after re-checking the current one."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    await set_password(db, db_obj=current_user, new_password=body.new_password)
    return Message(message="Password changed successfully.")
