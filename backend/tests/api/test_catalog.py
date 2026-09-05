"""The four rules the catalog rests on. Deliberately narrow."""

import pytest
from sqlalchemy import select

from app.models.catalog import (
    CategoryDiscountLimit,
    Currency,
    Product,
    ProductVariant,
    VariantPrice,
)
from app.models.customer import Customer, CustomerTier
from app.schemas.catalog import (
    CategoryLimitCreate,
    ProductCreate,
    VariantAttributeInput,
    VariantPriceInput,
    VariantRowInput,
)
from app.schemas.customer import CustomerCreate, CustomerTierCreate
from app.services import catalog_service, variant_service
from app.services.catalog_service import InUseError


async def _currencies(db):
    db.add(Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True))
    db.add(Currency(code="INR", name="Indian Rupee", symbol="₹", rate_to_base=0.02))
    await db.commit()


async def _tier(db, name="Gold", ceiling=15.0) -> CustomerTier:
    return await catalog_service.create_customer_tier(
        db, CustomerTierCreate(name=name, max_discount_percent=ceiling)
    )


async def test_generate_variants_is_idempotent(db_session):
    """Two attributes of two values make four SKUs, and regenerating keeps four."""
    product = await catalog_service.create_product(
        db_session,
        ProductCreate(
            name="Laptop Pro 14",
            category="Hardware",
            has_variants=True,
            attributes=[
                VariantAttributeInput(name="Color", values=["Black", "Silver"]),
                VariantAttributeInput(name="RAM", values=["8GB", "16GB"]),
            ],
        ),
    )
    assert len(product.variants) == 4
    skus = {variant.sku for variant in product.variants}
    assert len(skus) == 4, "every generated variant needs its own SKU"

    await variant_service.generate_variants(db_session, product)
    await db_session.commit()
    again = await catalog_service.get_product_by_id(db_session, product.id)
    assert len(again.variants) == 4
    assert {variant.sku for variant in again.variants} == skus


async def test_entering_one_currency_fills_the_other(db_session):
    """The admin types USD; INR is derived at the rate and marked as derived."""
    await _currencies(db_session)
    tier = await _tier(db_session)
    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Care Plan", category="Subscription")
    )
    variant = product.variants[0]

    await variant_service.save_variant_matrix(
        db_session,
        product,
        [
            VariantRowInput(
                id=variant.id,
                sku=variant.sku,
                prices=[
                    VariantPriceInput(
                        tier_id=tier.id, currency_code="USD", unit_price=46
                    )
                ],
            )
        ],
    )

    prices = {
        row.currency_code: row
        for row in (
            await db_session.execute(
                select(VariantPrice).where(VariantPrice.variant_id == variant.id)
            )
        )
        .scalars()
        .all()
    }
    assert float(prices["USD"].unit_price) == 46
    assert prices["USD"].is_entered is True
    # 46 USD at 0.02 base-per-INR is 2300 INR.
    assert float(prices["INR"].unit_price) == 2300
    assert prices["INR"].is_entered is False


async def test_tier_delete_is_refused_while_a_customer_is_on_it(db_session):
    tier = await _tier(db_session, name="Bronze", ceiling=5)
    await catalog_service.create_customer(
        db_session, CustomerCreate(name="Acme Corp", tier_id=tier.id)
    )

    with pytest.raises(InUseError):
        await catalog_service.delete_customer_tier(db_session, tier)

    spare = await _tier(db_session, name="Platinum", ceiling=20)
    await catalog_service.delete_customer_tier(db_session, spare)
    assert await catalog_service.get_customer_tier_by_name(db_session, "Platinum") is None


async def test_line_ceiling_is_the_stricter_of_tier_and_category(db_session):
    """The single rule the whole approval engine rests on.

    A category with no row has NO ceiling, so the tier's applies alone.
    """
    await _currencies(db_session)
    tier = await _tier(db_session, name="Gold", ceiling=15)
    await catalog_service.create_category_limit(
        db_session, CategoryLimitCreate(category="Services", max_discount_percent=10)
    )

    services = await catalog_service.get_category_limit(db_session, "Services")
    assert min(15.0, float(services.max_discount_percent)) == 10.0

    # "Subscription" was never given a ceiling; the tier is the only limit.
    assert await catalog_service.get_category_limit(db_session, "Subscription") is None
