"""Customers, their tiers, and sales teams."""

from typing import Optional
import uuid
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import PERCENT, TimestampMixin

class SalesTeam(Base, TimestampMixin):
    """A group of reps. Reporting filters by team, and the login screen offers
    a team selector for multi-team setups."""

    __tablename__ = "sales_teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CustomerTier(Base, TimestampMixin):
    """Bronze / Silver / Gold, each with the discount ceiling an admin can edit.

    A table rather than an enum for two reasons: the ceiling is configuration
    the spec insists must not be hardcoded, and with no migrations an enum can
    never gain a "Platinum" without dropping the database. A row can.
    """

    __tablename__ = "customer_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    # The name is the natural key: there is no code, and listings order by the
    # ceiling rather than by a hand-maintained sort column.
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    max_discount_percent: Mapped[float] = mapped_column(PERCENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "max_discount_percent >= 0 AND max_discount_percent <= 100",
            name="ck_customer_tier_percent_range",
        ),
    )


class Customer(Base, TimestampMixin):
    """A buying company. Quotations belong here rather than to a portal login,
    so two people at Acme can both see Acme's deals."""

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # RESTRICT: a tier that is in use must not be deletable out from under the
    # quotations whose ceilings were derived from it.
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_tiers.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    billing_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tier: Mapped["CustomerTier"] = relationship(lazy="selectin")
