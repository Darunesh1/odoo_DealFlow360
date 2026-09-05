"""Quotations, their lines, and customer negotiation."""

from datetime import date, datetime
import enum
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Computed, Date, DateTime, Enum as SAEnum,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, PERCENT, POINTS, UNIT_PRICE, TimestampMixin
from app.models.catalog import RecurringInterval

if TYPE_CHECKING:
    from app.models.catalog import PriceList, Product, ProductCategory
    from app.models.customer import Customer, CustomerTier
    from app.models.inventory import Warehouse


class QuotationStatus(str, enum.Enum):
    """The pipeline stages shown on the quotations board."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEGOTIATION = "negotiation"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class RiskBand(str, enum.Enum):
    """The blended risk banding shown on the approvals list."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LineSource(str, enum.Enum):
    """How a line got onto the quotation. Carried through to sales history so
    "top upsold product" is answerable."""

    MANUAL = "manual"
    UPSELL = "upsell"
    CROSS_SELL = "cross_sell"


class ChangeRequestStatus(str, enum.Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Quotation(Base, TimestampMixin):
    """A deal. Once CONFIRMED this row is also the sales order - the mockup
    uses one reference (Q-1042) for the quotation, approval and fulfillment
    rows alike, so a separate orders table would invent an entity the spec
    never shows."""

    __tablename__ = "quotations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # SET NULL, not RESTRICT: a rep who owns one quotation must still be
    # deletable, and the snapshot below keeps the pipeline card readable after
    # they are gone.
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        index=True, nullable=True,
    )
    owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sales_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_teams.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[QuotationStatus] = mapped_column(
        SAEnum(QuotationStatus, name="quotation_status",
               values_callable=lambda e: [m.value for m in e]),
        default=QuotationStatus.DRAFT, index=True, nullable=False,
    )

    price_list_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    customer_tier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_tiers.id", ondelete="RESTRICT"), nullable=True
    )
    # Snapshot, so the approval screen's "Customer Tier: Gold / 15%" header
    # stays truthful after an admin edits the ceiling.
    tier_max_discount_percent: Mapped[Optional[float]] = mapped_column(PERCENT, nullable=True)

    # Kept for display and editing. The service folds it into every line's
    # discount_percent, because a header-only discount would otherwise bypass
    # each line's own ceiling - the ceiling check reads line discounts.
    order_discount_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)

    subtotal: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    discount_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    tax_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    margin_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)

    blended_risk_score: Mapped[float] = mapped_column(POINTS, default=0, nullable=False)
    risk_band: Mapped[RiskBand] = mapped_column(
        SAEnum(RiskBand, name="risk_band", values_callable=lambda e: [m.value for m in e]),
        default=RiskBand.NONE, index=True, nullable=False,
    )
    max_line_over_points: Mapped[float] = mapped_column(POINTS, default=0, nullable=False)
    weighted_over_points: Mapped[float] = mapped_column(POINTS, default=0, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    requested_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    promised_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Powers the Deal Health "idle 9 days" tile.
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship(lazy="selectin")
    price_list: Mapped[Optional["PriceList"]] = relationship(lazy="selectin")
    customer_tier: Mapped[Optional["CustomerTier"]] = relationship(lazy="selectin")
    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", lazy="selectin",
        order_by="QuotationLine.position",
    )

    __table_args__ = (
        CheckConstraint(
            "order_discount_percent >= 0 AND order_discount_percent <= 100",
            name="ck_quotation_order_discount_range",
        ),
        Index("ix_quotations_pipeline", "status", "updated_at"),
    )


class QuotationLine(Base, TimestampMixin):
    """One product on a quotation.

    Nearly every column here is a SNAPSHOT taken when the line was added, not a
    live read. An admin raising the Services ceiling from 10% to 20% while this
    quote sits with Finance must not make the "Why This Quote Was Flagged"
    screen re-render as "OK", leaving an approver looking at a flagged quote
    with no visible reason. The workspace's "Reload Data" button is the
    sanctioned re-snapshot, and only for DRAFT quotations.
    """

    __tablename__ = "quotation_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_categories.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    warehouse_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    warehouse_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    warehouse_bin_location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stock_available_at_entry: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # What the price list resolved to, including variant deltas. The rep's
    # discount is measured against THIS, never against list_price_at_entry:
    # a Gold customer's list has already taken 10% off, so measuring against
    # the catalog price would start every line 10 points into its own ceiling
    # and fire approval on every quotation in the demo.
    unit_price: Mapped[float] = mapped_column(UNIT_PRICE, nullable=False)
    list_price_at_entry: Mapped[float] = mapped_column(MONEY, nullable=False)
    unit_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    tax_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)

    # What the rep typed on this line.
    line_discount_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    # line + order-level, materialised. This is the governed number.
    discount_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)

    tier_limit_percent: Mapped[Optional[float]] = mapped_column(PERCENT, nullable=True)
    category_limit_percent: Mapped[Optional[float]] = mapped_column(PERCENT, nullable=True)
    # The stricter of the two limits above; 100 when neither applies.
    allowed_discount_percent: Mapped[float] = mapped_column(PERCENT, default=100, nullable=False)
    # Generated so it can never drift from the two columns it derives from,
    # even if a service writes them directly.
    over_by_points: Mapped[float] = mapped_column(
        POINTS,
        Computed("GREATEST(discount_percent - allowed_discount_percent, 0)", persisted=True),
        nullable=False,
    )

    line_net: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    line_tax: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    line_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)

    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurring_interval: Mapped[Optional[RecurringInterval]] = mapped_column(
        SAEnum(RecurringInterval, name="recurring_interval",
               values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    # Display-only snapshot of chosen variant options; never queried, so it
    # needs no FK integrity and no combination table.
    selected_options: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    source: Mapped[LineSource] = mapped_column(
        SAEnum(LineSource, name="line_source", values_callable=lambda e: [m.value for m in e]),
        default=LineSource.MANUAL, nullable=False,
    )
    # Set the moment a rep clicks "Add to Quote" on a suggestion. Nothing
    # downstream can reconstruct later whether a line was suggested or typed.
    upsell_source_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    quotation: Mapped["Quotation"] = relationship(back_populates="lines")
    product: Mapped[Optional["Product"]] = relationship(
        foreign_keys=[product_id], lazy="selectin"
    )
    category: Mapped[Optional["ProductCategory"]] = relationship(lazy="selectin")
    warehouse: Mapped[Optional["Warehouse"]] = relationship(
        foreign_keys=[warehouse_id], lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("quotation_id", "position", name="uq_quotation_line_position"),
        CheckConstraint("quantity > 0", name="ck_quotation_line_quantity_positive"),
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_quotation_line_discount_range",
        ),
    )


class QuotationComment(Base, TimestampMixin):
    """Line-level Q&A. The customer portal writes these against a line."""

    __tablename__ = "quotation_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    quotation_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="CASCADE"), nullable=True
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Internal notes must never reach the portal.
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class QuotationChangeRequest(Base, TimestampMixin):
    """A customer's counter-offer from the portal. Accepting one is what
    re-triggers the approval chain for another round."""

    __tablename__ = "quotation_change_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    counter_discount_percent: Mapped[Optional[float]] = mapped_column(PERCENT, nullable=True)
    requested_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ChangeRequestStatus] = mapped_column(
        SAEnum(ChangeRequestStatus, name="change_request_status",
               values_callable=lambda e: [m.value for m in e]),
        default=ChangeRequestStatus.OPEN, nullable=False,
    )
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "counter_discount_percent IS NULL OR "
            "(counter_discount_percent >= 0 AND counter_discount_percent <= 100)",
            name="ck_change_request_discount_range",
        ),
    )
