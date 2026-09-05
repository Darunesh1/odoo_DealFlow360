from datetime import datetime, timezone
import enum
from typing import Optional
import uuid
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(str, enum.Enum):
    """A capability a user holds. A user may hold several at once.

    These are domain concepts rather than admin-configurable data, so they live
    in code. Every downstream module routes on them: approvals go to
    SALES_MANAGER then FINANCE, the portal is restricted to CUSTOMER, and the
    deal health dashboard is for SALES_MANAGER.
    """

    ADMIN = "admin"
    SALES_REP = "sales_rep"
    SALES_MANAGER = "sales_manager"
    FINANCE = "finance"
    CUSTOMER = "customer"


class UserRole(Base):
    """A single role grant.

    The composite primary key makes granting the same role twice impossible at
    the database level, so the service layer never has to de-duplicate.
    """

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # The tests bulk-delete users with a Core statement, which bypasses the
        # ORM cascade entirely, so the cleanup has to happen in the database.
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[Role] = mapped_column(
        # Without values_callable SQLAlchemy stores the member *names*
        # ("SALES_REP"), which silently disagrees with the JSON the API emits.
        SAEnum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        primary_key=True,
    )

    user: Mapped["User"] = relationship(back_populates="role_links")


class User(Base):
    """User database model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # lazy="selectin" is load-bearing. Under asyncpg a lazy load outside an
    # awaitable context raises MissingGreenlet, and roles are read in three
    # places that are not inside an await: the authorization dependency,
    # response serialization after the endpoint returns, and the delete-orphan
    # cascade. Eager-loading at the mapper covers every query at once.
    role_links: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def roles(self) -> list[Role]:
        """The roles this user holds.

        Read-only on purpose: it makes the blind setattr loop in update_user
        fail loudly rather than silently corrupting the grant rows.
        """
        return [link.role for link in self.role_links]

    def has_role(self, *roles: Role) -> bool:
        """True when the user holds at least one of the given roles."""
        return bool(set(roles) & set(self.roles))
