from typing import Iterable, Optional, Sequence
import uuid
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, unusable_password
from app.models.user import Role, User, UserRole


def normalize_email(email: str) -> str:
    """Normalizes an email address for storage and lookup."""
    return email.lower().strip()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Retrieves a user from the database by email address."""
    query = select(User).where(User.email == normalize_email(email))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Retrieves a user from the database by their unique UUID."""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


def apply_roles(db_obj: User, roles: Iterable[Role]) -> None:
    """Reconciles a user's role grants in place. The caller commits.

    Deliberately not `db_obj.role_links = [...]`: replacing the collection
    wholesale orphans every existing row and inserts fresh ones with identical
    composite keys, and the unit of work does not reliably order the deletes
    before the inserts. That produces an intermittent unique violation on any
    role the user already held. Reconciling leaves untouched rows alone.
    """
    wanted = {Role(role) for role in roles}
    current = {link.role for link in db_obj.role_links}

    for link in list(db_obj.role_links):
        if link.role not in wanted:
            db_obj.role_links.remove(link)  # delete-orphan issues the DELETE
    for role in sorted(wanted - current, key=lambda r: r.value):
        db_obj.role_links.append(UserRole(role=role))


async def create_invited_user(
    db: AsyncSession,
    *,
    email: str,
    full_name: Optional[str],
    roles: Iterable[Role],
    customer_id: Optional[uuid.UUID] = None,
) -> User:
    """Creates an account that cannot be signed into until its invite is accepted."""
    db_user = User(
        email=normalize_email(email),
        hashed_password=unusable_password(),
        full_name=full_name,
        customer_id=customer_id,
        is_active=True,
        is_verified=False,
        role_links=[UserRole(role=Role(r)) for r in dict.fromkeys(roles)],
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def register_customer(
    db: AsyncSession, *, full_name: str, email: str, password: str, company_name=None
) -> User:
    """Creates a portal login and the customer record behind it.

    Quotations belong to a *customer*, not to a login, so a self-registered
    user needs both: the company (or the individual, under their own name) and
    the account attached to it. The tier is the lowest ceiling on offer -
    nobody talks their way into Gold pricing by filling in a form; a rep or
    admin promotes them later.

    Roles come from here, never from the request. The schema has no `roles`
    field to carry one.
    """
    from app.models.customer import Customer
    from app.services.catalog_service import get_lowest_active_tier

    address = normalize_email(email)

    tier = await get_lowest_active_tier(db)
    if tier is None:
        raise ValueError("No customer tier is configured; an admin must add one first")

    customer = Customer(
        name=(company_name or full_name).strip(),
        tier_id=tier.id,
        contact_email=address,
        is_active=True,
    )
    db.add(customer)
    await db.flush()

    db_user = User(
        email=address,
        hashed_password=hash_password(password),
        full_name=full_name.strip(),
        customer_id=customer.id,
        is_active=True,
        # Unverified until they follow the emailed link, exactly like an
        # address change on an existing account.
        is_verified=False,
        role_links=[UserRole(role=Role.CUSTOMER)],
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def accept_invite(db: AsyncSession, db_obj: User, new_password: str) -> User:
    """Sets the first password on an invited account and marks it verified."""
    db_obj.hashed_password = hash_password(new_password)
    db_obj.is_verified = True
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_user(db: AsyncSession, db_obj: User, obj_in: BaseModel) -> User:
    """Applies the set fields of an update schema to a user record.

    The caller decides which schema to pass, and therefore which fields may be
    written: UserUpdateMe for self service, UserUpdateAdmin for admin routes.
    """
    update_data = obj_in.model_dump(exclude_unset=True)

    password = update_data.pop("password", None)
    if password:
        db_obj.hashed_password = hash_password(password)

    email = update_data.pop("email", None)
    if email:
        db_obj.email = normalize_email(email)

    # roles is a read-only property, so it must never reach the setattr loop.
    roles = update_data.pop("roles", None)
    if roles is not None:
        apply_roles(db_obj, roles)

    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def set_password(db: AsyncSession, db_obj: User, new_password: str) -> User:
    """Replaces a user's password hash."""
    db_obj.hashed_password = hash_password(new_password)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def set_verification_status(
    db: AsyncSession, db_obj: User, is_verified: bool
) -> User:
    """Sets a user's email verification flag."""
    db_obj.is_verified = is_verified
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def verify_user_email(db: AsyncSession, db_obj: User) -> User:
    """Marks a user as verified in the database."""
    return await set_verification_status(db, db_obj, True)


async def delete_user(db: AsyncSession, db_obj: User) -> None:
    """Permanently removes a user record."""
    await db.delete(db_obj)
    await db.commit()


def _list_filters(search: Optional[str], is_active: Optional[bool]) -> list:
    """Builds the shared WHERE clauses used by list_users and count_users."""
    filters = []
    if search:
        pattern = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(User.full_name, "")).like(pattern),
            )
        )
    if is_active is not None:
        filters.append(User.is_active == is_active)
    return filters


async def list_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Sequence[User]:
    """Returns a page of users, newest first, optionally filtered."""
    query = (
        select(User)
        .where(*_list_filters(search, is_active))
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def count_users(
    db: AsyncSession,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> int:
    """Counts users matching the same filters as list_users."""
    query = select(func.count()).select_from(User).where(*_list_filters(search, is_active))
    result = await db.execute(query)
    return result.scalar_one()
