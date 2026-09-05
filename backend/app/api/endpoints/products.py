"""Read-only product catalog, for everyone who works inside the app.

A sales rep needs to see what is sellable and at what price; only an admin may
change it. The write routes live in `catalog.py` behind `require_admin`, so this
router can be opened up without opening anything else.
"""

from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_db, get_pagination, require_roles
from app.api.endpoints.serializers import serialize_product
from app.core import cache
from app.core.cache import cached_json
from app.models.catalog import Product, ProductStatus, ProductVariant, VariantPrice
from app.models.customer import CustomerTier
from app.models.user import Role
from app.schemas.catalog import (
    CatalogStats,
    ProductListRow,
    ProductRead,
    ProductSort,
    SortOrder,
)
from app.schemas.common import Page
from app.services import catalog_service, pricing_service, variant_service

router = APIRouter(
    dependencies=[
        Depends(
            require_roles(
                Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER, Role.FINANCE
            )
        )
    ]
)


@router.get("/catalog/stats", response_model=CatalogStats)
async def read_catalog_stats(db: AsyncSession = Depends(get_db)) -> Any:
    """The three KPI boxes on the product catalog screen.

    Five aggregate queries for a header that changes only when an admin edits
    the catalog, so it is cached and invalidated by the catalog writes rather
    than re-counted on every page view.
    """

    async def load() -> dict:
        return (await _catalog_stats(db)).model_dump()

    return await cached_json(
        cache.NS_CATALOG, "stats", cache.TTL_CATALOG, load
    )


async def _catalog_stats(db: AsyncSession) -> CatalogStats:
    active = (
        await db.execute(
            select(func.count())
            .select_from(Product)
            .where(Product.status == ProductStatus.ACTIVE)
        )
    ).scalar_one()
    archived = (
        await db.execute(
            select(func.count())
            .select_from(Product)
            .where(Product.status == ProductStatus.ARCHIVED)
        )
    ).scalar_one()
    tiers = (await db.execute(select(func.count()).select_from(CustomerTier))).scalar_one()
    return CatalogStats(
        products_active=active,
        products_archived=archived,
        tier_count=tiers,
        currency_count=len(await catalog_service.list_currencies(db)),
        sku_count=await variant_service.count_skus(db),
    )


@router.get("/categories", response_model=List[str])
async def read_categories(db: AsyncSession = Depends(get_db)) -> Any:
    """Backs the category typeahead on the product form - read constantly,
    written when someone invents a new category."""
    return await cached_json(
        cache.NS_CATALOG,
        "categories",
        cache.TTL_CATALOG,
        lambda: catalog_service.list_categories(db),
    )


@router.get("/products", response_model=Page[ProductListRow])
async def read_products(
    db: AsyncSession = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    search: Optional[str] = Query(
        default=None, description="Match against name, category or SKU"
    ),
    status_filter: Optional[ProductStatus] = Query(default=None, alias="status"),
    sort: ProductSort = ProductSort.NAME,
    order: SortOrder = SortOrder.ASC,
) -> Any:
    base = await pricing_service.get_base_currency(db)
    base_code = base.code if base else "USD"

    # Variant count and cheapest price are correlated subqueries rather than a
    # GROUP BY join, so the row count stays exactly the product count and
    # pagination cannot double-count a product with four SKUs.
    variant_count = (
        select(func.count())
        .select_from(ProductVariant)
        .where(ProductVariant.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
    )
    min_price = (
        select(func.min(VariantPrice.unit_price))
        .select_from(VariantPrice)
        .join(ProductVariant, ProductVariant.id == VariantPrice.variant_id)
        .where(
            ProductVariant.product_id == Product.id,
            VariantPrice.currency_code == base_code,
        )
        .correlate(Product)
        .scalar_subquery()
    )
    max_price = (
        select(func.max(VariantPrice.unit_price))
        .select_from(VariantPrice)
        .join(ProductVariant, ProductVariant.id == VariantPrice.variant_id)
        .where(
            ProductVariant.product_id == Product.id,
            VariantPrice.currency_code == base_code,
        )
        .correlate(Product)
        .scalar_subquery()
    )

    filters = []
    if status_filter:
        filters.append(Product.status == status_filter)
    if search:
        term = f"%{search.lower()}%"
        sku_hit = (
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                func.lower(ProductVariant.sku).like(term),
            )
            .correlate(Product)
            .exists()
        )
        filters.append(
            or_(
                func.lower(Product.name).like(term),
                func.lower(Product.category).like(term),
                sku_hit,
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(Product).where(*filters))
    ).scalar_one()

    sort_column = {
        ProductSort.NAME: Product.name,
        ProductSort.CATEGORY: Product.category,
        ProductSort.TAX: Product.tax_percent,
        ProductSort.STATUS: Product.status,
        ProductSort.VARIANTS: variant_count,
        ProductSort.PRICE: min_price,
    }[sort]
    direction = sort_column.desc() if order is SortOrder.DESC else sort_column.asc()
    # A product nobody has priced yet has a NULL minimum. Postgres sorts NULLs
    # first descending, which would put unpriced products at the top of a
    # "most expensive" sort; push them to the end either way.
    if sort is ProductSort.PRICE:
        direction = direction.nullslast()

    stmt = (
        select(
            Product,
            variant_count.label("variant_count"),
            min_price.label("price_min"),
            max_price.label("price_max"),
        )
        .where(*filters)
        # Name breaks ties so paging is stable when the sort column repeats.
        .order_by(direction, Product.name)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )

    items = [
        ProductListRow(
            id=product.id,
            name=product.name,
            category=product.category,
            unit=product.unit,
            tax_percent=float(product.tax_percent),
            status=product.status,
            has_variants=product.has_variants,
            is_subscription=product.is_subscription,
            recurring_interval=product.recurring_interval,
            variant_count=count,
            price_min=float(low) if low is not None else None,
            price_max=float(high) if high is not None else None,
            base_currency=base_code,
        )
        for product, count, low, high in (await db.execute(stmt)).all()
    ]

    return Page[ProductListRow](
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(total),
    )


@router.get("/products/{product_id}", response_model=ProductRead)
async def read_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    product = await catalog_service.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    return await serialize_product(db, product)
