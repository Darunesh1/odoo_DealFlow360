from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.user import Role
from app.schemas.catalog import PriceListItemRead, PriceListRead, ProductRead
from app.schemas.customer import CustomerRead, CustomerTierRead
from app.services.catalog_service import list_customers, list_price_lists, list_products

router = APIRouter(dependencies=[Depends(require_roles(Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER))])


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


@router.get("/customers", response_model=list[CustomerRead])
async def read_customers(db: AsyncSession = Depends(get_db)) -> Any:
    return [CustomerRead.model_validate(item) for item in await list_customers(db)]


@router.get("/products", response_model=list[ProductRead])
async def read_products(db: AsyncSession = Depends(get_db)) -> Any:
    return [ProductRead.model_validate(item) for item in await list_products(db)]


@router.get("/price-lists", response_model=list[PriceListRead])
async def read_price_lists(db: AsyncSession = Depends(get_db)) -> Any:
    return [_serialize_price_list(item) for item in await list_price_lists(db)]
