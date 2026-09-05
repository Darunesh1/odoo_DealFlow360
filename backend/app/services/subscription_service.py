"""Subscription lifecycle and proration (spec A5, screens 9 and 10).

The proration rule, stated once:

```
days_in_period   = current_period_end - current_period_start
days_remaining   = current_period_end - effective_date
proration_factor = days_remaining / days_in_period
delta            = (new_qty - old_qty) x unit_price x proration_factor
```

A positive delta becomes a charge on the next invoice; a negative one becomes
a credit and a credit note. Every intermediate value is written to the
``SubscriptionEvent``, which is why the billing screen can show proration
*history* rather than an unexplained adjustment.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import with_lock
from app.models.analytics import AuditAction
from app.models.billing import (
    CreditNote,
    CreditNoteStatus,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)
from app.models.user import User
from app.services import audit_service


async def get(db: AsyncSession, subscription_id: uuid.UUID) -> Optional[Subscription]:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def list_subscriptions(
    db: AsyncSession,
    *,
    customer_id: Optional[uuid.UUID] = None,
    status: Optional[SubscriptionStatus] = None,
) -> Sequence[Subscription]:
    stmt = select(Subscription).order_by(Subscription.created_at.desc())
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if status:
        stmt = stmt.where(Subscription.status == status)
    return (await db.execute(stmt)).scalars().all()


async def counts(db: AsyncSession) -> dict[str, int]:
    rows = (
        await db.execute(
            select(Subscription.status, func.count()).group_by(Subscription.status)
        )
    ).all()
    result = {status.value: 0 for status in SubscriptionStatus}
    for status, count in rows:
        result[status.value] = int(count)
    return result


def _proration(
    subscription: Subscription, effective: date
) -> tuple[int, int, Decimal]:
    """Days in the period, days left, and the fraction of it still unused.

    Clamped to [0, 1]: an effective date outside the period would otherwise
    produce a negative or greater-than-one factor and bill nonsense.
    """
    start = subscription.current_period_start
    end = subscription.current_period_end
    days_in_period = max((end - start).days, 1)
    days_remaining = max(min((end - effective).days, days_in_period), 0)
    factor = Decimal(days_remaining) / Decimal(days_in_period)
    return days_in_period, days_remaining, factor


async def change_quantity(
    db: AsyncSession,
    *,
    subscription: Subscription,
    new_quantity: int,
    effective: Optional[date] = None,
    user: Optional[User] = None,
    reason: Optional[str] = None,
) -> SubscriptionEvent:
    """Mid-cycle quantity change, prorated for the unused remainder."""
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise ValueError("Only an active subscription can be changed")
    if new_quantity < 1:
        raise ValueError("Quantity must be at least 1")
    if new_quantity == subscription.quantity:
        raise ValueError("That is already the quantity")

    effective = effective or date.today()
    days_in_period, days_remaining, factor = _proration(subscription, effective)

    previous = subscription.quantity
    unit_price = Decimal(str(subscription.unit_price))
    delta = (Decimal(new_quantity - previous) * unit_price * factor).quantize(
        Decimal("0.01")
    )

    event = SubscriptionEvent(
        subscription_id=subscription.id,
        event_type=SubscriptionEventType.QUANTITY_CHANGED,
        effective_date=effective,
        previous_quantity=previous,
        new_quantity=new_quantity,
        previous_unit_price=float(unit_price),
        new_unit_price=float(unit_price),
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        days_in_period=days_in_period,
        days_remaining=days_remaining,
        proration_factor=float(factor),
        proration_amount=float(delta),
        reason=reason,
        created_by_id=user.id if user else None,
    )
    db.add(event)

    subscription.quantity = new_quantity
    db.add(subscription)

    # A downgrade leaves the customer in credit for the rest of the period.
    if delta < 0:
        note = await _credit_note(
            db,
            subscription=subscription,
            amount=-delta,
            reason=f"Quantity reduced from {previous} to {new_quantity}",
        )
        await db.flush()
        event.credit_note_id = note.id
        db.add(event)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_SUBSCRIPTION,
        entity_id=subscription.id,
        action=AuditAction.EDITED,
        user=user,
        reason=reason or f"Quantity {previous} -> {new_quantity}",
        context={
            "proration_factor": float(factor),
            "proration_amount": float(delta),
            "days_remaining": days_remaining,
        },
    )
    return event


async def pause(
    db: AsyncSession, *, subscription: Subscription, user: Optional[User] = None
) -> Subscription:
    """Stops billing without ending the contract.

    next_billing_date is cleared, which drops the row out of the biller's
    partial index - a second guard against billing a paused customer, on top
    of the status check.
    """
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise ValueError("Only an active subscription can be paused")

    subscription.status = SubscriptionStatus.PAUSED
    subscription.paused_at = datetime.now(timezone.utc)
    subscription.next_billing_date = None
    db.add(subscription)
    db.add(
        SubscriptionEvent(
            subscription_id=subscription.id,
            event_type=SubscriptionEventType.PAUSED,
            effective_date=date.today(),
            created_by_id=user.id if user else None,
        )
    )
    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_SUBSCRIPTION,
        entity_id=subscription.id,
        action=AuditAction.EDITED,
        user=user,
        reason="Paused",
    )
    return subscription


async def resume(
    db: AsyncSession, *, subscription: Subscription, user: Optional[User] = None
) -> Subscription:
    if subscription.status != SubscriptionStatus.PAUSED:
        raise ValueError("Only a paused subscription can be resumed")

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.paused_at = None
    # Bill from the current period, not from the date it was paused: the
    # customer got no service while it was down.
    subscription.next_billing_date = max(date.today(), subscription.current_period_start)
    db.add(subscription)
    db.add(
        SubscriptionEvent(
            subscription_id=subscription.id,
            event_type=SubscriptionEventType.RESUMED,
            effective_date=date.today(),
            created_by_id=user.id if user else None,
        )
    )
    return subscription


async def cancel(
    db: AsyncSession,
    *,
    subscription: Subscription,
    at_period_end: bool = True,
    reason: Optional[str] = None,
    user: Optional[User] = None,
) -> Subscription:
    """Ends a subscription, now or when the paid period runs out.

    Cancelling immediately credits the unused remainder - the customer has paid
    for days they will not receive, which is precisely what a credit note is.
    """
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise ValueError("That subscription is already cancelled")

    today = date.today()
    subscription.cancellation_reason = reason

    if at_period_end:
        subscription.cancel_at_period_end = True
        db.add(
            SubscriptionEvent(
                subscription_id=subscription.id,
                event_type=SubscriptionEventType.CANCELLED,
                effective_date=subscription.current_period_end,
                reason=reason,
                created_by_id=user.id if user else None,
            )
        )
    else:
        days_in_period, days_remaining, factor = _proration(subscription, today)
        refund = (
            Decimal(str(subscription.unit_price))
            * subscription.quantity
            * factor
        ).quantize(Decimal("0.01"))

        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.now(timezone.utc)
        subscription.end_date = today
        subscription.next_billing_date = None

        event = SubscriptionEvent(
            subscription_id=subscription.id,
            event_type=SubscriptionEventType.CANCELLED,
            effective_date=today,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            days_in_period=days_in_period,
            days_remaining=days_remaining,
            proration_factor=float(factor),
            proration_amount=float(-refund),
            reason=reason,
            created_by_id=user.id if user else None,
        )
        db.add(event)

        if refund > 0:
            note = await _credit_note(
                db,
                subscription=subscription,
                amount=refund,
                reason=reason or "Cancelled mid-cycle",
            )
            await db.flush()
            event.credit_note_id = note.id
            db.add(event)

    db.add(subscription)
    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_SUBSCRIPTION,
        entity_id=subscription.id,
        action=AuditAction.DELETED if not at_period_end else AuditAction.EDITED,
        user=user,
        reason=reason or ("Cancelled at period end" if at_period_end else "Cancelled"),
    )
    return subscription


async def _credit_note(
    db: AsyncSession, *, subscription: Subscription, amount: Decimal, reason: str
) -> CreditNote:
    """Records money owed back to the customer.

    Numbered under a lock: COUNT(*) alone races two concurrent downgrades into
    the same number and one of them dies on the unique index.
    """
    async with with_lock("credit-note-number", ttl=15):
        count = (
            await db.execute(select(func.count()).select_from(CreditNote))
        ).scalar_one()
        note = CreditNote(
            number=f"CN-{1000 + int(count) + 1}",
            customer_id=subscription.customer_id,
            subscription_id=subscription.id,
            amount=float(amount),
            currency=subscription.currency,
            reason=reason,
            status=CreditNoteStatus.ISSUED,
            # Set here rather than left null: a note created as ISSUED has, by
            # definition, been issued.
            issued_at=datetime.now(timezone.utc),
        )
        db.add(note)
        await db.flush()
    return note


async def events_for(
    db: AsyncSession, subscription_id: uuid.UUID
) -> Sequence[SubscriptionEvent]:
    """The proration history the billing detail screen renders."""
    result = await db.execute(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == subscription_id)
        .order_by(SubscriptionEvent.effective_date.asc(), SubscriptionEvent.created_at.asc())
    )
    return result.scalars().all()
