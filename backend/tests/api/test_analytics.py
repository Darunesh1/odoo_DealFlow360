"""Deal health and reporting.

The rules worth pinning: an alert is raised once and not re-raised while it is
open, a rep is measured against their own average rather than a company one,
and reporting reads frozen sales history rather than live lines.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.analytics import AlertStatus, AlertType
from app.models.quotation import QuotationStatus
from app.services import health_service, report_service
from app.services.report_service import ReportFilters
from tests.api.test_fulfillment import _catalog, _order


async def _stale_quotation(db_session, days: int = 9):
    from sqlalchemy import select

    from app.models.customer import Customer, CustomerTier
    from app.models.quotation import Quotation

    tier = (await db_session.execute(select(CustomerTier))).scalars().first()
    if tier is None:
        tier = CustomerTier(name="Bronze", max_discount_percent=5)
        db_session.add(tier)
        await db_session.flush()
    customer = (await db_session.execute(select(Customer))).scalars().first()
    if customer is None:
        customer = Customer(name="Zenith Co", tier_id=tier.id)
        db_session.add(customer)
        await db_session.flush()

    quotation = Quotation(
        number=f"Q-STALE-{datetime.now(timezone.utc).timestamp()}",
        customer_id=customer.id,
        status=QuotationStatus.DRAFT,
        currency="USD",
        customer_tier_id=tier.id,
        total=9750,
        last_activity_at=datetime.now(timezone.utc) - timedelta(days=days),
    )
    db_session.add(quotation)
    await db_session.commit()
    return quotation


async def test_an_idle_deal_is_flagged_once(db_session):
    from app.models.catalog import Currency

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    await db_session.commit()
    quotation = await _stale_quotation(db_session, days=9)

    assert await health_service.sweep(db_session) == 1
    # An hourly sweep must not produce an hourly duplicate.
    assert await health_service.sweep(db_session) == 0

    alerts = await health_service.list_alerts(db_session)
    assert len(alerts) == 1
    assert alerts[0].alert_type == AlertType.STALLED_DEAL
    assert "9 days" in alerts[0].detail


async def test_a_recent_deal_is_not_flagged(db_session):
    from app.models.catalog import Currency

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    await db_session.commit()
    await _stale_quotation(db_session, days=2)

    assert await health_service.sweep(db_session) == 0


async def test_resolving_buys_quiet_but_not_forever(db_session):
    from app.models.catalog import Currency

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    await db_session.commit()
    await _stale_quotation(db_session, days=9)
    await health_service.sweep(db_session)

    alert = (await health_service.list_alerts(db_session))[0]
    await health_service.act(db_session, alert=alert, action=AlertStatus.RESOLVED)
    await db_session.commit()

    # Just resolved, so the next sweep stays quiet.
    assert await health_service.sweep(db_session) == 0

    # Back-date the resolution and the deal, still stalled, is raised again.
    alert.acted_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.add(alert)
    await db_session.commit()
    assert await health_service.sweep(db_session) == 1


async def test_reporting_reads_frozen_history(db_session):
    """Editing a line after confirmation must not move the numbers."""
    from app.services import order_service

    product, variant, _, _ = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 4)
    await order_service.confirm_quotation(db_session, quotation=quotation)

    before = await report_service._build(db_session, ReportFilters())
    assert before["units_sold"] == 4
    assert before["revenue"] == pytest.approx(4560.0)

    # The line is still editable; the report must not follow it.
    quotation.lines[0].quantity = 99
    quotation.lines[0].line_total = 999999
    db_session.add(quotation.lines[0])
    await db_session.commit()

    after = await report_service._build(db_session, ReportFilters())
    assert after["units_sold"] == 4
    assert after["revenue"] == pytest.approx(4560.0)


async def test_a_period_filter_excludes_older_sales(db_session):
    from app.services import order_service

    product, variant, _, _ = await _catalog(db_session)
    quotation = await _order(db_session, product, variant, 4)
    await order_service.confirm_quotation(db_session, quotation=quotation)

    tomorrow = date.today() + timedelta(days=1)
    future = await report_service._build(
        db_session, ReportFilters(date_from=tomorrow)
    )
    assert future["units_sold"] == 0

    # And "to today" includes today, rather than cutting it off at midnight.
    today = await report_service._build(
        db_session, ReportFilters(date_to=date.today())
    )
    assert today["units_sold"] == 4
