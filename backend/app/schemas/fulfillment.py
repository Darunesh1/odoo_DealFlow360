"""Fulfillment and warehouse splitting (mockup screens 7 and 8)."""

from datetime import date, datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.fulfillment import (
    AllocationStatus,
    FulfillmentStatus,
    ShipmentStatus,
    SplitStrategy,
)
from app.models.quotation import QuotationStatus


class AllocationRead(BaseModel):
    """One row of the split table: how much of one line comes from where."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_line_id: uuid.UUID
    line_label: str
    sku: Optional[str] = None
    warehouse_id: uuid.UUID
    warehouse_name: str
    warehouse_code: str
    quantity: int
    quantity_shipped: int
    status: AllocationStatus
    estimated_shipping_cost: float
    expected_restock_date: Optional[date] = None
    is_manual: bool


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    warehouse_id: uuid.UUID
    warehouse_name: str
    status: ShipmentStatus
    estimated_cost: float
    actual_cost: float = 0
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    unit_count: int = 0


class FulfillmentRow(BaseModel):
    """One "order awaiting fulfillment" row on screen 7."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_id: uuid.UUID
    quotation_number: str
    customer_name: str
    quotation_status: QuotationStatus
    status: FulfillmentStatus
    strategy: SplitStrategy
    currency: str
    estimated_shipping_cost: float
    estimated_shipment_count: int
    warehouse_names: List[str] = Field(default_factory=list)
    has_backorder: bool = False
    requested_delivery_date: Optional[date] = None
    accepted_at: Optional[datetime] = None
    created_at: datetime


class FulfillmentDetail(FulfillmentRow):
    """Screen 8, in one response."""

    allocations: List[AllocationRead] = Field(default_factory=list)
    shipments: List[ShipmentRead] = Field(default_factory=list)
    # True when stock has arrived for something still backordered, which is
    # what raises the mockup's automatic "Consolidate Remaining Backorder".
    can_consolidate: bool = False
    consolidated_at: Optional[datetime] = None


class OverrideRow(BaseModel):
    quotation_line_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int = Field(ge=1)
    status: Optional[AllocationStatus] = None
    # Finance may state the shipping cost outright rather than take the rate.
    estimated_shipping_cost: Optional[float] = Field(default=None, ge=0)


class OverrideInput(BaseModel):
    rows: List[OverrideRow] = Field(min_length=1)
