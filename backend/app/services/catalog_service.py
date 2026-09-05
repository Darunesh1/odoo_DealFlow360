from typing import Optional, Sequence
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import (
    PriceList,
    PriceListItem,
    Product,
    ProductCategory,
)
from app.models.customer import Customer, CustomerTier
from app.models.inventory import StockItem, Warehouse
from app.schemas.catalog import (
    PriceListCreate,
    PriceListItemUpsert,
    PriceListUpdate,
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCreate,
    ProductUpdate,
    StockUpsert,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.schemas.customer import CustomerCreate, CustomerTierCreate, CustomerTierUpdate, CustomerUpdate


async def _get_one(db: AsyncSession, stmt):
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_product_category_by_id(db: AsyncSession, category_id: uuid.UUID) -> Optional[ProductCategory]:
    return await _get_one(db, select(ProductCategory).where(ProductCategory.id == category_id))


async def get_product_category_by_code(db: AsyncSession, code: str) -> Optional[ProductCategory]:
    return await _get_one(db, select(ProductCategory).where(func.lower(ProductCategory.code) == code.lower()))


async def list_product_categories(db: AsyncSession) -> Sequence[ProductCategory]:
    result = await db.execute(select(ProductCategory).order_by(ProductCategory.sort_order, ProductCategory.name))
    return result.scalars().all()


async def create_product_category(db: AsyncSession, obj_in: ProductCategoryCreate) -> ProductCategory:
    category = ProductCategory(**obj_in.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_product_category(db: AsyncSession, db_obj: ProductCategory, obj_in: ProductCategoryUpdate) -> ProductCategory:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> Optional[Product]:
    stmt = (
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.id == product_id)
    )
    return await _get_one(db, stmt)


async def get_product_by_sku(db: AsyncSession, sku: str) -> Optional[Product]:
    stmt = select(Product).where(func.lower(Product.sku) == sku.lower())
    return await _get_one(db, stmt)


async def list_products(db: AsyncSession) -> Sequence[Product]:
    stmt = (
        select(Product)
        .options(selectinload(Product.category))
        .order_by(Product.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_product(db: AsyncSession, obj_in: ProductCreate) -> Product:
    product = Product(**obj_in.model_dump())
    db.add(product)
    await db.commit()
    return await get_product_by_id(db, product.id)  # type: ignore[return-value]


async def update_product(db: AsyncSession, db_obj: Product, obj_in: ProductUpdate) -> Product:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_product_by_id(db, db_obj.id)  # type: ignore[return-value]


async def get_price_list_by_id(db: AsyncSession, price_list_id: uuid.UUID) -> Optional[PriceList]:
    stmt = (
        select(PriceList)
        .options(selectinload(PriceList.items).selectinload(PriceListItem.product), selectinload(PriceList.tier))
        .where(PriceList.id == price_list_id)
    )
    return await _get_one(db, stmt)


async def list_price_lists(db: AsyncSession) -> Sequence[PriceList]:
    stmt = (
        select(PriceList)
        .options(selectinload(PriceList.items).selectinload(PriceListItem.product), selectinload(PriceList.tier))
        .order_by(PriceList.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_price_list(db: AsyncSession, obj_in: PriceListCreate) -> PriceList:
    price_list = PriceList(**obj_in.model_dump())
    db.add(price_list)
    await db.commit()
    return await get_price_list_by_id(db, price_list.id)  # type: ignore[return-value]


async def update_price_list(db: AsyncSession, db_obj: PriceList, obj_in: PriceListUpdate) -> PriceList:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_price_list_by_id(db, db_obj.id)  # type: ignore[return-value]


async def get_price_list_item(db: AsyncSession, price_list_id: uuid.UUID, product_id: uuid.UUID) -> Optional[PriceListItem]:
    stmt = (
        select(PriceListItem)
        .options(selectinload(PriceListItem.product))
        .where(
            and_(PriceListItem.price_list_id == price_list_id, PriceListItem.product_id == product_id)
        )
    )
    return await _get_one(db, stmt)


async def list_price_list_items(db: AsyncSession, price_list_id: uuid.UUID) -> Sequence[PriceListItem]:
    stmt = (
        select(PriceListItem)
        .options(selectinload(PriceListItem.product))
        .where(PriceListItem.price_list_id == price_list_id)
        .order_by(PriceListItem.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def upsert_price_list_item(db: AsyncSession, price_list_id: uuid.UUID, obj_in: PriceListItemUpsert) -> PriceListItem:
    item = await get_price_list_item(db, price_list_id, obj_in.product_id)
    if item is None:
        item = PriceListItem(price_list_id=price_list_id, **obj_in.model_dump())
        db.add(item)
    else:
        item.unit_price = obj_in.unit_price
    await db.commit()
    return await _get_one(
        db,
        select(PriceListItem)
        .options(selectinload(PriceListItem.product))
        .where(PriceListItem.id == item.id),
    )  # type: ignore[return-value]


async def get_warehouse_by_id(db: AsyncSession, warehouse_id: uuid.UUID) -> Optional[Warehouse]:
    return await _get_one(db, select(Warehouse).where(Warehouse.id == warehouse_id))


async def get_warehouse_by_code(db: AsyncSession, code: str) -> Optional[Warehouse]:
    return await _get_one(db, select(Warehouse).where(func.lower(Warehouse.code) == code.lower()))


async def list_warehouses(db: AsyncSession) -> Sequence[Warehouse]:
    result = await db.execute(select(Warehouse).order_by(Warehouse.split_priority, Warehouse.name))
    return result.scalars().all()


async def create_warehouse(db: AsyncSession, obj_in: WarehouseCreate) -> Warehouse:
    warehouse = Warehouse(**obj_in.model_dump())
    db.add(warehouse)
    await db.commit()
    return await get_warehouse_by_id(db, warehouse.id)  # type: ignore[return-value]


async def update_warehouse(db: AsyncSession, db_obj: Warehouse, obj_in: WarehouseUpdate) -> Warehouse:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_warehouse_by_id(db, db_obj.id)  # type: ignore[return-value]


async def get_stock_item(db: AsyncSession, warehouse_id: uuid.UUID, product_id: uuid.UUID) -> Optional[StockItem]:
    stmt = (
        select(StockItem)
        .options(selectinload(StockItem.warehouse), selectinload(StockItem.product))
        .where(
        and_(StockItem.warehouse_id == warehouse_id, StockItem.product_id == product_id)
        )
    )
    return await _get_one(db, stmt)


async def list_stock_items(
    db: AsyncSession,
    warehouse_id: Optional[uuid.UUID] = None,
    product_id: Optional[uuid.UUID] = None,
) -> Sequence[StockItem]:
    stmt = (
        select(StockItem)
        .options(selectinload(StockItem.warehouse), selectinload(StockItem.product))
        .order_by(StockItem.created_at.desc())
    )
    if warehouse_id:
        stmt = stmt.where(StockItem.warehouse_id == warehouse_id)
    if product_id:
        stmt = stmt.where(StockItem.product_id == product_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def upsert_stock_item(db: AsyncSession, obj_in: StockUpsert) -> StockItem:
    stock = await get_stock_item(db, obj_in.warehouse_id, obj_in.product_id)
    if stock is None:
        stock = StockItem(**obj_in.model_dump())
        db.add(stock)
    else:
        for field, value in obj_in.model_dump(exclude={"warehouse_id", "product_id"}).items():
            setattr(stock, field, value)
    await db.commit()
    return await get_stock_item(db, stock.warehouse_id, stock.product_id)  # type: ignore[return-value]


async def get_customer_tier_by_id(db: AsyncSession, tier_id: uuid.UUID) -> Optional[CustomerTier]:
    return await _get_one(db, select(CustomerTier).where(CustomerTier.id == tier_id))


async def get_customer_tier_by_code(db: AsyncSession, code: str) -> Optional[CustomerTier]:
    return await _get_one(db, select(CustomerTier).where(func.lower(CustomerTier.code) == code.lower()))


async def list_customer_tiers(db: AsyncSession) -> Sequence[CustomerTier]:
    result = await db.execute(select(CustomerTier).order_by(CustomerTier.sort_order, CustomerTier.name))
    return result.scalars().all()


async def create_customer_tier(db: AsyncSession, obj_in: CustomerTierCreate) -> CustomerTier:
    tier = CustomerTier(**obj_in.model_dump())
    db.add(tier)
    await db.commit()
    return await get_customer_tier_by_id(db, tier.id)  # type: ignore[return-value]


async def update_customer_tier(db: AsyncSession, db_obj: CustomerTier, obj_in: CustomerTierUpdate) -> CustomerTier:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_customer_tier_by_id(db, db_obj.id)  # type: ignore[return-value]


async def get_customer_by_id(db: AsyncSession, customer_id: uuid.UUID) -> Optional[Customer]:
    stmt = (
        select(Customer)
        .options(selectinload(Customer.tier), selectinload(Customer.default_price_list))
        .where(Customer.id == customer_id)
    )
    return await _get_one(db, stmt)


async def list_customers(db: AsyncSession) -> Sequence[Customer]:
    stmt = (
        select(Customer)
        .options(selectinload(Customer.tier), selectinload(Customer.default_price_list))
        .order_by(Customer.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_customer(db: AsyncSession, obj_in: CustomerCreate) -> Customer:
    customer = Customer(**obj_in.model_dump())
    db.add(customer)
    await db.commit()
    return await get_customer_by_id(db, customer.id)  # type: ignore[return-value]


async def update_customer(db: AsyncSession, db_obj: Customer, obj_in: CustomerUpdate) -> Customer:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    return await get_customer_by_id(db, db_obj.id)  # type: ignore[return-value]


def resolve_price_list_unit_price(product: Product, price_list: Optional[PriceList]) -> float:
    if not price_list:
        return float(product.list_price)
    for item in price_list.items:
        if item.product_id == product.id:
            return float(item.unit_price)
    return float(product.list_price * (1 + (price_list.adjustment_percent / 100)))
