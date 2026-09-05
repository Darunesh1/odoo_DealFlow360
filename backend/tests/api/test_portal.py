"""The customer portal.

Section 7 of the spec calls for "a real, separate, restricted view". These
tests are about the restriction: a customer sees their own company's
quotations and nothing else, no cost or margin reaches them, and accepting
their counter re-runs the governance rather than quietly changing the price.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.quotation import ChangeRequestStatus, QuotationStatus
from app.models.user import Role
from app.services import negotiation_service
from tests.conftest import make_user

API = "/api"


async def _two_customers(db_session):
    from app.models.catalog import Currency
    from app.models.customer import Customer, CustomerTier

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    tier = CustomerTier(name="Bronze", max_discount_percent=5)
    db_session.add(tier)
    await db_session.flush()
    acme = Customer(name="Acme Corp", tier_id=tier.id)
    beta = Customer(name="Beta Industries", tier_id=tier.id)
    db_session.add_all([acme, beta])
    await db_session.commit()
    return acme, beta, tier


async def _quotation(db_session, customer, tier, status=QuotationStatus.APPROVED):
    from app.models.quotation import Quotation, QuotationLine

    quotation = Quotation(
        number=f"Q-{datetime.now(timezone.utc).timestamp()}",
        customer_id=customer.id,
        status=status,
        currency="USD",
        customer_tier_id=tier.id,
        total=1200,
        lines=[
            QuotationLine(
                position=1,
                product_name="Laptop Pro 14",
                quantity=1,
                unit_price=1200,
                list_price_at_entry=1200,
                # The number that must never reach the portal.
                unit_cost=850,
                line_net=1200,
                line_total=1200,
            )
        ],
    )
    db_session.add(quotation)
    await db_session.commit()
    return quotation


async def test_a_customer_sees_only_their_own_company(client, db_session):
    from tests.conftest import auth_headers

    acme, beta, tier = await _two_customers(db_session)
    mine = await _quotation(db_session, acme, tier)
    theirs = await _quotation(db_session, beta, tier)

    user = await make_user(db_session, "buyer@acme.example", roles=(Role.CUSTOMER,))
    user.customer_id = acme.id
    db_session.add(user)
    await db_session.commit()
    headers = await auth_headers(client, "buyer@acme.example")

    listing = await client.get(f"{API}/portal/quotations", headers=headers)
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [str(mine.id)]

    # 404 rather than 403: the portal is not an existence oracle either.
    other = await client.get(
        f"{API}/portal/quotations/{theirs.id}", headers=headers
    )
    assert other.status_code == 404


async def test_the_portal_never_returns_cost_or_margin(client, db_session):
    from tests.conftest import auth_headers

    acme, _, tier = await _two_customers(db_session)
    quotation = await _quotation(db_session, acme, tier)

    user = await make_user(db_session, "buyer2@acme.example", roles=(Role.CUSTOMER,))
    user.customer_id = acme.id
    db_session.add(user)
    await db_session.commit()
    headers = await auth_headers(client, "buyer2@acme.example")

    body = (
        await client.get(f"{API}/portal/quotations/{quotation.id}", headers=headers)
    ).json()

    flat = str(body)
    assert "unit_cost" not in flat
    assert "margin" not in flat
    assert "risk" not in flat
    # And the cost itself is nowhere in the payload, under any name.
    assert "850" not in flat


async def test_a_rep_cannot_use_the_portal(client, db_session):
    from tests.conftest import auth_headers

    await make_user(db_session, "rep-portal@example.com", roles=(Role.SALES_REP,))
    headers = await auth_headers(client, "rep-portal@example.com")

    response = await client.get(f"{API}/portal/quotations", headers=headers)
    # Not an internal screen with a different label.
    assert response.status_code == 403


async def _priced_quotation(db_session, discount: float = 0.0):
    """A quotation whose line is backed by a real priced variant.

    recalculate_quotation skips a line with no product - it has no ceiling to
    measure against - so a fixture that invents a bare line would score zero
    however large the discount.
    """
    from app.schemas.catalog import CategoryLimitCreate
    from app.schemas.quotation import QuotationCreate, QuotationLineCreate
    from app.services import catalog_service, quotation_service
    from tests.api.test_fulfillment import _catalog

    product, variant, _, _ = await _catalog(db_session)
    await catalog_service.create_category_limit(
        db_session,
        CategoryLimitCreate(category="Hardware", max_discount_percent=15),
    )

    from sqlalchemy import select

    from app.models.customer import Customer, CustomerTier

    # _catalog seeds the tier but no customer; the quotation needs one.
    tier = (await db_session.execute(select(CustomerTier))).scalars().first()
    customer = Customer(name="Acme Corp", tier_id=tier.id)
    db_session.add(customer)
    await db_session.commit()

    rep = await make_user(db_session, "rep-priced@example.com", roles=(Role.SALES_REP,))

    quotation = await quotation_service.create_draft_quotation(
        db_session,
        owner=rep,
        obj_in=QuotationCreate(
            customer_id=customer.id,
            currency="USD",
            requested_delivery_date=date.today() + timedelta(days=14),
        ),
    )
    quotation = await quotation_service.add_line(
        db_session,
        quotation,
        QuotationLineCreate(
            variant_id=variant.id, quantity=2, line_discount_percent=discount
        ),
    )
    quotation.status = QuotationStatus.APPROVED
    db_session.add(quotation)
    await db_session.commit()
    return quotation, customer, rep


async def test_accepting_a_counter_re_enters_approval(db_session):
    """Spec B8: terms beyond the threshold re-enter approval automatically."""
    from app.models.approval import ApprovalRule, ApprovalRuleStep, ApprovalTrigger
    from app.models.quotation import RiskBand

    quotation, acme, rep = await _priced_quotation(db_session)

    db_session.add(
        ApprovalRule(
            name="Within limits",
            min_score=0,
            max_score=0.01,
            risk_band=RiskBand.NONE,
            sort_order=1,
            is_active=True,
            steps=[],
        )
    )
    db_session.add(
        ApprovalRule(
            name="Over limit",
            min_score=0.01,
            max_score=None,
            risk_band=RiskBand.HIGH,
            sort_order=2,
            is_active=True,
            steps=[
                ApprovalRuleStep(step_order=1, role=Role.SALES_MANAGER),
                ApprovalRuleStep(step_order=2, role=Role.FINANCE),
            ],
        )
    )
    await db_session.commit()

    customer_user = await make_user(
        db_session, "buyer3@acme.example", roles=(Role.CUSTOMER,)
    )
    customer_user.customer_id = acme.id
    db_session.add(customer_user)
    await db_session.commit()

    request = await negotiation_service.open_change_request(
        db_session,
        quotation=quotation,
        requested_by=customer_user,
        counter_discount_percent=40,
        note="We would like 40% off",
    )
    await db_session.commit()
    assert quotation.status == QuotationStatus.NEGOTIATION

    updated, approval = await negotiation_service.accept_change_request(
        db_session, quotation=quotation, request=request, user=rep
    )

    assert request.status == ChangeRequestStatus.ACCEPTED
    assert approval.trigger == ApprovalTrigger.CUSTOMER_COUNTER
    # 40% against a 5% ceiling is well over, so it needs approval again.
    assert updated.status == QuotationStatus.PENDING_APPROVAL
    assert [step.role for step in approval.steps] == [
        Role.SALES_MANAGER,
        Role.FINANCE,
    ]


async def test_a_counter_within_limits_needs_no_approval(db_session):
    """The other branch: the same code path, auto-approved."""
    from app.models.approval import ApprovalRule
    from app.models.quotation import RiskBand

    quotation, acme, rep = await _priced_quotation(db_session)

    db_session.add(
        ApprovalRule(
            name="Within limits",
            min_score=0,
            max_score=0.01,
            risk_band=RiskBand.NONE,
            sort_order=1,
            is_active=True,
            steps=[],
        )
    )
    await db_session.commit()

    customer_user = await make_user(
        db_session, "buyer4@acme.example", roles=(Role.CUSTOMER,)
    )
    customer_user.customer_id = acme.id
    db_session.add(customer_user)
    await db_session.commit()

    # 3% is inside both the Bronze tier ceiling and the Hardware one.
    request = await negotiation_service.open_change_request(
        db_session,
        quotation=quotation,
        requested_by=customer_user,
        counter_discount_percent=3,
    )
    await db_session.commit()

    updated, approval = await negotiation_service.accept_change_request(
        db_session, quotation=quotation, request=request, user=rep
    )

    assert approval.steps == []
    assert updated.status == QuotationStatus.APPROVED
