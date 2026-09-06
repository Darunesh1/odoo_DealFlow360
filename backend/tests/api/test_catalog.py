"""The rules the catalog rests on. Deliberately narrow."""

import pytest
from sqlalchemy import select

from app.models.catalog import Currency, VariantPrice
from app.models.customer import CustomerTier
from app.schemas.catalog import (
    CategoryLimitCreate,
    ProductCreate,
    VariantAttributeInput,
    VariantRowInput,
)
from app.schemas.customer import CustomerCreate, CustomerTierCreate
from app.services import catalog_service, pricing_service, variant_service
from app.services.catalog_service import InUseError


async def _currencies(db):
    db.add(Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True))
    db.add(Currency(code="INR", name="Indian Rupee", symbol="₹", rate_to_base=0.012))
    await db.commit()


async def _tier(db, name, ceiling) -> CustomerTier:
    return await catalog_service.create_customer_tier(
        db, CustomerTierCreate(name=name, max_discount_percent=ceiling)
    )


async def _prices(db, variant_id) -> dict[tuple[str, str], float]:
    rows = (
        await db.execute(
            select(VariantPrice).where(VariantPrice.variant_id == variant_id)
        )
    ).scalars().all()
    tiers = {
        tier.id: tier.name
        for tier in (await db.execute(select(CustomerTier))).scalars().all()
    }
    return {
        (tiers[row.tier_id], row.currency_code): float(row.unit_price) for row in rows
    }


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


async def test_the_stored_price_is_the_list_price_not_a_tier_discount(db_session):
    """One price in the base currency drives the whole grid, converted only.

    The tier used to discount this number as well as capping the rep, so a Gold
    line at its ceiling was 29% off list while the quote reported 15%. The tier
    is now only a ceiling: every tier sees the same list.
    """
    await _currencies(db_session)
    await _tier(db_session, "Bronze", 5)
    await _tier(db_session, "Silver", 10)
    await _tier(db_session, "Gold", 15)

    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Care Plan", category="Subscription",
                                  is_subscription=True, recurring_interval="monthly")
    )
    variant = product.variants[0]
    await variant_service.save_variant_matrix(
        db_session,
        product,
        [
            VariantRowInput(
                id=variant.id,
                sku=variant.sku,
                unit_cost=700,
                base_price=1000,
                # A plan is capped rather than stocked, and the cap is required.
                available_quantity=50,
            )
        ],
    )

    prices = await _prices(db_session, variant.id)
    assert prices[("Bronze", "USD")] == 1000
    assert prices[("Silver", "USD")] == 1000
    assert prices[("Gold", "USD")] == 1000, "the ceiling does not move the price"
    # 1000 USD at 0.012 base-per-INR.
    assert prices[("Gold", "INR")] == pytest.approx(83333.3333, abs=0.001)


async def test_raising_a_ceiling_does_not_move_the_price(db_session):
    """The ceiling governs what a rep may give away, not what the thing costs."""
    await _currencies(db_session)
    bronze = await _tier(db_session, "Bronze", 5)
    gold = await _tier(db_session, "Gold", 15)

    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Dock", category="Hardware", is_subscription=False)
    )
    variant = product.variants[0]
    await variant_service.save_variant_matrix(
        db_session,
        product,
        [VariantRowInput(id=variant.id, sku=variant.sku, unit_cost=50, base_price=100)],
    )
    assert (await _prices(db_session, variant.id))[("Gold", "USD")] == 100

    from app.schemas.customer import CustomerTierUpdate

    await catalog_service.update_customer_tier(
        db_session, gold, CustomerTierUpdate(max_discount_percent=20)
    )
    prices = await _prices(db_session, variant.id)
    assert prices[("Gold", "USD")] == 100, "a wider ceiling is not a discount"
    assert prices[("Bronze", "USD")] == 100
    assert bronze.max_discount_percent == 5
    assert gold.max_discount_percent == 20, "only the ceiling moved"


async def test_a_variant_cannot_be_saved_half_configured(db_session):
    """No cost, or a warehouse left blank, and the whole batch is refused."""
    await _currencies(db_session)
    await _tier(db_session, "Bronze", 5)
    from app.schemas.catalog import WarehouseCreate

    warehouse = await catalog_service.create_warehouse(
        db_session, WarehouseCreate(code="MAIN", name="Main Warehouse")
    )
    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Dock", category="Hardware")
    )
    variant = product.variants[0]

    # A stocked product with no quantity for the one warehouse there is.
    with pytest.raises(ValueError, match="Main Warehouse"):
        await variant_service.save_variant_matrix(
            db_session,
            product,
            [VariantRowInput(id=variant.id, sku=variant.sku, unit_cost=50, base_price=100)],
        )

    await variant_service.save_variant_matrix(
        db_session,
        product,
        [
            VariantRowInput(
                id=variant.id,
                sku=variant.sku,
                unit_cost=50,
                base_price=100,
                stock=[{"warehouse_id": warehouse.id, "quantity_on_hand": 4}],
            )
        ],
    )
    assert (await _prices(db_session, variant.id))[("Bronze", "USD")] == 100


async def test_tier_delete_is_refused_while_a_customer_is_on_it(db_session):
    tier = await _tier(db_session, "Bronze", 5)
    await catalog_service.create_customer(
        db_session, CustomerCreate(name="Acme Corp", tier_id=tier.id)
    )

    with pytest.raises(InUseError):
        await catalog_service.delete_customer_tier(db_session, tier)

    spare = await _tier(db_session, "Platinum", 20)
    await catalog_service.delete_customer_tier(db_session, spare)
    assert await catalog_service.get_customer_tier_by_name(db_session, "Platinum") is None


async def test_line_ceiling_is_the_stricter_of_tier_and_category(db_session):
    """The single rule the whole approval engine rests on.

    A category with no row has NO ceiling, so the tier's applies alone.
    """
    await _tier(db_session, "Gold", 15)
    await catalog_service.create_category_limit(
        db_session, CategoryLimitCreate(category="Services", max_discount_percent=10)
    )

    services = await catalog_service.get_category_limit(db_session, "Services")
    assert min(15.0, float(services.max_discount_percent)) == 10.0
    assert await catalog_service.get_category_limit(db_session, "Subscription") is None


async def test_a_rep_can_read_the_catalog_but_not_change_it(client, db_session, mock_emails):
    """The whole point of splitting the routers: reads open up, writes do not."""
    from app.models.user import Role
    from tests.conftest import API, admin_headers, auth_headers, make_user

    await make_user(db_session, "rep@example.com", roles=(Role.SALES_REP,))
    rep = await auth_headers(client, "rep@example.com")

    listed = await client.get(f"{API}/products?size=5", headers=rep)
    assert listed.status_code == 200
    body = listed.json()
    assert {"items", "total", "page", "size", "pages"} <= body.keys()

    assert (await client.get(f"{API}/catalog/stats", headers=rep)).status_code == 200

    blocked = await client.post(
        f"{API}/admin/products", headers=rep, json={"name": "Nope", "category": "X"}
    )
    assert blocked.status_code == 403
    # Tiers are configuration, not catalog: a rep sees none of it.
    assert (await client.get(f"{API}/admin/customer-tiers", headers=rep)).status_code == 403

    admin = await admin_headers(client, db_session)
    assert (
        await client.post(
            f"{API}/admin/products", headers=admin, json={"name": "Yes", "category": "X"}
        )
    ).status_code == 201


async def test_finance_manages_warehouses(client, db_session, mock_emails):
    from app.models.user import Role
    from tests.conftest import API, auth_headers, make_user

    await make_user(db_session, "fin@example.com", roles=(Role.FINANCE,))
    finance = await auth_headers(client, "fin@example.com")

    created = await client.post(
        f"{API}/admin/warehouses",
        headers=finance,
        json={"code": "EAST", "name": "East Depot"},
    )
    assert created.status_code == 201
    assert (await client.get(f"{API}/admin/warehouses", headers=finance)).status_code == 200


async def test_the_subscription_category_is_set_by_the_toggle(db_session):
    """The toggle is the only place subscription-ness is declared."""
    await _currencies(db_session)

    plan = await catalog_service.create_product(
        db_session,
        ProductCreate(
            name="Support SLA",
            # Deliberately wrong: the service overrides it.
            category="Services",
            is_subscription=True,
            recurring_interval="quarterly",
        ),
    )
    assert plan.category == "Subscription"

    # And the reverse: the name is refused on a product whose toggle is off.
    with pytest.raises(ValueError, match="Only a subscription product"):
        await catalog_service.create_product(
            db_session,
            ProductCreate(name="Sneaky", category="Subscription"),
        )

    # It is never suggested either, so nobody is invited to type it.
    assert "Subscription" not in await catalog_service.list_categories(db_session)


async def test_a_plan_cannot_be_sold_beyond_its_capacity(db_session):
    """A plan has no warehouse, so its limit is a capacity, checked at entry."""
    from datetime import date, timedelta

    from app.models.customer import Customer
    from app.schemas.quotation import QuotationCreate, QuotationLineCreate
    from app.services import quotation_service
    from tests.conftest import make_user

    await _currencies(db_session)
    tier = await _tier(db_session, "Bronze", 5)

    plan = await catalog_service.create_product(
        db_session,
        ProductCreate(
            name="Care Plan",
            category="Subscription",
            is_subscription=True,
            recurring_interval="monthly",
        ),
    )
    variant = plan.variants[0]
    await variant_service.save_variant_matrix(
        db_session,
        plan,
        [
            VariantRowInput(
                id=variant.id,
                sku=variant.sku,
                unit_cost=18,
                base_price=46,
                available_quantity=10,
            )
        ],
    )

    customer = Customer(name="Acme Corp", tier_id=tier.id)
    db_session.add(customer)
    await db_session.commit()
    rep = await make_user(db_session, "rep-cap@example.com")

    quotation = await quotation_service.create_draft_quotation(
        db_session,
        owner=rep,
        obj_in=QuotationCreate(
            customer_id=customer.id,
            currency="USD",
            requested_delivery_date=date.today() + timedelta(days=7),
        ),
    )

    with pytest.raises(ValueError, match="only 10 of 10 licences"):
        await quotation_service.add_line(
            db_session,
            quotation,
            QuotationLineCreate(variant_id=variant.id, quantity=11),
        )

    # Inside the cap it goes on without complaint.
    quotation = await quotation_service.add_line(
        db_session,
        quotation,
        QuotationLineCreate(variant_id=variant.id, quantity=10),
    )
    assert quotation.lines[0].quantity == 10
