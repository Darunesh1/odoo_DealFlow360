from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import create_verification_token
from app.models.user import User
from app.schemas.common import Message
from app.schemas.user import UserRead, UserUpdateMe
from app.services import (
    delete_user,
    get_user_by_email,
    normalize_email,
    set_verification_status,
    update_user,
)
from app.tasks.email_tasks import send_verification_email

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_user_me(current_user: User = Depends(get_current_user)) -> Any:
    """Retrieves profile details of the currently authenticated user."""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_user_me(
    user_in: UserUpdateMe,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Updates the authenticated user's own profile.

    UserUpdateMe intentionally cannot carry is_superuser / is_active / is_verified,
    so this route cannot be used to escalate privileges.
    """
    email_changed = False
    if user_in.email:
        new_email = normalize_email(user_in.email)
        existing_user = await get_user_by_email(db, email=new_email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )
        email_changed = new_email != current_user.email

    updated = await update_user(db, db_obj=current_user, obj_in=user_in)

    if email_changed:
        # A new address is unproven, so the account drops back to unverified.
        updated = await set_verification_status(db, db_obj=updated, is_verified=False)
        send_verification_email.delay(
            email=updated.email,
            token=create_verification_token(updated.id),
            full_name=updated.full_name or "",
        )

    return updated


@router.delete("/me", response_model=Message)
async def delete_user_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Permanently deletes the authenticated user's own account."""
    if current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superusers cannot delete their own account.",
        )

    await delete_user(db, db_obj=current_user)
    return Message(message="Your account has been deleted.")
