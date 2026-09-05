from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.catalog import ProductUnit, RecurringInterval
from app.schemas.customer import CustomerTierRead


class ProductCategoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    max_discount_percent: Optional[float] = None
    sort_order: int = 0
    is_active: bool = True


class ProductCategoryRead(ProductCategoryBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProductCategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    max_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    sort_order: int = 0
    is_active: bool = True


class ProductCategoryUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    max_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProductBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    category_id: uuid.UUID
    description: Optional[str] = None
    list_price: float
    unit_cost: float = 0
    unit: ProductUnit = ProductUnit.EACH
    tax_percent: float = 0
    is_subscription: bool = False
    recurring_interval: Optional[RecurringInterval] = None
    is_promoted: bool = False
    promotion_label: Optional[str] = None
    is_active: bool = True


class ProductRead(ProductBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    category: ProductCategoryRead


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category_id: uuid.UUID
    description: Optional[str] = None
    list_price: float = Field(ge=0)
    unit_cost: float = Field(default=0, ge=0)
    unit: ProductUnit = ProductUnit.EACH
    tax_percent: float = Field(default=0, ge=0, le=100)
    is_subscription: bool = False
    recurring_interval: Optional[RecurringInterval] = None
    is_promoted: bool = False
    promotion_label: Optional[str] = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    list_price: Optional[float] = Field(default=None, ge=0)
    unit_cost: Optional[float] = Field(default=None, ge=0)
    unit: Optional[ProductUnit] = None
    tax_percent: Optional[float] = Field(default=None, ge=0, le=100)
    is_subscription: Optional[bool] = None
    recurring_interval: Optional[RecurringInterval] = None
    is_promoted: Optional[bool] = None
    promotion_label: Optional[str] = None
    is_active: Optional[bool] = None


class PriceListItemBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price_list_id: uuid.UUID
    product_id: uuid.UUID
    unit_price: float


class PriceListItemRead(PriceListItemBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    product_name: str
    sku: str


class PriceListItemUpsert(BaseModel):
    product_id: uuid.UUID
    unit_price: float = Field(ge=0)


class PriceListBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    tier_id: Optional[uuid.UUID] = None
    currency: str = "USD"
    adjustment_percent: float = 0
    is_active: bool = True


class PriceListRead(PriceListBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: List[PriceListItemRead] = Field(default_factory=list)
    tier: Optional[CustomerTierRead] = None


class PriceListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tier_id: Optional[uuid.UUID] = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    adjustment_percent: float = 0
    is_active: bool = True


class PriceListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tier_id: Optional[uuid.UUID] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    adjustment_percent: Optional[float] = None
    is_active: Optional[bool] = None


class WarehouseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    address: Optional[str] = None
    shipping_base_cost: float = 0
    shipping_cost_per_unit: float = 0
    shipping_cost_weight: float = 1
    split_priority: int = 100
    is_active: bool = True


class WarehouseRead(WarehouseBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = None
    shipping_base_cost: float = 0
    shipping_cost_per_unit: float = 0
    shipping_cost_weight: float = 1
    split_priority: int = 100
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=16)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = None
    shipping_base_cost: Optional[float] = None
    shipping_cost_per_unit: Optional[float] = None
    shipping_cost_weight: Optional[float] = None
    split_priority: Optional[int] = None
    is_active: Optional[bool] = None


class StockBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity_on_hand: int = 0
    quantity_reserved: int = 0
    reorder_point: int = 0
    reorder_quantity: int = 0
    lead_time_days: int = 0
    bin_location: Optional[str] = None


class StockRead(StockBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    quantity_available: int
    warehouse_name: str
    warehouse_code: str
    product_name: str
    sku: str


class StockUpsert(BaseModel):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity_on_hand: int = Field(ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    bin_location: Optional[str] = None
