"""The warehouse split.

The planner's job is to draw from the fewest warehouses, break ties on the
rates a human entered, and backorder what nothing can cover - never to refuse.
"""

import pytest

from app.models.fulfillment import AllocationStatus, FulfillmentStatus
from app.models.inventory import StockItem, Warehouse
from app.services import fulfillment_service


async def _catalog(db_session):
    """A stocked variant across two warehouses with different rates."""
    from app.models.catalog import Currency
    from app.schemas.catalog import ProductCreate, VariantRowInput
    from app.schemas.customer import CustomerTierCreate
    from app.services import catalog_service, variant_service

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    await db_session.commit()
    await catalog_service.create_customer_tier(
        db_session, CustomerTierCreate(name="Bronze", max_discount_percent=5)
    )

    main = Warehouse(
        code="MAIN",
        name="Main Warehouse",
        shipping_base_cost=25,
        shipping_cost_per_unit=0.7,
        default_lead_time_days=5,
    )
    east = Warehouse(
        code="EAST",
        name="East Depot",
        shipping_base_cost=18,
        shipping_cost_per_unit=0.9,
        default_lead_time_days=9,
    )
    db_session.add_all([main, east])
    await db_session.commit()

    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Laptop Pro 14", category="Hardware")
    )
    variant = product.variants[0]
    await variant_service.save_variant_matrix(
        db_session,
        product,
        [
            VariantRowInput(
                id=variant.id,
                sku=variant.sku,
                unit_cost=850,
                base_price=1200,
                stock=[
                    {"warehouse_id": main.id, "quantity_on_hand": 3},
                    {"warehouse_id": east.id, "quantity_on_hand": 8},
                ],
            )
        ],
    )
    return product, variant, main, east


async def _order(db_session, product, variant, quantity: int):
    """An approved quotation with one stocked line, ready to confirm."""
    from datetime import datetime, timezone

    from app.models.customer import Customer, CustomerTier
    from app.models.quotation import Quotation, QuotationLine, QuotationStatus
    from sqlalchemy import select

    tier = (await db_session.execute(select(CustomerTier))).scalars().first()
    customer = Customer(name="Acme Corp", tier_id=tier.id)
    db_session.add(customer)
    await db_session.flush()

    quotation = Quotation(
        number=f"Q-{datetime.now(timezone.utc).timestamp()}",
        customer_id=customer.id,
        status=QuotationStatus.APPROVED,
        currency="USD",
        customer_tier_id=tier.id,
        lines=[
            QuotationLine(
                position=1,
                product_id=product.id,
                variant_id=variant.id,
                product_name=product.name,
                sku=variant.sku,
                category=product.category,
                quantity=quantity,
                unit_price=1140,
                list_price_at_entry=1200,
                unit_cost=850,
                line_net=1140 * quantity,
                line_total=1140 * quantity,
            )
        ],
    )
    db_session.add(quotation)
    await db_session.commit()
    return quotation


async def test_a_short_order_splits_and_backorders_the_rest(db_session):
    """24 units against 3 + 8 on hand: two warehouses drawn, 13 backordered."""
    from app.services import order_service

    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 24)

    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)

    by_status = {}
    for allocation in fulfillment.allocations:
        by_status.setdefault(allocation.status, []).append(allocation)

    assert sum(a.quantity for a in by_status[AllocationStatus.PLANNED]) == 11
    assert sum(a.quantity for a in by_status[AllocationStatus.BACKORDERED]) == 13
    assert fulfillment.status == FulfillmentStatus.BACKORDER
    # Two warehouses, so two shipments - not one per allocation.
    assert fulfillment.estimated_shipment_count == 2
    # 25 + 3x0.70 from Main, 18 + 8x0.90 from East. Real arithmetic over the
    # rates a human typed.
    assert float(fulfillment.estimated_shipping_cost) == pytest.approx(52.30)


async def test_an_order_one_warehouse_can_cover_uses_only_that_one(db_session):
    from app.services import order_service

    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 6)

    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)

    assert fulfillment.estimated_shipment_count == 1
    assert len(fulfillment.allocations) == 1
    # East holds 8 and Main holds 3, so the deepest shelf covers it alone.
    assert fulfillment.allocations[0].warehouse_id == east.id
    assert fulfillment.status == FulfillmentStatus.SPLIT_PENDING


async def test_accepting_reserves_the_stock(db_session):
    from sqlalchemy import select

    from app.services import order_service

    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 6)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)

    await fulfillment_service.accept_split(db_session, fulfillment=fulfillment)
    await db_session.commit()

    stock = (
        await db_session.execute(
            select(StockItem).where(
                StockItem.variant_id == variant.id,
                StockItem.warehouse_id == east.id,
            )
        )
    ).scalars().first()
    assert stock.quantity_reserved == 6
    # Held, not gone: the units only leave on despatch.
    assert stock.quantity_on_hand == 8
    assert stock.quantity_available == 2


async def test_a_split_cannot_be_accepted_twice(db_session):
    from app.services import order_service

    product, variant, _, _ = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 2)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)

    await fulfillment_service.accept_split(db_session, fulfillment=fulfillment)
    await db_session.commit()

    with pytest.raises(ValueError, match="already been accepted"):
        await fulfillment_service.accept_split(db_session, fulfillment=fulfillment)


async def test_an_override_that_loses_units_is_refused(db_session):
    """A split that ships fewer units than were sold is an invoice that will
    never reconcile."""
    from app.services import order_service

    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 6)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)
    line = quotation.lines[0]

    with pytest.raises(ValueError, match="allocated 4 of 6"):
        await fulfillment_service.manual_override(
            db_session,
            fulfillment=fulfillment,
            quotation=quotation,
            rows=[
                {
                    "quotation_line_id": str(line.id),
                    "warehouse_id": str(east.id),
                    "quantity": 4,
                }
            ],
        )


async def test_an_override_cannot_overdraw_a_warehouse(db_session):
    from app.services import order_service

    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 6)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)
    line = quotation.lines[0]

    with pytest.raises(ValueError, match="holds 3, not 6"):
        await fulfillment_service.manual_override(
            db_session,
            fulfillment=fulfillment,
            quotation=quotation,
            rows=[
                {
                    "quotation_line_id": str(line.id),
                    "warehouse_id": str(main.id),
                    "quantity": 6,
                }
            ],
        )
