from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    get_db,
    get_pagination,
    require_admin,
)
from app.core.security import create_invite_token, is_password_usable
from app.models.user import Role, User
from app.schemas.common import Message, Page
from app.schemas.user import UserInvite, UserRead, UserUpdateAdmin
from app.services import (
    count_users,
    create_invited_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    normalize_email,
    update_user,
)
from app.tasks.email_tasks import send_invite_email

# Every route in this module requires the admin role.
router = APIRouter(dependencies=[Depends(require_admin)])


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Loads a user by id or raises a 404."""
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def invite_user(user_in: UserInvite, db: AsyncSession = Depends(get_db)) -> Any:
    """Creates an account with no usable password and emails its owner a setup link.

    This replaces public signup: an administrator decides who exists and what
    roles they hold, and the invitee chooses their own password.
    """
    if await get_user_by_email(db, email=user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    new_user = await create_invited_user(
        db,
        email=user_in.email,
        full_name=user_in.full_name,
        roles=user_in.roles,
    )
    send_invite_email.delay(
        email=new_user.email,
        token=create_invite_token(new_user.id),
        full_name=new_user.full_name or "",
    )
    return new_user


@router.post("/users/{user_id}/resend-invite", response_model=Message)
async def resend_invite(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    """Issues a fresh invitation link to someone who has not accepted theirs.

    Unlike the public email routes this does not hide whether the account
    exists: the caller is an administrator who can already list every account.
    """
    user = await _get_user_or_404(db, user_id)

    if is_password_usable(user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user has already accepted their invitation.",
        )

    send_invite_email.delay(
        email=user.email,
        token=create_invite_token(user.id),
        full_name=user.full_name or "",
    )
    return Message(message="Invitation resent.")


@router.get("/users", response_model=Page[UserRead])
async def read_users(
    db: AsyncSession = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    search: Optional[str] = Query(default=None, description="Match against email or full name"),
    is_active: Optional[bool] = Query(default=None),
) -> Any:
    """Lists users with pagination, free text search, and an active/inactive filter."""
    total = await count_users(db, search=search, is_active=is_active)
    items = await list_users(
        db,
        skip=pagination.skip,
        limit=pagination.limit,
        search=search,
        is_active=is_active,
    )
    return Page[UserRead](
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(total),
    )


@router.get("/users/{user_id}", response_model=UserRead)
async def read_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    """Retrieves a single user by id."""
    return await _get_user_or_404(db, user_id)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_by_id(
    user_id: uuid.UUID,
    user_in: UserUpdateAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """Updates any field of any user account."""
    user = await _get_user_or_404(db, user_id)

    if user_in.email:
        existing_user = await get_user_by_email(db, email=normalize_email(user_in.email))
        if existing_user and existing_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )

    # Guard against an admin locking themselves out of the admin area. roles is
    # a full replacement, so omitting ADMIN from the list is removing it.
    if user.id == current_user.id:
        if user_in.roles is not None and Role.ADMIN not in user_in.roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot remove your own administrator role.",
            )
        if user_in.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account.",
            )

    return await update_user(db, db_obj=user, obj_in=user_in)


@router.delete("/users/{user_id}", response_model=Message)
async def delete_user_by_id(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """Permanently deletes a user account."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account from the admin area.",
        )

    user = await _get_user_or_404(db, user_id)
    await delete_user(db, db_obj=user)
    return Message(message="User deleted successfully.")
