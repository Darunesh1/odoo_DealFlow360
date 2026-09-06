"""What the blended risk score is for, and the shape of its curve.

The score decides who approves a deal, so the property that matters is not any
particular number but that "slightly over the ceiling" and "wildly over on a
large order" land in different bands. They used to be indistinguishable: the old
score was `8 x worst + 5 x weighted`, and on a single-line quotation the
weighted term equals the worst term, so it collapsed to `13 x points_over` -
3.5 points over was already HIGH and 7.7 points hit the 100 cap, whatever the
deal was worth.

These tests pin band boundaries and orderings, not exact scores, so the weights
in `core/config.py` can be tuned without rewriting the suite.
"""

from datetime import date, timedelta

import pytest

from app.models.catalog import Currency
from app.models.quotation import RiskBand
from app.models.user import Role
from app.schemas.catalog import ProductCreate, VariantRowInput
from app.schemas.customer import CustomerCreate, CustomerTierCreate
from app.schemas.quotation import QuotationCreate, QuotationLineCreate
from app.services import catalog_service, quotation_service, variant_service
from tests.conftest import make_user


async def _world(db, *, ceiling=10.0, price=1000.0, cost=400.0):
    """A tier with a ceiling, one product, and a customer on that tier."""
    db.add(Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True))
    await db.commit()
    tier = await catalog_service.create_customer_tier(
        db, CustomerTierCreate(name="Silver", max_discount_percent=ceiling)
    )
    product = await catalog_service.create_product(
        db, ProductCreate(name="Studio Laptop", category="Hardware", has_variants=False)
    )
    variant = product.variants[0]
    await variant_service.save_variant_matrix(
        db,
        product,
        [VariantRowInput(id=variant.id, sku="SKU-LAPTOP", unit_cost=cost, base_price=price)],
    )
    product = await catalog_service.get_product_by_id(db, product.id)
    customer = await catalog_service.create_customer(
        db, CustomerCreate(name="Northwind", tier_id=tier.id, contact_email="buy@example.com")
    )
    owner = await make_user(db, "rep@example.com", roles=[Role.SALES_REP])
    return tier, product, customer, owner


async def _quote(db, customer, owner, product, *, lines):
    """lines: [(quantity, discount_percent)]"""
    quotation = await quotation_service.create_draft_quotation(
        db,
        owner=owner,
        obj_in=QuotationCreate(
            customer_id=customer.id,
            currency="USD",
            requested_delivery_date=date.today() + timedelta(days=14),
        ),
    )
    for quantity, discount in lines:
        quotation = await quotation_service.add_line(
            db,
            quotation,
            QuotationLineCreate(
                variant_id=product.variants[0].id,
                quantity=quantity,
                line_discount_percent=discount,
            ),
        )
    return quotation


async def test_within_the_ceiling_needs_no_approver(db_session):
    """The only case that scores zero, and the only one that skips approval."""
    _, product, customer, owner = await _world(db_session, ceiling=10)

    quotation = await _quote(db_session, customer, owner, product, lines=[(1, 10)])

    assert quotation.blended_risk_score == 0
    assert quotation.risk_band == RiskBand.NONE
    assert quotation.requires_approval is False


async def test_a_small_breach_reaches_the_manager_not_finance(db_session):
    """Two points over on a small line is the Sales Manager's call alone."""
    _, product, customer, owner = await _world(db_session, ceiling=10, price=500)

    quotation = await _quote(db_session, customer, owner, product, lines=[(1, 12)])

    assert quotation.requires_approval is True
    assert quotation.risk_band == RiskBand.MEDIUM
    assert quotation.blended_risk_score < 45, "must not pull Finance in"


async def test_a_large_breach_reaches_finance_too(db_session):
    """Badly over is a different decision, and now scores like one."""
    _, product, customer, owner = await _world(db_session, ceiling=10, price=500)

    quotation = await _quote(db_session, customer, owner, product, lines=[(1, 22)])

    assert quotation.risk_band == RiskBand.HIGH
    assert quotation.blended_risk_score >= 45


async def test_deal_size_moves_the_score(db_session):
    """The fix for the real defect: quantity used to cancel out entirely.

    The same breach on 400 units gives away four hundred times the money, and
    the score has to say so.
    """
    _, product, customer, owner = await _world(db_session, ceiling=10, price=500)

    small = await _quote(db_session, customer, owner, product, lines=[(1, 12)])
    small_score = small.blended_risk_score

    big = await _quote(db_session, customer, owner, product, lines=[(400, 12)])

    assert big.blended_risk_score > small_score, (
        "a 400-unit breach must outscore a 1-unit breach at the same discount"
    )


async def test_a_pattern_of_small_breaches_outscores_a_single_one(db_session):
    """Breadth: four lines each a little over is not the same as one."""
    _, product, customer, owner = await _world(db_session, ceiling=10, price=500)

    one = await _quote(db_session, customer, owner, product, lines=[(1, 13), (1, 10)])
    many = await _quote(db_session, customer, owner, product, lines=[(1, 13), (1, 13)])

    assert many.blended_risk_score > one.blended_risk_score


async def test_the_stricter_of_tier_and_category_is_the_ceiling(db_session):
    """A category ceiling below the tier's binds instead of it."""
    from app.schemas.catalog import CategoryLimitCreate

    _, product, customer, owner = await _world(db_session, ceiling=20)
    await catalog_service.create_category_limit(
        db_session, CategoryLimitCreate(category="Hardware", max_discount_percent=5)
    )

    quotation = await _quote(db_session, customer, owner, product, lines=[(1, 10)])

    line = quotation.lines[0]
    assert line.tier_limit_percent == 20
    assert line.category_limit_percent == 5
    assert line.allowed_discount_percent == 5, "the stricter one wins"
    assert line.over_by_points == 5


async def test_the_score_does_not_saturate_on_a_small_breach(db_session):
    """The regression that made the bands meaningless.

    Under the old formula this line scored 13 x 4 = 52, i.e. HIGH, and pulled
    Finance into a four-point breach on a single small line.
    """
    _, product, customer, owner = await _world(db_session, ceiling=10, price=500)

    quotation = await _quote(db_session, customer, owner, product, lines=[(1, 14)])

    assert quotation.blended_risk_score < 45
    assert quotation.risk_band == RiskBand.MEDIUM


# --------------------------------------------------------------------------- #
# Margin has to mean the same thing in every currency
# --------------------------------------------------------------------------- #


async def test_margin_is_the_same_percentage_in_any_currency(db_session):
    """`unit_cost` is typed in the base currency; the line is priced in the
    quote's. Subtracting one from the other without converting reported a 15%
    margin as 88% on an INR quote, and the same number gates the upsell panel
    and is snapshotted into sales_records.
    """
    from app.models.catalog import Currency

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    db_session.add(
        Currency(code="INR", name="Indian Rupee", symbol="₹", rate_to_base=0.011)
    )
    await db_session.commit()

    tier = await catalog_service.create_customer_tier(
        db_session, CustomerTierCreate(name="Gold", max_discount_percent=15)
    )
    product = await catalog_service.create_product(
        db_session, ProductCreate(name="Cable Kit", category="Accessories", has_variants=False)
    )
    variant = product.variants[0]
    await variant_service.save_variant_matrix(
        db_session,
        product,
        [VariantRowInput(id=variant.id, sku="SKU-CABLE", unit_cost=44.16, base_price=66.25)],
    )
    product = await catalog_service.get_product_by_id(db_session, product.id)
    owner = await make_user(db_session, "rep@example.com", roles=[Role.SALES_REP])

    percentages = {}
    for index, code in enumerate(("USD", "INR")):
        customer = await catalog_service.create_customer(
            db_session,
            CustomerCreate(
                name=f"Buyer {code}", tier_id=tier.id, contact_email=f"b{index}@example.com"
            ),
        )
        quotation = await quotation_service.create_draft_quotation(
            db_session,
            owner=owner,
            obj_in=QuotationCreate(
                customer_id=customer.id,
                currency=code,
                requested_delivery_date=date.today() + timedelta(days=14),
            ),
        )
        quotation = await quotation_service.add_line(
            db_session,
            quotation,
            QuotationLineCreate(
                variant_id=product.variants[0].id, quantity=30, line_discount_percent=19
            ),
        )
        percentages[code] = quotation.margin_total / quotation.total * 100

    assert percentages["USD"] == pytest.approx(percentages["INR"], abs=0.01), (
        "the same deal cannot have two different margins because of its currency"
    )
    # 66.25 less 19% is 53.66 against a 44.16 cost, so roughly a sixth of the
    # total once 0% tax is added - nothing like the 88% the bug reported.
    assert 10 < percentages["USD"] < 25
