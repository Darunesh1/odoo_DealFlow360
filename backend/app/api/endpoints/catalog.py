"""Admin Management: currencies, tiers, category ceilings, products, variants,
warehouses, stock and customers.

The router carries `require_admin` once, so every route added here is admin-only
by construction.
"""

from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.api.endpoints.serializers import serialize_product
from app.models.catalog import (
    CategoryDiscountLimit,
    Product,
    ProductStatus,
    ProductVariant,
    VariantPrice,
)
from app.models.customer import CustomerTier
from app.schemas.catalog import (
    CatalogStats,
    CategoryLimitCreate,
    CategoryLimitRead,
    CategoryLimitUpdate,
    CurrencyCreate,
    CurrencyRead,
    CurrencyUpdate,
    PriceMatrixRow,
    ProductCreate,
    ProductListRow,
    ProductRead,
    ProductUpdate,
    ProductVariantRead,
    StockRead,
    StockUpsert,
    VariantMatrixSave,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)
from app.schemas.approval import ApprovalRuleRead
from app.schemas.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerTierCreate,
    CustomerTierRead,
    CustomerTierUpdate,
    CustomerUpdate,
)
from app.services import catalog_service, pricing_service, variant_service
from app.services.catalog_service import InUseError

router = APIRouter(dependencies=[Depends(require_admin)])


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Currencies
# --------------------------------------------------------------------------- #

@router.get("/currencies", response_model=List[CurrencyRead])
async def read_currencies(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await catalog_service.list_currencies(db))


@router.post("/currencies", response_model=CurrencyRead, status_code=status.HTTP_201_CREATED)
async def create_currency(body: CurrencyCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await catalog_service.get_currency(db, body.code):
        raise _conflict(ValueError(f"{body.code.upper()} already exists"))
    return await catalog_service.create_currency(db, body)


@router.patch("/currencies/{code}", response_model=CurrencyRead)
async def patch_currency(
    code: str, body: CurrencyUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    currency = await catalog_service.get_currency(db, code)
    if not currency:
        raise _not_found("Currency")
    try:
        return await catalog_service.update_currency(db, currency, body)
    except ValueError as exc:
        raise _bad_request(exc)


@router.delete("/currencies/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_currency(code: str, db: AsyncSession = Depends(get_db)) -> None:
    currency = await catalog_service.get_currency(db, code)
    if not currency:
        raise _not_found("Currency")
    try:
        await catalog_service.delete_currency(db, currency)
    except InUseError as exc:
        raise _conflict(exc)


# --------------------------------------------------------------------------- #
# Customer tiers
# --------------------------------------------------------------------------- #

@router.get("/customer-tiers", response_model=List[CustomerTierRead])
async def read_customer_tiers(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await catalog_service.list_customer_tiers(db))


@router.post(
    "/customer-tiers", response_model=CustomerTierRead, status_code=status.HTTP_201_CREATED
)
async def create_customer_tier(
    body: CustomerTierCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    if await catalog_service.get_customer_tier_by_name(db, body.name):
        raise _conflict(ValueError(f"A tier named {body.name} already exists"))
    return await catalog_service.create_customer_tier(db, body)


@router.patch("/customer-tiers/{tier_id}", response_model=CustomerTierRead)
async def patch_customer_tier(
    tier_id: uuid.UUID, body: CustomerTierUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    tier = await catalog_service.get_customer_tier_by_id(db, tier_id)
    if not tier:
        raise _not_found("Customer tier")
    if body.name:
        clash = await catalog_service.get_customer_tier_by_name(db, body.name)
        if clash and clash.id != tier.id:
            raise _conflict(ValueError(f"A tier named {body.name} already exists"))
    return await catalog_service.update_customer_tier(db, tier, body)


@router.delete("/customer-tiers/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_customer_tier(
    tier_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    tier = await catalog_service.get_customer_tier_by_id(db, tier_id)
    if not tier:
        raise _not_found("Customer tier")
    try:
        await catalog_service.delete_customer_tier(db, tier)
    except InUseError as exc:
        raise _conflict(exc)


# --------------------------------------------------------------------------- #
# Categories and their ceilings
# --------------------------------------------------------------------------- #

@router.get("/category-limits", response_model=List[CategoryLimitRead])
async def read_category_limits(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await catalog_service.list_category_limits(db))


@router.post(
    "/category-limits", response_model=CategoryLimitRead, status_code=status.HTTP_201_CREATED
)
async def create_category_limit(
    body: CategoryLimitCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    if await catalog_service.get_category_limit(db, body.category):
        raise _conflict(ValueError(f"{body.category} already has a ceiling"))
    return await catalog_service.create_category_limit(db, body)


@router.patch("/category-limits/{limit_id}", response_model=CategoryLimitRead)
async def patch_category_limit(
    limit_id: uuid.UUID, body: CategoryLimitUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    row = await catalog_service.get_category_limit_by_id(db, limit_id)
    if not row:
        raise _not_found("Category ceiling")
    return await catalog_service.update_category_limit(db, row, body)


@router.delete("/category-limits/{limit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_category_limit(
    limit_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    row = await catalog_service.get_category_limit_by_id(db, limit_id)
    if not row:
        raise _not_found("Category ceiling")
    await catalog_service.delete_category_limit(db, row)


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        product = await catalog_service.create_product(db, body)
    except ValueError as exc:
        raise _bad_request(exc)
    return await serialize_product(db, product)


@router.patch("/products/{product_id}", response_model=ProductRead)
async def patch_product(
    product_id: uuid.UUID, body: ProductUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    try:
        updated = await catalog_service.update_product(db, product, body)
    except ValueError as exc:
        raise _bad_request(exc)
    return await serialize_product(db, updated)


@router.post("/products/{product_id}/archive", response_model=ProductRead)
async def archive_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    updated = await catalog_service.set_product_status(db, product, ProductStatus.ARCHIVED)
    return await serialize_product(db, updated)


@router.post("/products/{product_id}/restore", response_model=ProductRead)
async def restore_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    updated = await catalog_service.set_product_status(db, product, ProductStatus.ACTIVE)
    return await serialize_product(db, updated)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    try:
        await catalog_service.delete_product(db, product)
    except InUseError as exc:
        raise _conflict(exc)


@router.post("/products/{product_id}/generate-variants", response_model=ProductRead)
async def generate_product_variants(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    await variant_service.generate_variants(db, product)
    await db.commit()
    return await serialize_product(db, await catalog_service.get_product_by_id(db, product_id))


@router.put("/products/{product_id}/variants", response_model=ProductRead)
async def save_product_variants(
    product_id: uuid.UUID, body: VariantMatrixSave, db: AsyncSession = Depends(get_db)
) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise _not_found("Product")
    try:
        await variant_service.save_variant_matrix(db, product, body.rows)
    except ValueError as exc:
        raise _bad_request(exc)
    return await serialize_product(db, await catalog_service.get_product_by_id(db, product_id))


@router.get("/price-matrix", response_model=List[PriceMatrixRow])
async def read_price_matrix(db: AsyncSession = Depends(get_db)) -> Any:
    """The read-only "one place" view behind the Price Lists tab."""
    stmt = (
        select(
            Product.id,
            Product.name,
            ProductVariant.id,
            ProductVariant.name,
            ProductVariant.sku,
            CustomerTier.name,
            CustomerTier.max_discount_percent,
            VariantPrice.currency_code,
            VariantPrice.unit_price,
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(VariantPrice, VariantPrice.variant_id == ProductVariant.id)
        .join(CustomerTier, CustomerTier.id == VariantPrice.tier_id)
        .order_by(
            Product.name,
            ProductVariant.name,
            CustomerTier.max_discount_percent,
            VariantPrice.currency_code,
        )
    )
    return [
        PriceMatrixRow(
            product_id=row[0],
            product_name=row[1],
            variant_id=row[2],
            variant_name=row[3],
            sku=row[4],
            tier_name=row[5],
            max_discount_percent=float(row[6]),
            currency_code=row[7],
            unit_price=float(row[8]),
            # The floor, not a second price: what the list allows a rep on this
            # tier to sell it down to.
            floor_price=round(float(row[8]) * (1 - float(row[6]) / 100), 2),
        )
        for row in (await db.execute(stmt)).all()
    ]


# --------------------------------------------------------------------------- #
# Warehouses and stock
# --------------------------------------------------------------------------- #

@router.get("/customers", response_model=List[CustomerRead])
async def read_customers(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await catalog_service.list_customers(db))


@router.get("/customers/{customer_id}", response_model=CustomerRead)
async def read_customer(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    customer = await catalog_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise _not_found("Customer")
    return customer


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if not await catalog_service.get_customer_tier_by_id(db, body.tier_id):
        raise _not_found("Customer tier")
    return await catalog_service.create_customer(db, body)


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
async def patch_customer(
    customer_id: uuid.UUID, body: CustomerUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    customer = await catalog_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise _not_found("Customer")
    return await catalog_service.update_customer(db, customer, body)


# --------------------------------------------------------------------------- #
# Approval chain (read-only here; editing is the next phase's work)
# --------------------------------------------------------------------------- #

@router.get("/approval-rules", response_model=List[ApprovalRuleRead])
async def read_approval_rules(db: AsyncSession = Depends(get_db)) -> Any:
    from app.models.approval import ApprovalRule

    rows = (
        await db.execute(select(ApprovalRule).order_by(ApprovalRule.sort_order))
    ).scalars().all()
    return list(rows)


@router.get("/subscription-plans", response_model=List[ProductRead])
async def read_subscription_plans(db: AsyncSession = Depends(get_db)) -> Any:
    """Every product that bills on a cycle - the Subscription Plans tab."""
    products = [
        product
        for product in await catalog_service.list_products(db)
        if product.is_subscription
    ]
    return [await serialize_product(db, product) for product in products]
