"""Confirming a quotation, which is what turns it into an order.

There is no separate orders table: once CONFIRMED, the quotation row *is* the
sales order, and the mockup uses one reference (Q-1042) for the quotation, its
approval and its fulfillment alike.

Confirmation is the fan-out point of the whole system. It writes the immutable
sales history, opens the subscriptions, creates the fulfillment and runs the
split planner - all in one transaction, under a lock, so a double-clicked
Confirm cannot produce two of anything.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import with_lock
from app.models.analytics import AuditAction, SalesRecord
from app.models.billing import BillingTiming, Subscription, SubscriptionStatus
from app.models.catalog import RecurringInterval
from app.models.fulfillment import Fulfillment
from app.models.quotation import LineSource, Quotation, QuotationStatus
from app.models.user import User
from app.services import audit_service, fulfillment_service

# How many months one cycle of each interval covers. Weekly is the odd one out
# and is handled in days.
_MONTHS = {
    RecurringInterval.MONTHLY: 1,
    RecurringInterval.QUARTERLY: 3,
    RecurringInterval.YEARLY: 12,
}


def advance(start: date, interval: RecurringInterval, count: int = 1) -> date:
    """The end of `count` cycles starting at `start`.

    Month arithmetic by hand rather than a dependency: clamping to the end of
    a short month is the only hard part, and "the 31st becomes the 30th" is
    what every billing system does anyway.
    """
    if interval == RecurringInterval.WEEKLY:
        from datetime import timedelta

        return start + timedelta(weeks=count)

    months = _MONTHS[interval] * count
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    # Clamp: 31 Jan + 1 month is the last day of February, not an error.
    last_day = [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
        month - 1
    ]
    return date(year, month, min(start.day, last_day))


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


async def confirm_quotation(
    db: AsyncSession, *, quotation: Quotation, user: Optional[User] = None
) -> Fulfillment:
    """Turns an approved quotation into an order.

    Refuses anything not APPROVED: confirming a quote that is still with
    Finance would reserve stock against a discount nobody signed off.
    """
    if quotation.status == QuotationStatus.CONFIRMED:
        # Idempotent rather than an error: a double-clicked Confirm should land
        # the user on the split they just created, not on a red banner.
        existing = await fulfillment_service.get_for_quotation(db, quotation.id)
        if existing is not None:
            return existing
    if quotation.status not in {QuotationStatus.APPROVED, QuotationStatus.CONFIRMED}:
        raise ValueError("Only an approved quotation can be confirmed")

    async with with_lock(f"confirm:{quotation.id}", ttl=60):
        # Re-check inside the lock: the loser of a double-click race must see
        # the winner's write, not the state it read before waiting.
        existing = await fulfillment_service.get_for_quotation(db, quotation.id)
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        today = date.today()

        quotation.status = QuotationStatus.CONFIRMED
        quotation.confirmed_at = now
        quotation.last_activity_at = now
        db.add(quotation)

        for line in quotation.lines:
            _write_sales_record(db, quotation=quotation, line=line, sold_at=now)
            if line.is_recurring and line.recurring_interval:
                _open_subscription(db, quotation=quotation, line=line, start=today)

        fulfillment = Fulfillment(
            quotation_id=quotation.id,
            requested_delivery_date=quotation.requested_delivery_date,
        )
        db.add(fulfillment)
        # Planned BEFORE the flush, deliberately. A flush makes the row
        # persistent without marking its collections loaded, so reading
        # fulfillment.allocations afterwards emits a lazy load - which under
        # asyncpg is a MissingGreenlet rather than a query. While it is still
        # pending the collection is the empty list it was constructed with.
        await fulfillment_service.plan_split(
            db, fulfillment=fulfillment, quotation=quotation
        )

        audit_service.record(
            db,
            entity_type=audit_service.ENTITY_QUOTATION,
            entity_id=quotation.id,
            action=AuditAction.CONFIRMED,
            user=user,
            context={
                "quotation_number": quotation.number,
                "total": float(quotation.total),
                "shipments": fulfillment.estimated_shipment_count,
            },
        )
        await db.commit()

    return await fulfillment_service.get_for_quotation(db, quotation.id)


def _write_sales_record(
    db: AsyncSession, *, quotation: Quotation, line, sold_at: datetime
) -> None:
    """Freezes one line into sales history.

    Every reporting dimension is snapshotted rather than joined live: if a
    product moves category or a rep changes team, last quarter's numbers must
    stay as they were.
    """
    unit_price = float(line.unit_price)
    unit_cost = float(line.unit_cost)
    db.add(
        SalesRecord(
            quotation_id=quotation.id,
            quotation_line_id=line.id,
            product_id=line.product_id,
            product_name=line.product_name,
            customer_id=quotation.customer_id,
            sales_rep_id=quotation.owner_id,
            sales_rep_name=quotation.owner_name,
            variant_id=line.variant_id,
            sku=line.sku,
            category=line.category,
            customer_tier_id=quotation.customer_tier_id,
            sales_team_id=quotation.sales_team_id,
            quantity=line.quantity,
            unit_price=unit_price,
            unit_cost=unit_cost,
            discount_percent=float(line.discount_percent),
            line_net=float(line.line_net),
            line_total=float(line.line_total),
            margin_amount=round((unit_price - unit_cost) * line.quantity, 2),
            is_recurring=line.is_recurring,
            recurring_interval=line.recurring_interval,
            source=line.source,
            # Answers "Top Upsold Product" without reconstructing anything.
            came_from_upsell=line.source
            in {LineSource.UPSELL, LineSource.CROSS_SELL},
            sold_at=sold_at,
        )
    )


def _open_subscription(
    db: AsyncSession, *, quotation: Quotation, line, start: date
) -> None:
    """Turns a recurring line into a contract.

    Price, cycle and timing are snapshots: repricing "Care Plan 2yr" from $46
    to $52 tomorrow must not retroactively change what this customer agreed to.
    """
    period_end = advance(start, line.recurring_interval)
    db.add(
        Subscription(
            customer_id=quotation.customer_id,
            quotation_id=quotation.id,
            quotation_line_id=line.id,
            product_id=line.product_id,
            variant_id=line.variant_id,
            plan_name=line.product_name,
            interval=line.recurring_interval,
            interval_count=1,
            billing_timing=BillingTiming.ADVANCE,
            quantity=line.quantity,
            unit_price=float(line.unit_price)
            * (1 - float(line.discount_percent) / 100),
            currency=quotation.currency,
            status=SubscriptionStatus.ACTIVE,
            start_date=start,
            current_period_start=start,
            current_period_end=period_end,
            # Billed in advance, so the first invoice is due at the start of
            # the period rather than the end of it.
            next_billing_date=start,
        )
    )
