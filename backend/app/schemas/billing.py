"""Subscriptions, invoices and payments (mockup screens 9, 10, 12 and 13)."""

from datetime import date, datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.billing import (
    InvoiceKind,
    InvoiceLineType,
    InvoiceStatus,
    PaymentMethod,
    SubscriptionEventType,
    SubscriptionStatus,
)
from app.models.catalog import RecurringInterval


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #

class SubscriptionRow(BaseModel):
    """One row of the subscriptions list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    quotation_id: uuid.UUID
    quotation_number: str
    plan_name: str
    interval: RecurringInterval
    quantity: int
    unit_price: float
    currency: str
    status: SubscriptionStatus
    start_date: date
    current_period_start: date
    current_period_end: date
    # Null is literally the "-" in the mockup's paused row.
    next_billing_date: Optional[date] = None
    cancel_at_period_end: bool = False


class SubscriptionCounts(BaseModel):
    active: int = 0
    paused: int = 0
    cancelled: int = 0
    expired: int = 0


class SubscriptionEventRead(BaseModel):
    """One entry of the proration history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: SubscriptionEventType
    effective_date: date
    previous_quantity: Optional[int] = None
    new_quantity: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    days_in_period: Optional[int] = None
    days_remaining: Optional[int] = None
    proration_factor: Optional[float] = None
    proration_amount: Optional[float] = None
    reason: Optional[str] = None
    created_at: datetime


class OneTimeLineRead(BaseModel):
    """A one-time line from the originating order, shown beside the recurring
    ones on the billing detail screen."""

    id: uuid.UUID
    description: str
    quantity: int
    unit_price: float
    amount: float


class UpcomingBill(BaseModel):
    """One row of the upcoming billing schedule."""

    period_start: date
    period_end: date
    amount: float


class SubscriptionDetail(SubscriptionRow):
    one_time_lines: List[OneTimeLineRead] = Field(default_factory=list)
    recurring_lines: List[SubscriptionRow] = Field(default_factory=list)
    upcoming: List[UpcomingBill] = Field(default_factory=list)
    events: List[SubscriptionEventRead] = Field(default_factory=list)


class QuantityChangeInput(BaseModel):
    quantity: int = Field(ge=1)
    effective_date: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=255)


class CancelInput(BaseModel):
    # Default is the kind one: the customer keeps what they have paid for.
    at_period_end: bool = True
    reason: Optional[str] = Field(default=None, max_length=255)


# --------------------------------------------------------------------------- #
# Invoices and payments
# --------------------------------------------------------------------------- #

class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_type: InvoiceLineType
    description: str
    quantity: int
    unit_price: float
    tax_percent: float
    tax_amount: float
    line_subtotal: float
    line_total: float
    service_period_start: Optional[date] = None
    service_period_end: Optional[date] = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: float
    is_refund: bool
    method: PaymentMethod
    reference: Optional[str] = None
    received_at: datetime
    note: Optional[str] = None


class InvoiceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: str
    quotation_id: Optional[uuid.UUID] = None
    quotation_number: Optional[str] = None
    kind: InvoiceKind
    status: InvoiceStatus
    issue_date: date
    due_date: date
    currency: str
    subtotal: float
    tax_total: float
    total: float
    amount_paid: float
    paid_at: Optional[datetime] = None


class InvoiceCounts(BaseModel):
    unpaid: int = 0
    partially_paid: int = 0
    paid: int = 0
    draft: int = 0
    void: int = 0


class InvoiceDetail(InvoiceRow):
    lines: List[InvoiceLineRead] = Field(default_factory=list)
    payments: List[PaymentRead] = Field(default_factory=list)
    # The Order Confirmed -> Shipped -> Invoiced -> Paid strip at the top of
    # screen 13. Each is a fact about the order, not a stored status.
    order_confirmed: bool = False
    order_shipped: bool = False
    order_invoiced: bool = True
    order_paid: bool = False
    # Every invoice raised against the same order, so the detail screen can
    # reconcile the one-time and recurring bills side by side.
    related: List[InvoiceRow] = Field(default_factory=list)


class RecordPaymentInput(BaseModel):
    amount: float = Field(gt=0)
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    reference: Optional[str] = Field(default=None, max_length=255)
    received_on: Optional[date] = None
    is_refund: bool = False
    note: Optional[str] = Field(default=None, max_length=255)
