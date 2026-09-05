from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    get_current_active_superuser,
    get_db,
    get_pagination,
)
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.user import UserRead, UserUpdateAdmin
from app.services import (
    count_users,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    normalize_email,
    update_user,
)

# Every route in this module requires a superuser.
router = APIRouter(dependencies=[Depends(get_current_active_superuser)])


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Loads a user by id or raises a 404."""
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


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
    current_user: User = Depends(get_current_active_superuser),
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

    # Guard against an admin locking themselves out of the admin area.
    if user.id == current_user.id:
        if user_in.is_superuser is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot remove your own superuser privileges.",
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
    current_user: User = Depends(get_current_active_superuser),
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
