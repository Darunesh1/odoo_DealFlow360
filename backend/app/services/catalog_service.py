"""Catalog configuration: currencies, tiers, category ceilings, products,
warehouses, stock and customers."""

from __future__ import annotations

from typing import Optional, Sequence
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import (
    CategoryDiscountLimit,
    Currency,
    Product,
    ProductStatus,
    ProductVariant,
    VariantPrice,
)
from app.models.customer import Customer, CustomerTier
from app.models.inventory import StockItem, Warehouse
from app.models.quotation import Quotation, QuotationLine
from app.schemas.catalog import (
    CategoryLimitCreate,
    CategoryLimitUpdate,
    CurrencyCreate,
    CurrencyUpdate,
    ProductCreate,
    ProductUpdate,
    StockUpsert,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.schemas.customer import (
    CustomerCreate,
    CustomerTierCreate,
    CustomerTierUpdate,
    CustomerUpdate,
)
from app.services import pricing_service, variant_service


class InUseError(Exception):
    """Raised when a delete is refused because something still references the row."""


async def _get_one(db: AsyncSession, stmt):
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Currencies
# --------------------------------------------------------------------------- #

async def list_currencies(db: AsyncSession) -> Sequence[Currency]:
    return await pricing_service.list_currencies(db)


async def get_currency(db: AsyncSession, code: str) -> Optional[Currency]:
    return await pricing_service.get_currency(db, code)


async def create_currency(db: AsyncSession, obj_in: CurrencyCreate) -> Currency:
    currency = Currency(
        code=obj_in.code.upper(),
        name=obj_in.name,
        symbol=obj_in.symbol,
        rate_to_base=obj_in.rate_to_base,
        is_base=False,
        is_active=obj_in.is_active,
    )
    db.add(currency)
    await db.commit()
    await db.refresh(currency)
    # A new currency has no price rows yet; give it the full column.
    await pricing_service.rebuild_variant_prices(db)
    await db.refresh(currency)
    return currency


async def update_currency(
    db: AsyncSession, db_obj: Currency, obj_in: CurrencyUpdate
) -> Currency:
    data = obj_in.model_dump(exclude_unset=True)
    if db_obj.is_base and "rate_to_base" in data and float(data["rate_to_base"]) != 1:
        raise ValueError("The base currency rate is always 1")
    rate_changed = "rate_to_base" in data
    for field, value in data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    if rate_changed:
        # Every price in this currency is derived from the rate, so the rate
        # moving means the prices move with it.
        await pricing_service.rebuild_variant_prices(db)
        await db.refresh(db_obj)
    return db_obj


async def delete_currency(db: AsyncSession, db_obj: Currency) -> None:
    if db_obj.is_base:
        raise InUseError("The base currency cannot be deleted")
    priced = (
        await db.execute(
            select(func.count())
            .select_from(VariantPrice)
            .where(VariantPrice.currency_code == db_obj.code)
        )
    ).scalar_one()
    if priced:
        raise InUseError(f"{priced} price(s) still use {db_obj.code}")
    quoted = (
        await db.execute(
            select(func.count())
            .select_from(Quotation)
            .where(Quotation.currency == db_obj.code)
        )
    ).scalar_one()
    if quoted:
        raise InUseError(f"{quoted} quotation(s) still use {db_obj.code}")
    await db.delete(db_obj)
    await db.commit()
    await pricing_service.rebuild_variant_prices(db)


# --------------------------------------------------------------------------- #
# Customer tiers
# --------------------------------------------------------------------------- #

async def get_customer_tier_by_id(
    db: AsyncSession, tier_id: uuid.UUID
) -> Optional[CustomerTier]:
    return await _get_one(db, select(CustomerTier).where(CustomerTier.id == tier_id))


async def get_customer_tier_by_name(db: AsyncSession, name: str) -> Optional[CustomerTier]:
    return await _get_one(
        db, select(CustomerTier).where(func.lower(CustomerTier.name) == name.lower())
    )


async def list_customer_tiers(db: AsyncSession) -> Sequence[CustomerTier]:
    # Ordered by the ceiling, so Bronze 5 -> Silver 10 -> Gold 15 falls out of
    # the data instead of a hand-maintained sort column.
    result = await db.execute(
        select(CustomerTier).order_by(
            CustomerTier.max_discount_percent, CustomerTier.name
        )
    )
    return result.scalars().all()


async def create_customer_tier(
    db: AsyncSession, obj_in: CustomerTierCreate
) -> CustomerTier:
    tier = CustomerTier(**obj_in.model_dump())
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    # A tier is a column of the price matrix; it arrives already priced.
    await pricing_service.rebuild_variant_prices(db)
    await db.refresh(tier)
    return tier


async def update_customer_tier(
    db: AsyncSession, db_obj: CustomerTier, obj_in: CustomerTierUpdate
) -> CustomerTier:
    data = obj_in.model_dump(exclude_unset=True)
    ceiling_changed = "max_discount_percent" in data
    for field, value in data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    if ceiling_changed:
        # The tier's percentage IS the discount baked into its prices, so
        # raising the ceiling reprices that tier's whole column.
        await pricing_service.rebuild_variant_prices(db)
        await db.refresh(db_obj)
    return db_obj


async def delete_customer_tier(db: AsyncSession, db_obj: CustomerTier) -> None:
    """Refuse while anything still points at the tier.

    Customers and quotations block it; variant prices do not, because they are
    configuration that only exists to serve the tier and cascade with it.
    """
    customers = (
        await db.execute(
            select(func.count()).select_from(Customer).where(Customer.tier_id == db_obj.id)
        )
    ).scalar_one()
    if customers:
        raise InUseError(
            f"{customers} customer(s) are on the {db_obj.name} tier. "
            "Move them to another tier first."
        )
    quotations = (
        await db.execute(
            select(func.count())
            .select_from(Quotation)
            .where(Quotation.customer_tier_id == db_obj.id)
        )
    ).scalar_one()
    if quotations:
        raise InUseError(
            f"{quotations} quotation(s) were priced on the {db_obj.name} tier."
        )
    await db.delete(db_obj)
    await db.commit()
    await pricing_service.rebuild_variant_prices(db)


# --------------------------------------------------------------------------- #
# Categories: free text on the product, with an optional discount ceiling
# --------------------------------------------------------------------------- #

async def list_categories(db: AsyncSession) -> list[str]:
    """Every category name in use, for the product form's combobox."""
    used = (await db.execute(select(Product.category).distinct())).scalars().all()
    limited = (
        (await db.execute(select(CategoryDiscountLimit.category))).scalars().all()
    )
    return sorted({*used, *limited}, key=str.lower)


async def list_category_limits(db: AsyncSession) -> Sequence[CategoryDiscountLimit]:
    result = await db.execute(
        select(CategoryDiscountLimit).order_by(CategoryDiscountLimit.category)
    )
    return result.scalars().all()


async def get_category_limit_by_id(
    db: AsyncSession, limit_id: uuid.UUID
) -> Optional[CategoryDiscountLimit]:
    return await _get_one(
        db, select(CategoryDiscountLimit).where(CategoryDiscountLimit.id == limit_id)
    )


async def get_category_limit(
    db: AsyncSession, category: str
) -> Optional[CategoryDiscountLimit]:
    return await _get_one(
        db,
        select(CategoryDiscountLimit).where(
            func.lower(CategoryDiscountLimit.category) == category.lower()
        ),
    )


async def create_category_limit(
    db: AsyncSession, obj_in: CategoryLimitCreate
) -> CategoryDiscountLimit:
    row = CategoryDiscountLimit(**obj_in.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_category_limit(
    db: AsyncSession, db_obj: CategoryDiscountLimit, obj_in: CategoryLimitUpdate
) -> CategoryDiscountLimit:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def delete_category_limit(
    db: AsyncSession, db_obj: CategoryDiscountLimit
) -> None:
    """Always allowed: removing a ceiling means "this category is uncapped",
    which is a legitimate state, not a broken reference."""
    await db.delete(db_obj)
    await db.commit()


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

def _product_query():
    return select(Product).options(
        selectinload(Product.attributes),
        selectinload(Product.variants).selectinload(ProductVariant.prices),
    )


async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> Optional[Product]:
    return await _get_one(db, _product_query().where(Product.id == product_id))


async def list_products(db: AsyncSession) -> Sequence[Product]:
    result = await db.execute(_product_query().order_by(Product.name))
    return result.scalars().all()


async def list_active_products(db: AsyncSession) -> Sequence[Product]:
    """What a rep may quote. Archived products are absent by construction."""
    result = await db.execute(
        _product_query()
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.name)
    )
    return result.scalars().all()


async def create_product(db: AsyncSession, obj_in: ProductCreate) -> Product:
    data = obj_in.model_dump(exclude={"attributes"})
    product = Product(**data)
    db.add(product)
    await db.flush()

    if obj_in.has_variants and obj_in.attributes:
        await variant_service.replace_attributes(db, product, obj_in.attributes)
        await variant_service.generate_variants(db, product)
    else:
        await variant_service.ensure_default_variant(db, product)

    await db.commit()
    return await get_product_by_id(db, product.id)


async def update_product(
    db: AsyncSession, db_obj: Product, obj_in: ProductUpdate
) -> Product:
    data = obj_in.model_dump(exclude_unset=True)
    attributes = data.pop("attributes", None)
    for field, value in data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.flush()

    if attributes is not None:
        await variant_service.replace_attributes(db, db_obj, obj_in.attributes or [])
    if not db_obj.has_variants:
        await variant_service.ensure_default_variant(db, db_obj)

    await db.commit()
    return await get_product_by_id(db, db_obj.id)


async def set_product_status(
    db: AsyncSession, db_obj: Product, status: ProductStatus
) -> Product:
    db_obj.status = status
    db.add(db_obj)
    await db.commit()
    return await get_product_by_id(db, db_obj.id)


async def delete_product(db: AsyncSession, db_obj: Product) -> None:
    """Hard delete, refused once the product appears on any quotation.

    Archiving is the answer for a product with history; deleting is for one
    created by mistake.
    """
    used = (
        await db.execute(
            select(func.count())
            .select_from(QuotationLine)
            .where(QuotationLine.product_id == db_obj.id)
        )
    ).scalar_one()
    if used:
        raise InUseError(
            f"{db_obj.name} appears on {used} quotation line(s). Archive it instead."
        )
    await db.delete(db_obj)
    await db.commit()


async def get_variant_by_id(
    db: AsyncSession, variant_id: uuid.UUID
) -> Optional[ProductVariant]:
    return await _get_one(
        db,
        select(ProductVariant)
        .options(selectinload(ProductVariant.product))
        .where(ProductVariant.id == variant_id),
    )


# --------------------------------------------------------------------------- #
# Warehouses and stock
# --------------------------------------------------------------------------- #

async def get_warehouse_by_id(
    db: AsyncSession, warehouse_id: uuid.UUID
) -> Optional[Warehouse]:
    return await _get_one(db, select(Warehouse).where(Warehouse.id == warehouse_id))


async def get_warehouse_by_code(db: AsyncSession, code: str) -> Optional[Warehouse]:
    return await _get_one(
        db, select(Warehouse).where(func.lower(Warehouse.code) == code.lower())
    )


async def list_warehouses(db: AsyncSession) -> Sequence[Warehouse]:
    result = await db.execute(
        select(Warehouse).order_by(Warehouse.name)
    )
    return result.scalars().all()


async def list_active_warehouses(db: AsyncSession) -> Sequence[Warehouse]:
    result = await db.execute(
        select(Warehouse)
        .where(Warehouse.is_active.is_(True))
        .order_by(Warehouse.name)
    )
    return result.scalars().all()


async def create_warehouse(db: AsyncSession, obj_in: WarehouseCreate) -> Warehouse:
    warehouse = Warehouse(**obj_in.model_dump())
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def update_warehouse(
    db: AsyncSession, db_obj: Warehouse, obj_in: WarehouseUpdate
) -> Warehouse:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def delete_warehouse(db: AsyncSession, db_obj: Warehouse) -> None:
    stocked = (
        await db.execute(
            select(func.count())
            .select_from(StockItem)
            .where(StockItem.warehouse_id == db_obj.id, StockItem.quantity_on_hand > 0)
        )
    ).scalar_one()
    if stocked:
        raise InUseError(
            f"{db_obj.name} still holds stock for {stocked} SKU(s). Empty it first."
        )
    quoted = (
        await db.execute(
            select(func.count())
            .select_from(QuotationLine)
            .where(QuotationLine.warehouse_id == db_obj.id)
        )
    ).scalar_one()
    if quoted:
        raise InUseError(
            f"{quoted} quotation line(s) were allocated from {db_obj.name}."
        )
    await db.delete(db_obj)
    await db.commit()


def _stock_query():
    return select(StockItem).options(
        selectinload(StockItem.warehouse),
        selectinload(StockItem.variant).selectinload(ProductVariant.product),
    )


async def get_stock_item(
    db: AsyncSession, warehouse_id: uuid.UUID, variant_id: uuid.UUID
) -> Optional[StockItem]:
    return await _get_one(
        db,
        _stock_query().where(
            StockItem.warehouse_id == warehouse_id, StockItem.variant_id == variant_id
        ),
    )


async def list_stock_items(
    db: AsyncSession,
    *,
    warehouse_id: Optional[uuid.UUID] = None,
    variant_id: Optional[uuid.UUID] = None,
) -> Sequence[StockItem]:
    stmt = _stock_query()
    if warehouse_id:
        stmt = stmt.where(StockItem.warehouse_id == warehouse_id)
    if variant_id:
        stmt = stmt.where(StockItem.variant_id == variant_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def list_stock_for_variant(
    db: AsyncSession, variant_id: uuid.UUID
) -> Sequence[StockItem]:
    """Warehouses holding a SKU, richest first - the order the split planner
    and the quotation builder both want."""
    result = await db.execute(
        _stock_query()
        .where(StockItem.variant_id == variant_id)
        .order_by(StockItem.quantity_available.desc())
    )
    return result.scalars().all()


async def upsert_stock_item(db: AsyncSession, obj_in: StockUpsert) -> StockItem:
    item = await get_stock_item(db, obj_in.warehouse_id, obj_in.variant_id)
    if item is None:
        item = StockItem(**obj_in.model_dump())
        db.add(item)
    else:
        for field, value in obj_in.model_dump().items():
            setattr(item, field, value)
        db.add(item)
    await db.commit()
    return await get_stock_item(db, obj_in.warehouse_id, obj_in.variant_id)


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #

async def get_customer_by_id(
    db: AsyncSession, customer_id: uuid.UUID
) -> Optional[Customer]:
    return await _get_one(
        db,
        select(Customer)
        .options(selectinload(Customer.tier))
        .where(Customer.id == customer_id),
    )


async def list_customers(db: AsyncSession) -> Sequence[Customer]:
    result = await db.execute(
        select(Customer).options(selectinload(Customer.tier)).order_by(Customer.name)
    )
    return result.scalars().all()


async def create_customer(db: AsyncSession, obj_in: CustomerCreate) -> Customer:
    customer = Customer(**obj_in.model_dump())
    db.add(customer)
    await db.commit()
    return await get_customer_by_id(db, customer.id)


async def update_customer(
    db: AsyncSession, db_obj: Customer, obj_in: CustomerUpdate
) -> Customer:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_customer_by_id(db, db_obj.id)
