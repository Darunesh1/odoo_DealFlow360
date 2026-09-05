"""The customer-facing view (mockup screen 11).

Deliberately a separate set of schemas rather than a filtered reuse of
QuotationRead. Section 7 of the spec: *"The customer facing negotiation screen
must be a real, separate, restricted view, not just another internal screen
with a different label."*

The fields that are absent are the point: no unit_cost, no margin, no blended
risk score, no approval chain. A field cannot leak through a schema that has
no place to put it.
"""

from datetime import date, datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.catalog import RecurringInterval
from app.models.quotation import ChangeRequestStatus, QuotationStatus


class PortalLine(BaseModel):
    """One line as the customer sees it: what they get and what it costs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_name: str
    variant_name: Optional[str] = None
    quantity: int
    unit_price: float
    discount_percent: float
    # What this line comes to after its discount and BEFORE tax. Shown as the
    # row total, so price x (1 - discount) reconciles on the row; tax is added
    # once in the summary rather than silently inside every line.
    line_net: float
    line_tax: float
    line_total: float
    is_recurring: bool
    recurring_interval: Optional[RecurringInterval] = None


class PortalComment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_line_id: Optional[uuid.UUID] = None
    author_name: str
    body: str
    created_at: datetime


class PortalChangeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requested_by_name: str
    counter_discount_percent: Optional[float] = None
    requested_delivery_date: Optional[date] = None
    note: Optional[str] = None
    status: ChangeRequestStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None


class PortalQuotationRow(BaseModel):
    id: uuid.UUID
    number: str
    status: QuotationStatus
    currency: str
    total: float
    valid_until: Optional[date] = None
    updated_at: datetime


class PortalQuotation(PortalQuotationRow):
    customer_name: str
    subtotal: float
    discount_total: float
    tax_total: float
    order_discount_percent: float
    requested_delivery_date: Optional[date] = None
    promised_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    lines: List[PortalLine] = Field(default_factory=list)
    comments: List[PortalComment] = Field(default_factory=list)
    change_requests: List[PortalChangeRequest] = Field(default_factory=list)
    # Whether the customer may still act, so the screen does not offer buttons
    # the server will refuse.
    can_negotiate: bool = False
    can_confirm: bool = False


class CommentInput(BaseModel):
    quotation_line_id: Optional[uuid.UUID] = None
    body: str = Field(min_length=1, max_length=2000)


class ChangeRequestInput(BaseModel):
    """The counter-offer. All three are optional individually, but asking for
    nothing at all is refused by the route."""

    counter_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    requested_delivery_date: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class PortalInvoiceRow(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    issue_date: date
    due_date: date
    currency: str
    total: float
    amount_paid: float
