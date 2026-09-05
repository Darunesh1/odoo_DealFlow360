from datetime import date, datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.catalog import ProductUnit, RecurringInterval
from app.models.approval import ApprovalStatus, ApprovalTrigger
from app.models.quotation import LineSource, QuotationStatus, RiskBand
from app.schemas.approval import ApprovalRead
from app.schemas.customer import CustomerRead, PriceListRef, CustomerTierRead


class QuotationLineBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    warehouse_id: Optional[uuid.UUID] = None
    product_name: str
    category_name: Optional[str] = None
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
    selected_options: List[dict] = Field(default_factory=list)
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
    product_id: uuid.UUID
    quantity: int = Field(ge=1)
    line_discount_percent: float = Field(default=0, ge=0, le=100)
    selected_options: List[dict] = Field(default_factory=list)
    source: LineSource = LineSource.MANUAL


class QuotationLineUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1)
    line_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    selected_options: Optional[List[dict]] = None
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
    price_list_id: Optional[uuid.UUID] = None
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
    price_list: Optional[PriceListRef] = None
    customer_tier: Optional[CustomerTierRead] = None
    lines: List[QuotationLineRead] = Field(default_factory=list)
    approval: Optional[ApprovalRead] = None


class QuotationCreate(BaseModel):
    customer_id: uuid.UUID
    price_list_id: Optional[uuid.UUID] = None
    recipient_email: Optional[EmailStr] = None
    order_discount_percent: float = Field(default=0, ge=0, le=100)
    notes: Optional[str] = None
    requested_delivery_date: Optional[date] = None
    valid_until: Optional[date] = None


class QuotationUpdate(BaseModel):
    price_list_id: Optional[uuid.UUID] = None
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
