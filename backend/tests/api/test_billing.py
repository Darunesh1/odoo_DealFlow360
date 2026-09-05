"""Billing.

Three rules: nothing is billed before it ships, a period is billed once, and
proration is the unused fraction of the period times the change.
"""

from datetime import date, timedelta

import pytest

from app.models.billing import InvoiceStatus, PaymentMethod, SubscriptionStatus
from app.services import (
    fulfillment_service,
    invoice_service,
    order_service,
    payment_service,
    subscription_service,
)
from tests.api.test_fulfillment import _catalog, _order


async def _shipped_order(db_session, quantity: int = 6):
    """An order confirmed, split accepted and fully despatched."""
    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, quantity)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)
    await fulfillment_service.accept_split(db_session, fulfillment=fulfillment)
    await db_session.commit()

    for shipment in await fulfillment_service.list_shipments(db_session, fulfillment.id):
        await fulfillment_service.ship(db_session, shipment=shipment)
    await db_session.commit()
    return quotation, fulfillment


async def test_nothing_is_billed_before_it_ships(db_session):
    """A confirmed but undespatched order has nothing billable on it."""
    product, variant, _, _ = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 6)
    await order_service.confirm_quotation(db_session, quotation=quotation)

    assert await invoice_service.invoice_shipped(db_session, quotation=quotation) is None


async def test_only_the_shipped_units_are_invoiced(db_session):
    """24 against 11 on hand: the invoice covers 11, not 24."""
    product, variant, main, east = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 24)
    fulfillment = await order_service.confirm_quotation(db_session, quotation=quotation)
    await fulfillment_service.accept_split(db_session, fulfillment=fulfillment)
    await db_session.commit()
    for shipment in await fulfillment_service.list_shipments(db_session, fulfillment.id):
        await fulfillment_service.ship(db_session, shipment=shipment)
    await db_session.commit()

    invoice = await invoice_service.invoice_shipped(db_session, quotation=quotation)
    assert invoice is not None
    assert sum(line.quantity for line in invoice.lines) == 11


async def test_a_second_invoice_run_bills_nothing_new(db_session):
    quotation, _ = await _shipped_order(db_session)

    first = await invoice_service.invoice_shipped(db_session, quotation=quotation)
    assert first is not None
    # Everything shipped is now marked invoiced, so there is nothing left.
    assert await invoice_service.invoice_shipped(db_session, quotation=quotation) is None


async def test_proration_is_the_unused_fraction_of_the_period(db_session):
    """3 more seats with 16 of 31 days left: 3 x price x 16/31."""
    from app.models.billing import Subscription
    from app.models.catalog import RecurringInterval
    from sqlalchemy import select

    quotation, _ = await _shipped_order(db_session)

    start = date(2026, 10, 6)
    subscription = Subscription(
        customer_id=quotation.customer_id,
        quotation_id=quotation.id,
        quotation_line_id=quotation.lines[0].id,
        product_id=quotation.lines[0].product_id,
        plan_name="Care Plan 2yr",
        interval=RecurringInterval.MONTHLY,
        quantity=5,
        unit_price=39.10,
        currency="USD",
        status=SubscriptionStatus.ACTIVE,
        start_date=start,
        current_period_start=start,
        current_period_end=date(2026, 11, 6),
        next_billing_date=start,
    )
    db_session.add(subscription)
    await db_session.commit()

    event = await subscription_service.change_quantity(
        db_session,
        subscription=subscription,
        new_quantity=8,
        effective=date(2026, 10, 21),
    )
    await db_session.commit()

    assert event.days_in_period == 31
    assert event.days_remaining == 16
    assert float(event.proration_factor) == pytest.approx(16 / 31, abs=1e-6)
    # 3 x 39.10 x 16/31
    assert float(event.proration_amount) == pytest.approx(60.54, abs=0.01)


async def test_a_downgrade_issues_a_credit_note(db_session):
    from app.models.billing import CreditNote, Subscription
    from app.models.catalog import RecurringInterval
    from sqlalchemy import select

    quotation, _ = await _shipped_order(db_session)
    start = date.today()
    subscription = Subscription(
        customer_id=quotation.customer_id,
        quotation_id=quotation.id,
        quotation_line_id=quotation.lines[0].id,
        product_id=quotation.lines[0].product_id,
        plan_name="Care Plan 2yr",
        interval=RecurringInterval.MONTHLY,
        quantity=8,
        unit_price=39.10,
        currency="USD",
        status=SubscriptionStatus.ACTIVE,
        start_date=start,
        current_period_start=start,
        current_period_end=start + timedelta(days=30),
        next_billing_date=start,
    )
    db_session.add(subscription)
    await db_session.commit()

    event = await subscription_service.change_quantity(
        db_session, subscription=subscription, new_quantity=3, effective=start
    )
    await db_session.commit()

    assert float(event.proration_amount) < 0
    notes = (await db_session.execute(select(CreditNote))).scalars().all()
    assert len(notes) == 1
    assert float(notes[0].amount) == pytest.approx(-float(event.proration_amount))


async def test_payments_settle_the_invoice(db_session):
    quotation, _ = await _shipped_order(db_session)
    invoice = await invoice_service.invoice_shipped(db_session, quotation=quotation)

    half = round(float(invoice.total) / 2, 2)
    await payment_service.record_payment(
        db_session, invoice=invoice, amount=half, method=PaymentMethod.BANK_TRANSFER
    )
    await db_session.commit()
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID

    await payment_service.record_payment(
        db_session,
        invoice=invoice,
        amount=round(float(invoice.total) - half, 2),
        method=PaymentMethod.CARD,
    )
    await db_session.commit()
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.paid_at is not None


async def test_an_overpayment_is_refused(db_session):
    quotation, _ = await _shipped_order(db_session)
    invoice = await invoice_service.invoice_shipped(db_session, quotation=quotation)

    with pytest.raises(ValueError, match="more than the"):
        await payment_service.record_payment(
            db_session, invoice=invoice, amount=float(invoice.total) + 1
        )
