from datetime import date, datetime
import enum
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.catalog import ProductUnit, RecurringInterval
from app.models.approval import ApprovalStatus, ApprovalTrigger
from app.models.quotation import LineSource, QuotationStatus, RiskBand
from app.schemas.approval import ApprovalRead
from app.schemas.common import Page
from app.schemas.customer import CustomerRead, CustomerTierRead


class QuotationLineBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: Optional[uuid.UUID] = None
    variant_id: Optional[uuid.UUID] = None
    warehouse_id: Optional[uuid.UUID] = None
    product_name: str
    variant_name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    warehouse_name: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_bin_location: Optional[str] = None
    stock_available_at_entry: Optional[int] = None
    quantity: int
    unit_price: float
    list_price_at_entry: float
    unit_cost: float = 0
    tax_percent: float = 0
    line_discount_percent: float = 0
    discount_percent: float = 0
    tier_limit_percent: Optional[float] = None
    category_limit_percent: Optional[float] = None
    allowed_discount_percent: float = 100
    line_net: float = 0
    line_tax: float = 0
    line_total: float = 0
    is_recurring: bool = False
    recurring_interval: Optional[RecurringInterval] = None
    selected_options: dict = Field(default_factory=dict)
    source: LineSource = LineSource.MANUAL
    upsell_source_product_id: Optional[uuid.UUID] = None


class QuotationLineRead(QuotationLineBase):
    id: uuid.UUID
    quotation_id: uuid.UUID
    position: int
    over_by_points: float
    created_at: datetime
    updated_at: datetime


class QuotationLineCreate(BaseModel):
    # The variant is what carries the SKU, the stock and the tier price, so it
    # is what a line points at. The product falls out of it.
    variant_id: uuid.UUID
    quantity: int = Field(ge=1)
    line_discount_percent: float = Field(default=0, ge=0, le=100)
    source: LineSource = LineSource.MANUAL


class QuotationLineUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1)
    line_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    source: Optional[LineSource] = None


class QuotationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: str
    customer_id: uuid.UUID
    recipient_email: Optional[EmailStr] = None
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    sales_team_id: Optional[uuid.UUID] = None
    status: QuotationStatus = QuotationStatus.DRAFT
    currency: str = "USD"
    customer_tier_id: Optional[uuid.UUID] = None
    tier_max_discount_percent: Optional[float] = None
    order_discount_percent: float = 0
    subtotal: float = 0
    discount_total: float = 0
    tax_total: float = 0
    total: float = 0
    margin_total: float = 0
    blended_risk_score: float = 0
    risk_band: RiskBand = RiskBand.NONE
    max_line_over_points: float = 0
    weighted_over_points: float = 0
    requires_approval: bool = False
    current_round: int = 0
    requested_delivery_date: Optional[date] = None
    promised_delivery_date: Optional[date] = None
    valid_until: Optional[date] = None
    last_activity_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    notes: Optional[str] = None


class QuotationRead(QuotationBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    customer: CustomerRead
    customer_tier: Optional[CustomerTierRead] = None
    lines: List[QuotationLineRead] = Field(default_factory=list)
    approval: Optional[ApprovalRead] = None


class QuotationSort(str, enum.Enum):
    NUMBER = "number"
    CUSTOMER = "customer"
    TOTAL = "total"
    STATUS = "status"
    RISK = "risk"
    UPDATED = "updated"


class QuotationListRow(BaseModel):
    """One card, or one table row, on the quotations list (screen 3)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: str
    customer_tier: Optional[str] = None
    owner_name: Optional[str] = None
    status: QuotationStatus
    currency: str
    total: float
    margin_total: float
    line_count: int = 0
    risk_band: RiskBand = RiskBand.NONE
    blended_risk_score: float = 0
    requires_approval: bool = False
    valid_until: Optional[date] = None
    last_activity_at: Optional[datetime] = None
    updated_at: datetime


class QuotationStageCounts(BaseModel):
    """The stage chips above the list, and the Kanban column headers."""

    draft: int = 0
    pending_approval: int = 0
    approved: int = 0
    negotiation: int = 0
    confirmed: int = 0
    rejected: int = 0
    cancelled: int = 0


class QuotationListPage(Page[QuotationListRow]):
    """A page of rows plus the counts, so the chips do not need a second call."""

    counts: QuotationStageCounts


class UpsellSuggestion(BaseModel):
    """One card in the upsell panel (spec B5)."""

    product_id: uuid.UUID
    variant_id: uuid.UUID
    name: str
    category: str
    sku: str
    unit_price: float
    unit_cost: float
    margin_delta: float
    margin_percent: float
    is_promoted: bool
    promotion_label: Optional[str] = None
    is_recurring: bool
    reason: str


class QuotationCreate(BaseModel):
    customer_id: uuid.UUID
    currency: str = Field(default="USD", min_length=3, max_length=3)
    recipient_email: Optional[EmailStr] = None
    order_discount_percent: float = Field(default=0, ge=0, le=100)
    notes: Optional[str] = None
    requested_delivery_date: Optional[date] = None
    valid_until: Optional[date] = None


class QuotationUpdate(BaseModel):
    recipient_email: Optional[EmailStr] = None
    order_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None
    requested_delivery_date: Optional[date] = None
    promised_delivery_date: Optional[date] = None
    valid_until: Optional[date] = None


class QuotationDiscountUpdate(BaseModel):
    order_discount_percent: float = Field(ge=0, le=100)


class QuotationSubmitResponse(BaseModel):
    quotation: QuotationRead
    approval_required: bool
    approval: Optional[ApprovalRead] = None
