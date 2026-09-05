"""Read-only pickers for the rep workspace.

Everything here is scoped to what a rep may actually quote: archived products
never appear, and prices come back already resolved for the customer's tier.
"""

from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.api.endpoints.serializers import serialize_product, serialize_stock
from app.core import cache
from app.core.cache import cached_json
from app.models.user import Role
from app.schemas.catalog import CurrencyRead, ProductRead, StockRead
from app.schemas.customer import CustomerRead, CustomerTierRead
from app.services import catalog_service, pricing_service
from app.services.catalog_service import list_active_products, list_customers

router = APIRouter(
    dependencies=[Depends(require_roles(Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER))]
)


@router.get("/customers", response_model=List[CustomerRead])
async def read_customers(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await list_customers(db))


# The four routes below are read on every quotation screen and written only by
# an admin editing the catalog, which is exactly the shape a cache is for. All
# four share the catalog namespace, so any catalog write invalidates the set in
# one INCR - there is no key list to keep in step.


@router.get("/customer-tiers", response_model=List[CustomerTierRead])
async def read_customer_tiers(db: AsyncSession = Depends(get_db)) -> Any:
    async def load() -> list[dict]:
        return [
            CustomerTierRead.model_validate(tier).model_dump()
            for tier in await catalog_service.list_customer_tiers(db)
        ]

    return await cached_json(cache.NS_CATALOG, "tiers", cache.TTL_CATALOG, load)


@router.get("/currencies", response_model=List[CurrencyRead])
async def read_currencies(db: AsyncSession = Depends(get_db)) -> Any:
    async def load() -> list[dict]:
        return [
            CurrencyRead.model_validate(currency).model_dump()
            for currency in await pricing_service.list_currencies(db, active_only=True)
        ]

    return await cached_json(cache.NS_CATALOG, "currencies", cache.TTL_CATALOG, load)


@router.get("/products", response_model=List[ProductRead])
async def read_products(db: AsyncSession = Depends(get_db)) -> Any:
    """Only active products: an archived one can never reach a quotation.

    The heaviest read in the app - every product with every variant, price and
    stock row - and the one the product picker opens with.
    """

    async def load() -> list[dict]:
        return [
            ProductRead.model_validate(await serialize_product(db, product)).model_dump()
            for product in await list_active_products(db)
        ]

    return await cached_json(
        cache.NS_CATALOG, "active-products", cache.TTL_CATALOG, load
    )


@router.get("/variants/{variant_id}/stock", response_model=List[StockRead])
async def read_variant_stock(
    variant_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    items = await catalog_service.list_stock_for_variant(db, variant_id)
    return [serialize_stock(item) for item in items]


@router.get("/variants/{variant_id}/price")
async def read_variant_price(
    variant_id: uuid.UUID,
    tier_id: uuid.UUID,
    currency: str = Query(default="USD", min_length=3, max_length=3),
    db: AsyncSession = Depends(get_db),
) -> Any:
    price = await pricing_service.resolve_variant_price(
        db, variant_id=variant_id, tier_id=tier_id, currency_code=currency
    )
    return {"unit_price": float(price) if price is not None else None}


@router.get("/warehouses")
async def read_warehouses(db: AsyncSession = Depends(get_db)) -> Any:
    async def load() -> list[dict]:
        return [
            {"id": str(w.id), "name": w.name, "code": w.code}
            for w in await catalog_service.list_active_warehouses(db)
        ]

    return await cached_json(cache.NS_CATALOG, "warehouses", cache.TTL_CATALOG, load)
