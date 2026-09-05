from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, get_db
from app.models.catalog import PriceListItem
from app.models.customer import CustomerTier
from app.schemas.catalog import (
    PriceListCreate,
    PriceListItemRead,
    PriceListItemUpsert,
    PriceListRead,
    PriceListUpdate,
    ProductCategoryCreate,
    ProductCategoryRead,
    ProductCategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockRead,
    StockUpsert,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerTierCreate, CustomerTierRead, CustomerTierUpdate, CustomerUpdate
from app.services.catalog_service import (
    create_customer,
    create_customer_tier,
    create_price_list,
    create_product,
    create_product_category,
    create_warehouse,
    get_customer_by_id,
    get_customer_tier_by_id,
    get_price_list_by_id,
    get_price_list_item,
    get_product_by_id,
    get_product_by_sku,
    get_product_category_by_code,
    get_product_category_by_id,
    get_stock_item,
    get_warehouse_by_code,
    get_warehouse_by_id,
    list_customer_tiers,
    list_customers,
    list_price_list_items,
    list_price_lists,
    list_products,
    list_product_categories,
    list_stock_items,
    list_warehouses,
    resolve_price_list_unit_price,
    update_customer,
    update_customer_tier,
    update_price_list,
    update_product,
    update_product_category,
    update_warehouse,
    upsert_price_list_item,
    upsert_stock_item,
)

router = APIRouter(dependencies=[Depends(require_admin)])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _serialize_price_list(item) -> PriceListRead:
    return PriceListRead(
        id=item.id,
        name=item.name,
        tier_id=item.tier_id,
        currency=item.currency,
        adjustment_percent=float(item.adjustment_percent),
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
        tier=CustomerTierRead.model_validate(item.tier) if item.tier else None,
        items=[
            PriceListItemRead(
                id=price_item.id,
                price_list_id=price_item.price_list_id,
                product_id=price_item.product_id,
                unit_price=float(price_item.unit_price),
                created_at=price_item.created_at,
                updated_at=price_item.updated_at,
                product_name=price_item.product.name if price_item.product else "",
                sku=price_item.product.sku if price_item.product else "",
            )
            for price_item in item.items
        ],
    )


@router.get("/customer-tiers", response_model=list[CustomerTierRead])
async def read_customer_tiers(db: AsyncSession = Depends(get_db)) -> Any:
    return [CustomerTierRead.model_validate(item) for item in await list_customer_tiers(db)]


@router.post("/customer-tiers", response_model=CustomerTierRead, status_code=status.HTTP_201_CREATED)
async def create_customer_tier_api(body: CustomerTierCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await get_customer_tier_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer tier code already exists.")
    return await create_customer_tier(db, body)


@router.patch("/customer-tiers/{tier_id}", response_model=CustomerTierRead)
async def update_customer_tier_api(
    tier_id: uuid.UUID,
    body: CustomerTierUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    tier = await get_customer_tier_by_id(db, tier_id)
    if not tier:
        raise _not_found("Customer tier not found")
    if body.code and body.code.lower() != tier.code.lower() and await get_customer_tier_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer tier code already exists.")
    return await update_customer_tier(db, tier, body)


@router.get("/product-categories", response_model=list[ProductCategoryRead])
async def read_product_categories(db: AsyncSession = Depends(get_db)) -> Any:
    return [ProductCategoryRead.model_validate(item) for item in await list_product_categories(db)]


@router.post("/product-categories", response_model=ProductCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_product_category_api(body: ProductCategoryCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await get_product_category_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product category code already exists.")
    return await create_product_category(db, body)


@router.patch("/product-categories/{category_id}", response_model=ProductCategoryRead)
async def update_product_category_api(
    category_id: uuid.UUID,
    body: ProductCategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    category = await get_product_category_by_id(db, category_id)
    if not category:
        raise _not_found("Product category not found")
    if body.code and body.code.lower() != category.code.lower() and await get_product_category_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product category code already exists.")
    return await update_product_category(db, category, body)


@router.get("/products", response_model=list[ProductRead])
async def read_products(db: AsyncSession = Depends(get_db)) -> Any:
    return [ProductRead.model_validate(item) for item in await list_products(db)]


@router.get("/products/{product_id}", response_model=ProductRead)
async def read_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    product = await get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product not found")
    return product


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product_api(body: ProductCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await get_product_by_sku(db, body.sku):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product SKU already exists.")
    return await create_product(db, body)


@router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product_api(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    product = await get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product not found")
    if body.sku and body.sku.lower() != product.sku.lower() and await get_product_by_sku(db, body.sku):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product SKU already exists.")
    return await update_product(db, product, body)


@router.get("/price-lists", response_model=list[PriceListRead])
async def read_price_lists(db: AsyncSession = Depends(get_db)) -> Any:
    return [_serialize_price_list(item) for item in await list_price_lists(db)]


@router.post("/price-lists", response_model=PriceListRead, status_code=status.HTTP_201_CREATED)
async def create_price_list_api(body: PriceListCreate, db: AsyncSession = Depends(get_db)) -> Any:
    return _serialize_price_list(await create_price_list(db, body))


@router.patch("/price-lists/{price_list_id}", response_model=PriceListRead)
async def update_price_list_api(
    price_list_id: uuid.UUID,
    body: PriceListUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    price_list = await get_price_list_by_id(db, price_list_id)
    if not price_list:
        raise _not_found("Price list not found")
    return _serialize_price_list(await update_price_list(db, price_list, body))


@router.get("/price-lists/{price_list_id}/items", response_model=list[PriceListItemRead])
async def read_price_list_items(price_list_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    items = await list_price_list_items(db, price_list_id)
    return [
        PriceListItemRead(
            id=item.id,
            price_list_id=item.price_list_id,
            product_id=item.product_id,
            unit_price=float(item.unit_price),
            created_at=item.created_at,
            updated_at=item.updated_at,
            product_name=item.product.name if item.product else "",
            sku=item.product.sku if item.product else "",
        )
        for item in items
    ]


@router.post("/price-lists/{price_list_id}/items", response_model=PriceListItemRead, status_code=status.HTTP_201_CREATED)
async def upsert_price_list_item_api(
    price_list_id: uuid.UUID,
    body: PriceListItemUpsert,
    db: AsyncSession = Depends(get_db),
) -> Any:
    price_list = await get_price_list_by_id(db, price_list_id)
    if not price_list:
        raise _not_found("Price list not found")
    item = await upsert_price_list_item(db, price_list_id, body)
    return PriceListItemRead(
        id=item.id,
        price_list_id=item.price_list_id,
        product_id=item.product_id,
        unit_price=float(item.unit_price),
        created_at=item.created_at,
        updated_at=item.updated_at,
        product_name=item.product.name if item.product else "",
        sku=item.product.sku if item.product else "",
    )


@router.get("/warehouses", response_model=list[WarehouseRead])
async def read_warehouses(db: AsyncSession = Depends(get_db)) -> Any:
    return [WarehouseRead.model_validate(item) for item in await list_warehouses(db)]


@router.post("/warehouses", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
async def create_warehouse_api(body: WarehouseCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await get_warehouse_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Warehouse code already exists.")
    return await create_warehouse(db, body)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseRead)
async def update_warehouse_api(
    warehouse_id: uuid.UUID,
    body: WarehouseUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    warehouse = await get_warehouse_by_id(db, warehouse_id)
    if not warehouse:
        raise _not_found("Warehouse not found")
    if body.code and body.code.lower() != warehouse.code.lower() and await get_warehouse_by_code(db, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Warehouse code already exists.")
    return await update_warehouse(db, warehouse, body)


@router.get("/stock", response_model=list[StockRead])
async def read_stock(
    warehouse_id: Optional[uuid.UUID] = Query(default=None),
    product_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stock_items = await list_stock_items(db, warehouse_id=warehouse_id, product_id=product_id)
    return [
        StockRead(
            id=item.id,
            warehouse_id=item.warehouse_id,
            product_id=item.product_id,
            quantity_on_hand=item.quantity_on_hand,
            quantity_reserved=item.quantity_reserved,
            reorder_point=item.reorder_point,
            reorder_quantity=item.reorder_quantity,
            lead_time_days=item.lead_time_days,
            bin_location=item.bin_location,
            created_at=item.created_at,
            updated_at=item.updated_at,
            quantity_available=item.quantity_available,
            warehouse_name=item.warehouse.name if item.warehouse else "",
            warehouse_code=item.warehouse.code if item.warehouse else "",
            product_name=item.product.name if item.product else "",
            sku=item.product.sku if item.product else "",
        )
        for item in stock_items
    ]


@router.post("/stock", response_model=StockRead, status_code=status.HTTP_201_CREATED)
async def upsert_stock_api(body: StockUpsert, db: AsyncSession = Depends(get_db)) -> Any:
    stock = await upsert_stock_item(db, body)
    return StockRead(
        id=stock.id,
        warehouse_id=stock.warehouse_id,
        product_id=stock.product_id,
        quantity_on_hand=stock.quantity_on_hand,
        quantity_reserved=stock.quantity_reserved,
        reorder_point=stock.reorder_point,
        reorder_quantity=stock.reorder_quantity,
        lead_time_days=stock.lead_time_days,
        bin_location=stock.bin_location,
        created_at=stock.created_at,
        updated_at=stock.updated_at,
        quantity_available=stock.quantity_available,
        warehouse_name=stock.warehouse.name if stock.warehouse else "",
        warehouse_code=stock.warehouse.code if stock.warehouse else "",
        product_name=stock.product.name if stock.product else "",
        sku=stock.product.sku if stock.product else "",
    )


@router.get("/customers", response_model=list[CustomerRead])
async def read_customers(db: AsyncSession = Depends(get_db)) -> Any:
    return [CustomerRead.model_validate(item) for item in await list_customers(db)]


@router.get("/customers/{customer_id}", response_model=CustomerRead)
async def read_customer(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    customer = await get_customer_by_id(db, customer_id)
    if not customer:
        raise _not_found("Customer not found")
    return customer


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer_api(body: CustomerCreate, db: AsyncSession = Depends(get_db)) -> Any:
    return await create_customer(db, body)


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
async def update_customer_api(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    customer = await get_customer_by_id(db, customer_id)
    if not customer:
        raise _not_found("Customer not found")
    return await update_customer(db, customer, body)
