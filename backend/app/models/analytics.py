"""Sales history, deal health alerts and the audit trail."""

from datetime import datetime
import enum
from typing import Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import MONEY, PERCENT, UNIT_PRICE, TimestampMixin
from app.models.catalog import RecurringInterval
from app.models.quotation import LineSource, RiskBand


class AlertType(str, enum.Enum):
    STALLED_DEAL = "stalled_deal"
    DISCOUNT_ANOMALY = "discount_anomaly"
    DELIVERY_SLIPPAGE = "delivery_slippage"


class AlertStatus(str, enum.Enum):
    OPEN = "open"
    NUDGED = "nudged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class AuditAction(str, enum.Enum):
    CREATED = "created"
    EDITED = "edited"
    DELETED = "deleted"
    SUBMITTED = "submitted"
    RESUBMITTED = "resubmitted"
    APPROVED = "approved"
    AUTO_APPROVED = "auto_approved"
    RETURNED = "returned"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    CUSTOMER_COUNTERED = "customer_countered"
    REPRICED = "repriced"


class SalesRecord(Base, TimestampMixin):
    """The immutable history of what actually sold - one row per confirmed line.

    Not derived from quotation_lines at read time, for three reasons. Lines
    stay editable after confirmation, so derived history silently changes, and
    a "top product" report that shifts retroactively is worse than none. The
    reporting dimensions have to freeze too: if a product moves category or a
    rep changes team, last quarter's numbers must stay as they were, so
    category, tier and team are snapshotted here rather than joined live. And
    every report the mockup shows becomes one indexed scan instead of a
    four-way join filtered on quotation status.

    Written at confirmation only. Recurring revenue in later periods is the
    invoice trail's job - otherwise a monthly subscription would inflate
    "units sold" every cycle.
    """

    __tablename__ = "sales_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    quotation_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    sales_rep_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sales_rep_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Reporting dimensions, snapshotted so historical numbers never move.
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    sku: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    customer_tier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_tiers.id", ondelete="SET NULL"), nullable=True
    )
    sales_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_teams.id", ondelete="SET NULL"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(UNIT_PRICE, nullable=False)
    unit_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    discount_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    line_net: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    line_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    margin_amount: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)

    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurring_interval: Mapped[Optional[RecurringInterval]] = mapped_column(
        SAEnum(RecurringInterval, name="recurring_interval",
               values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    # Carried from quotation_lines.source. Without it "Top Upsold Product" is
    # unanswerable, because nothing downstream can reconstruct whether a line
    # was suggested or typed.
    source: Mapped[LineSource] = mapped_column(
        SAEnum(LineSource, name="line_source", values_callable=lambda e: [m.value for m in e]),
        default=LineSource.MANUAL, nullable=False,
    )
    came_from_upsell: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_record_quantity_positive"),
        # One index per reporting dimension the mockup filters on.
        Index("ix_sales_record_product", "product_id", "sold_at"),
        Index("ix_sales_record_rep", "sales_rep_id", "sold_at"),
        Index("ix_sales_record_category", "category", "sold_at"),
        Index("ix_sales_record_customer", "customer_id", "sold_at"),
        Index("ix_sales_record_team", "sales_team_id", "sold_at"),
    )


class DealHealthAlert(Base, TimestampMixin):
    """A flag raised on the Deal Health dashboard."""

    __tablename__ = "deal_health_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        SAEnum(AlertType, name="alert_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    severity: Mapped[RiskBand] = mapped_column(
        SAEnum(RiskBand, name="risk_band", values_callable=lambda e: [m.value for m in e]),
        default=RiskBand.LOW, nullable=False,
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus, name="alert_status", values_callable=lambda e: [m.value for m in e]),
        default=AlertStatus.OPEN, index=True, nullable=False,
    )
    flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    action_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class AuditLog(Base, TimestampMixin):
    """Every approval, rejection and edit, with user, timestamp and reason.

    Deliberately generic rather than one audit table per entity, and keyed to
    the entity rather than to a single approval round so a trail spans rounds.
    actor_name is snapshotted because user_id is SET NULL - the trail must
    survive the user being deleted.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id", "created_at"),
    )
