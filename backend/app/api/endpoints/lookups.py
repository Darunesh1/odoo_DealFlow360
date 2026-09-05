from typing import Any
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.user import Role
from app.schemas.catalog import PriceListItemRead, PriceListRead, ProductRead, StockRead
from app.schemas.customer import CustomerRead, CustomerTierRead
from app.services.catalog_service import (
    list_active_products,
    list_customers,
    list_price_lists,
    list_stock_for_product,
)

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
    return [ProductRead.model_validate(item) for item in await list_active_products(db)]


@router.get("/products/{product_id}/stock", response_model=list[StockRead])
async def read_product_stock(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    stock_items = await list_stock_for_product(db, product_id)
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


@router.get("/price-lists", response_model=list[PriceListRead])
async def read_price_lists(db: AsyncSession = Depends(get_db)) -> Any:
    return [_serialize_price_list(item) for item in await list_price_lists(db)]
