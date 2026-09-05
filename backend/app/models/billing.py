"""Subscriptions, proration history, invoices and payments."""

from datetime import date, datetime
import enum
from typing import Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, PERCENT, RATIO, UNIT_PRICE, TimestampMixin
from app.models.catalog import RecurringInterval


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class SubscriptionEventType(str, enum.Enum):
    CREATED = "created"
    RENEWED = "renewed"
    QUANTITY_CHANGED = "quantity_changed"
    PLAN_CHANGED = "plan_changed"
    PRICE_CHANGED = "price_changed"
    PAUSED = "paused"
    RESUMED = "resumed"
    CANCELLED = "cancelled"


class BillingTiming(str, enum.Enum):
    ADVANCE = "advance"
    ARREARS = "arrears"


class InvoiceKind(str, enum.Enum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"


class InvoiceLineType(str, enum.Enum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"
    PRORATION_CHARGE = "proration_charge"
    PRORATION_CREDIT = "proration_credit"
    SHIPPING = "shipping"
    ADJUSTMENT = "adjustment"


class PaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CHEQUE = "cheque"
    CASH = "cash"
    CREDIT_APPLIED = "credit_applied"
    OTHER = "other"


class CreditNoteStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class Subscription(Base, TimestampMixin):
    """One recurring order line, become a contract.

    The cycle, price and timing are SNAPSHOTS of the product at order time: an
    admin repricing "Care Plan 2yr" from $46 to $52 must not retroactively
    change live subscriptions or reprice history.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    # Unique, which makes order confirmation idempotent: a double-clicked
    # Confirm or a retried Celery task raises IntegrityError rather than
    # creating a second subscription.
    quotation_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Nullable only for the theoretical plan with no variant; in practice every
    # product owns at least one, so this is always populated. It carries the SKU
    # and the tier price the plan was actually sold at.
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=True,
    )
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    interval: Mapped[RecurringInterval] = mapped_column(
        SAEnum(RecurringInterval, name="recurring_interval",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    interval_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    billing_timing: Mapped[BillingTiming] = mapped_column(
        SAEnum(BillingTiming, name="billing_timing",
               values_callable=lambda e: [m.value for m in e]),
        default=BillingTiming.ADVANCE, nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(UNIT_PRICE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status",
               values_callable=lambda e: [m.value for m in e]),
        default=SubscriptionStatus.ACTIVE, nullable=False,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    # Nullable on purpose. It is literally the "-" in the mockup's paused row,
    # AND it drops the subscription out of the biller's partial index - two
    # independent guards against billing a paused customer. A NOT NULL column
    # would force a sentinel far-future date, and sentinel dates arrive.
    next_billing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list["SubscriptionEvent"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_subscription_quantity_positive"),
        CheckConstraint(
            "current_period_end > current_period_start", name="ck_subscription_period_ordered"
        ),
        Index("ix_subscription_customer_status", "customer_id", "status"),
        Index(
            "ix_subscription_due", "next_billing_date",
            postgresql_where=text("status = 'active' AND next_billing_date IS NOT NULL"),
        ),
    )


class SubscriptionEvent(Base, TimestampMixin):
    """Lifecycle audit and proration history in one table.

    Every proration IS a lifecycle event, and the detail screen wants one
    timeline; splitting them would make "proration history" a UNION for no
    gain. Non-financial events simply leave the proration columns NULL.
    """

    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    event_type: Mapped[SubscriptionEventType] = mapped_column(
        SAEnum(SubscriptionEventType, name="subscription_event_type",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    previous_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_unit_price: Mapped[Optional[float]] = mapped_column(UNIT_PRICE, nullable=True)
    new_unit_price: Mapped[Optional[float]] = mapped_column(UNIT_PRICE, nullable=True)

    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    days_in_period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    days_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    proration_factor: Mapped[Optional[float]] = mapped_column(RATIO, nullable=True)
    # Signed: positive is a charge, negative is a credit.
    proration_amount: Mapped[Optional[float]] = mapped_column(MONEY, nullable=True)

    # NULL here means "prorated but not yet billed". The nullable FK IS the
    # pending-proration queue - the biller sweeps it on the next invoice run,
    # so there is no queue table and no job state.
    resulting_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    resulting_invoice_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_lines.id", ondelete="SET NULL"), nullable=True
    )
    credit_note_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    subscription: Mapped["Subscription"] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_subscription_event_history", "subscription_id", "effective_date"),
        Index(
            "ix_subscription_event_pending_proration", "subscription_id",
            postgresql_where=text(
                "proration_amount IS NOT NULL AND resulting_invoice_line_id IS NULL"
            ),
        ),
    )


class Invoice(Base, TimestampMixin):
    """A bill. quotation_id is populated on RECURRING invoices too, not just
    one-time ones - the invoice detail screen is really an order-level billing
    reconciliation panel and needs to find both."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    quotation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="SET NULL"),
        index=True, nullable=True,
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[InvoiceKind] = mapped_column(
        SAEnum(InvoiceKind, name="invoice_kind", values_callable=lambda e: [m.value for m in e]),
        default=InvoiceKind.ONE_TIME, nullable=False,
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status",
               values_callable=lambda e: [m.value for m in e]),
        default=InvoiceStatus.DRAFT, nullable=False,
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    subtotal: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    tax_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    amount_paid: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin",
        foreign_keys="InvoiceLine.invoice_id",
    )

    __table_args__ = (
        CheckConstraint("due_date >= issue_date", name="ck_invoice_due_after_issue"),
        CheckConstraint(
            "total >= 0 AND amount_paid >= 0", name="ck_invoice_amounts_non_negative"
        ),
        Index("ix_invoice_customer_status", "customer_id", "status"),
        Index(
            "ix_invoice_open_due", "due_date",
            postgresql_where=text("status IN ('unpaid','partially_paid')"),
        ),
    )


class InvoiceLine(Base, TimestampMixin):
    """One billed item.

    A one-time line MUST point at a shipment line. Combined with
    ShipmentLine's invoiced-within-shipped check, there is no sequence of
    writes that bills a physical unit before it ships.
    """

    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    line_type: Mapped[InvoiceLineType] = mapped_column(
        SAEnum(InvoiceLineType, name="invoice_line_type",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    # Null on the lines that have no SKU behind them - shipping, proration
    # charges and credits.
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    quotation_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="SET NULL"),
        index=True, nullable=True,
    )
    # The delivery-to-billing link. RESTRICT so shipping history cannot be
    # deleted out from under an issued invoice.
    shipment_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipment_lines.id", ondelete="RESTRICT"),
        index=True, nullable=True,
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    service_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    service_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(UNIT_PRICE, nullable=False)
    discount_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    tax_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    line_subtotal: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    line_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines", foreign_keys=[invoice_id])

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_line_quantity_positive"),
        # Nothing physical is billable without a dispatch behind it.
        CheckConstraint(
            "line_type <> 'one_time' OR shipment_line_id IS NOT NULL",
            name="ck_invoice_line_one_time_requires_shipment",
        ),
        CheckConstraint(
            "line_type NOT IN ('recurring','proration_charge','proration_credit') "
            "OR (subscription_id IS NOT NULL AND service_period_start IS NOT NULL)",
            name="ck_invoice_line_recurring_requires_period",
        ),
        # Billing idempotency: one recurring charge per subscription per period,
        # ever. A retried task or a duplicate cron tick cannot double-bill, and
        # this is why future billing periods need not be materialised.
        Index(
            "uq_invoice_line_subscription_period", "subscription_id", "service_period_start",
            unique=True, postgresql_where=text("line_type = 'recurring'"),
        ),
    )


class Payment(Base, TimestampMixin):
    """Money received, or refunded. Separate from the invoice because partial
    payments are a list; invoices.amount_paid is their signed sum."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    # Refunds are payments with a direction, not a separate table: same fields,
    # same screen.
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method",
               values_callable=lambda e: [m.value for m in e]),
        default=PaymentMethod.BANK_TRANSFER, nullable=False,
    )
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    credit_note_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        # Always positive; is_refund carries the sign.
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
    )


class CreditNote(Base, TimestampMixin):
    """Issued when a cancellation or downgrade leaves the customer in credit."""

    __tablename__ = "credit_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[CreditNoteStatus] = mapped_column(
        SAEnum(CreditNoteStatus, name="credit_note_status",
               values_callable=lambda e: [m.value for m in e]),
        default=CreditNoteStatus.DRAFT, nullable=False,
    )
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_credit_note_amount_positive"),
    )
