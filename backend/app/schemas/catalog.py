from datetime import datetime
import enum
from typing import Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.catalog import ProductStatus, ProductUnit, RecurringInterval


# --------------------------------------------------------------------------- #
# Currencies
# --------------------------------------------------------------------------- #

class CurrencyBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    symbol: str = ""
    rate_to_base: float = 1
    is_base: bool = False
    is_active: bool = True


class CurrencyRead(CurrencyBase):
    created_at: datetime
    updated_at: datetime


class CurrencyCreate(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1, max_length=64)
    symbol: str = Field(default="", max_length=8)
    rate_to_base: float = Field(gt=0)
    is_active: bool = True


class CurrencyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    symbol: Optional[str] = Field(default=None, max_length=8)
    rate_to_base: Optional[float] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


# --------------------------------------------------------------------------- #
# Category discount ceilings (screen 18, right-hand panel)
# --------------------------------------------------------------------------- #

class CategoryLimitBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    max_discount_percent: float


class CategoryLimitRead(CategoryLimitBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CategoryLimitCreate(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    max_discount_percent: float = Field(ge=0, le=100)


class CategoryLimitUpdate(BaseModel):
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    max_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)


# --------------------------------------------------------------------------- #
# Variants
# --------------------------------------------------------------------------- #

class VariantPriceRead(BaseModel):
    """A derived cell. Nothing here is typed, so there is nothing to write back."""

    model_config = ConfigDict(from_attributes=True)

    tier_id: uuid.UUID
    currency_code: str
    unit_price: float


class VariantAttributeValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    value: str
    position: int


class VariantAttributeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int
    values: List[VariantAttributeValueRead] = Field(default_factory=list)


class VariantStockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: uuid.UUID
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    options: Dict[str, str] = Field(default_factory=dict)
    unit_cost: float = 0
    base_price: float = 0
    is_default: bool = False
    is_active: bool = True
    prices: List[VariantPriceRead] = Field(default_factory=list)
    stock: List[VariantStockRead] = Field(default_factory=list)


class VariantAttributeInput(BaseModel):
    """One axis of the matrix, with every value the admin typed for it."""

    name: str = Field(min_length=1, max_length=100)
    values: List[str] = Field(min_length=1)


class VariantStockInput(BaseModel):
    warehouse_id: uuid.UUID
    quantity_on_hand: int = Field(ge=0)


class VariantRowInput(BaseModel):
    """One row of the generated-variants table.

    Two amounts, both in the base currency; every tier and currency price is
    derived from base_price. Both are required, and so is a quantity for each
    active warehouse on a stocked product - the service rejects the batch and
    names the SKU otherwise.
    """

    id: uuid.UUID
    sku: str = Field(min_length=1, max_length=64)
    unit_cost: float = Field(gt=0)
    base_price: float = Field(gt=0)
    is_active: bool = True
    stock: List[VariantStockInput] = Field(default_factory=list)


class VariantMatrixSave(BaseModel):
    rows: List[VariantRowInput]


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

class ProductBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    category: str
    description: Optional[str] = None
    unit: ProductUnit = ProductUnit.EACH
    tax_percent: float = 0
    is_subscription: bool = False
    recurring_interval: Optional[RecurringInterval] = None
    has_variants: bool = False
    is_promoted: bool = False
    promotion_label: Optional[str] = None
    status: ProductStatus = ProductStatus.ACTIVE


class ProductRead(ProductBase):
    """The full edit payload behind screen 17."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    attributes: List[VariantAttributeRead] = Field(default_factory=list)
    variants: List[ProductVariantRead] = Field(default_factory=list)


class ProductSort(str, enum.Enum):
    NAME = "name"
    CATEGORY = "category"
    VARIANTS = "variants"
    PRICE = "price"
    TAX = "tax"
    STATUS = "status"


class SortOrder(str, enum.Enum):
    ASC = "asc"
    DESC = "desc"


class ProductListRow(BaseModel):
    """One row of screen 16's table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    unit: ProductUnit
    tax_percent: float
    status: ProductStatus
    has_variants: bool
    is_subscription: bool
    recurring_interval: Optional[RecurringInterval] = None
    variant_count: int = 0
    # Min and max across every variant, in the base currency. Both None when no
    # price has been entered yet.
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    base_currency: str = "USD"


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    unit: ProductUnit = ProductUnit.EACH
    tax_percent: float = Field(default=0, ge=0, le=100)
    is_subscription: bool = False
    recurring_interval: Optional[RecurringInterval] = None
    has_variants: bool = False
    is_promoted: bool = False
    promotion_label: Optional[str] = None
    # Present only when has_variants is true; the axes to build the matrix from.
    attributes: List[VariantAttributeInput] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    unit: Optional[ProductUnit] = None
    tax_percent: Optional[float] = Field(default=None, ge=0, le=100)
    is_subscription: Optional[bool] = None
    recurring_interval: Optional[RecurringInterval] = None
    has_variants: Optional[bool] = None
    is_promoted: Optional[bool] = None
    promotion_label: Optional[str] = None
    attributes: Optional[List[VariantAttributeInput]] = None


class CatalogStats(BaseModel):
    """Screen 16's three KPI boxes."""

    products_active: int
    products_archived: int
    tier_count: int
    currency_count: int
    sku_count: int


class PriceMatrixRow(BaseModel):
    """One line of the read-only Price Lists matrix."""

    product_id: uuid.UUID
    product_name: str
    variant_id: uuid.UUID
    variant_name: str
    sku: str
    tier_name: str
    currency_code: str
    unit_price: float


# --------------------------------------------------------------------------- #
# Warehouses and stock
# --------------------------------------------------------------------------- #

class WarehouseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    address: Optional[str] = None
    is_active: bool = True


class WarehouseRead(WarehouseBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = None
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=16)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = None
    is_active: Optional[bool] = None


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    reorder_point: int
    reorder_quantity: int
    lead_time_days: int
    bin_location: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    warehouse_name: str
    warehouse_code: str
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str


class StockUpsert(BaseModel):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_on_hand: int = Field(ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    bin_location: Optional[str] = None
