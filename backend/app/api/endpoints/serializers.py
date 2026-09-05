"""Shared response shaping for the catalog routers.

Lives apart from any router so the admin, product and warehouse routers all
render a product, a variant and a stock row the same way - there is one
implementation, not three that can drift.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product, ProductVariant
from app.schemas.catalog import ProductRead, ProductVariantRead, StockRead
from app.services import catalog_service


async def serialize_variant(
    db: AsyncSession, variant: ProductVariant
) -> ProductVariantRead:
    stock = await catalog_service.list_stock_for_variant(db, variant.id)
    return ProductVariantRead(
        id=variant.id,
        sku=variant.sku,
        name=variant.name,
        options=variant.options or {},
        unit_cost=float(variant.unit_cost),
        base_price=float(variant.base_price),
        available_quantity=variant.available_quantity,
        is_default=variant.is_default,
        is_active=variant.is_active,
        prices=[
            {
                "tier_id": price.tier_id,
                "currency_code": price.currency_code,
                "unit_price": float(price.unit_price),
            }
            for price in variant.prices
        ],
        stock=[
            {
                "warehouse_id": item.warehouse_id,
                "quantity_on_hand": item.quantity_on_hand,
                "quantity_reserved": item.quantity_reserved,
                "quantity_available": item.quantity_available,
            }
            for item in stock
        ],
    )


async def serialize_product(db: AsyncSession, product: Product) -> ProductRead:
    return ProductRead(
        id=product.id,
        name=product.name,
        category=product.category,
        description=product.description,
        unit=product.unit,
        tax_percent=float(product.tax_percent),
        is_subscription=product.is_subscription,
        recurring_interval=product.recurring_interval,
        has_variants=product.has_variants,
        is_promoted=product.is_promoted,
        promotion_label=product.promotion_label,
        status=product.status,
        created_at=product.created_at,
        updated_at=product.updated_at,
        attributes=[
            {
                "id": attribute.id,
                "name": attribute.name,
                "position": attribute.position,
                "values": [
                    {"id": value.id, "value": value.value, "position": value.position}
                    for value in attribute.values
                ],
            }
            for attribute in product.attributes
        ],
        variants=[await serialize_variant(db, variant) for variant in product.variants],
    )


def serialize_stock(item) -> StockRead:
    variant = item.variant
    product = variant.product if variant else None
    return StockRead(
        id=item.id,
        warehouse_id=item.warehouse_id,
        variant_id=item.variant_id,
        quantity_on_hand=item.quantity_on_hand,
        quantity_reserved=item.quantity_reserved,
        quantity_available=item.quantity_available,
        reorder_point=item.reorder_point,
        reorder_quantity=item.reorder_quantity,
        lead_time_days=item.lead_time_days,
        bin_location=item.bin_location,
        created_at=item.created_at,
        updated_at=item.updated_at,
        warehouse_name=item.warehouse.name if item.warehouse else "",
        warehouse_code=item.warehouse.code if item.warehouse else "",
        product_id=product.id if product else item.variant_id,
        product_name=product.name if product else "",
        variant_name=variant.name if variant else "",
        sku=variant.sku if variant else "",
    )
