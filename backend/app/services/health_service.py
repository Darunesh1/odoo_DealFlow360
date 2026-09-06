"""Deal health and anomaly detection (mockup screen 14).

Three signals, each a different kind of "this deal is in trouble":

* **Stalled** - time has passed and nothing happened. The only one that needs
  a clock rather than an event, which is why the whole module runs on a
  schedule.
* **Discount anomaly** - this rep is discounting far above their own norm.
  Measured against *their* history, not a company average: a rep who sells
  enterprise deals at 14% is not an outlier, and flagging them would train
  everyone to ignore the alerts.
* **Delivery slippage** - a promise that the fulfillment reality no longer
  supports.

Alerts are idempotent per (quotation, type) while one is OPEN, so a sweep
every hour does not produce a wall of duplicates.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.cache import cached_json
from app.core.config import settings
from app.models.analytics import (
    AlertStatus,
    AlertType,
    AuditAction,
    DealHealthAlert,
    SalesRecord,
)
from app.models.fulfillment import AllocationStatus, Fulfillment, FulfillmentAllocation, FulfillmentStatus
from app.models.quotation import Quotation, QuotationStatus, RiskBand
from app.models.user import User
from app.services import audit_service

logger = logging.getLogger(__name__)

# A deal untouched for this long is stalled.
STALLED_DAYS = 7
# How long resolving an alert buys quiet before the same problem may be raised
# again. Its own knob: it used to reuse the stall window, so widening that to
# thirty days also silenced resolved alerts for thirty.
ALERT_QUIET_DAYS = 7
# How far above their own average a rep's discount has to be to count.
ANOMALY_MULTIPLE = 2.0
# Below this, "twice the average" is noise - 2% versus 1% is not a story.
ANOMALY_FLOOR_POINTS = 5.0
# How far back a rep's own average looks.
REP_AVERAGE_DAYS = 180
# Where the last sweep's timestamp lives, and how long it survives. A week,
# because a marker that expires sooner would make a quiet system look
# unswept.
LAST_SWEEP_KEY = "deal-health:last-swept"
LAST_SWEEP_TTL = 7 * 24 * 3600
# States where a deal can still stall. A confirmed order is not stalled, it is
# done being negotiated.
LIVE_STATES = {
    QuotationStatus.DRAFT,
    QuotationStatus.PENDING_APPROVAL,
    QuotationStatus.NEGOTIATION,
}


def _stalled_days() -> int:
    return int(getattr(settings, "STALLED_DEAL_DAYS", STALLED_DAYS))


_SEVERITY_ORDER = {
    RiskBand.NONE: 0,
    RiskBand.LOW: 1,
    RiskBand.MEDIUM: 2,
    RiskBand.HIGH: 3,
}


async def _suppressed(
    db: AsyncSession,
    quotation_id: uuid.UUID,
    alert_type: AlertType,
    severity: RiskBand,
) -> bool:
    """Whether this alert should stay quiet.

    An open alert of the same kind normally suppresses - re-raising hourly
    would bury the dashboard in duplicates. But only while the situation has
    not got worse: nudging an alert used to silence that pair for ever, so a
    deal idle for nine days and then ninety went on showing the same MEDIUM
    flag somebody had already waved at.

    A resolved alert buys quiet for ALERT_QUIET_DAYS. Not for ever either: a
    deal still stalled a fortnight after someone said they had dealt with it is
    genuinely worth raising again.
    """
    existing = (
        await db.execute(
            select(DealHealthAlert).where(
                DealHealthAlert.quotation_id == quotation_id,
                DealHealthAlert.alert_type == alert_type,
                DealHealthAlert.status != AlertStatus.RESOLVED,
            )
        )
    ).scalars().first()
    if existing is not None:
        worse = _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[existing.severity]
        if not worse:
            return True
        # It has escalated. Close the old one so the new one is not a duplicate
        # of something that says something milder.
        existing.status = AlertStatus.RESOLVED
        existing.acted_at = datetime.now(timezone.utc)
        existing.action_note = "Superseded - the deal got worse"
        db.add(existing)
        return False

    quiet_until = datetime.now(timezone.utc) - timedelta(
        days=int(getattr(settings, "ALERT_QUIET_DAYS", ALERT_QUIET_DAYS))
    )
    recently_resolved = (
        await db.execute(
            select(DealHealthAlert).where(
                DealHealthAlert.quotation_id == quotation_id,
                DealHealthAlert.alert_type == alert_type,
                DealHealthAlert.status == AlertStatus.RESOLVED,
                DealHealthAlert.acted_at.isnot(None),
                DealHealthAlert.acted_at > quiet_until,
            )
        )
    ).scalars().first()
    return recently_resolved is not None


async def _raise(
    db: AsyncSession,
    *,
    quotation_id: uuid.UUID,
    alert_type: AlertType,
    severity: RiskBand,
    detail: str,
) -> bool:
    """Opens an alert unless one of the same kind is already open."""
    if await _suppressed(db, quotation_id, alert_type, severity):
        return False
    db.add(
        DealHealthAlert(
            quotation_id=quotation_id,
            alert_type=alert_type,
            severity=severity,
            detail=detail,
            status=AlertStatus.OPEN,
            flagged_at=datetime.now(timezone.utc),
        )
    )
    return True


async def rep_average_discount(db: AsyncSession, rep_id: uuid.UUID) -> Optional[float]:
    """A rep's own trailing mean discount, cached for an hour.

    Read once per rep per sweep and once per dashboard load, over a table that
    only grows at confirmation time - which is exactly what a TTL cache is for.
    """

    async def load() -> Optional[float]:
        # Genuinely trailing. Without the window a rep's oldest deals weigh the
        # same as last month's, so a changed selling style never shows up.
        since = datetime.now(timezone.utc) - timedelta(days=REP_AVERAGE_DAYS)
        value = (
            await db.execute(
                select(func.avg(SalesRecord.discount_percent)).where(
                    SalesRecord.sales_rep_id == rep_id,
                    SalesRecord.sold_at >= since,
                )
            )
        ).scalar_one_or_none()
        return float(value) if value is not None else None

    return await cached_json(
        cache.NS_REPORT, f"rep-average:{rep_id}", cache.TTL_REP_AVERAGE, load
    )


async def sweep(db: AsyncSession) -> int:
    """Raises every alert the current state justifies. Returns how many."""
    raised = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_stalled_days())
    today = date.today()

    live = (
        await db.execute(
            select(Quotation).where(Quotation.status.in_(LIVE_STATES))
        )
    ).scalars().all()

    for quotation in live:
        # --- stalled ------------------------------------------------------ #
        last = quotation.last_activity_at or quotation.updated_at
        if last is not None and last < cutoff:
            idle = (now - last).days
            if await _raise(
                db,
                quotation_id=quotation.id,
                alert_type=AlertType.STALLED_DEAL,
                severity=RiskBand.MEDIUM if idle < 14 else RiskBand.HIGH,
                detail=f"Idle {idle} days",
            ):
                raised += 1

        # --- discount anomaly --------------------------------------------- #
        if quotation.owner_id and quotation.lines:
            average = await rep_average_discount(db, quotation.owner_id)
            given = max(
                (float(line.discount_percent) for line in quotation.lines),
                default=0.0,
            )
            if (
                average is not None
                and average > 0
                and given >= ANOMALY_FLOOR_POINTS
                and given >= average * ANOMALY_MULTIPLE
            ):
                # Scaled, not always HIGH: twice the average and five times
                # the average are not the same conversation.
                ratio = given / average
                severity = (
                    RiskBand.HIGH
                    if ratio >= ANOMALY_MULTIPLE * 1.5
                    else RiskBand.MEDIUM
                )
                if await _raise(
                    db,
                    quotation_id=quotation.id,
                    alert_type=AlertType.DISCOUNT_ANOMALY,
                    severity=severity,
                    # One decimal place: ":.0f" rendered 12.4% vs 6.2% as
                    # "12% vs 6%", which does not look like twice.
                    detail=(
                        f"Discount {given:.1f}% vs this rep's average "
                        f"{average:.1f}%"
                    ),
                ):
                    raised += 1

    # --- delivery slippage ------------------------------------------------ #
    promised = (
        await db.execute(
            select(Quotation, Fulfillment)
            .join(Fulfillment, Fulfillment.quotation_id == Quotation.id)
            .where(
                Quotation.promised_delivery_date.isnot(None),
                Fulfillment.status.notin_(
                    [FulfillmentStatus.FULFILLED, FulfillmentStatus.CANCELLED]
                ),
            )
        )
    ).all()

    for quotation, fulfillment in promised:
        promise = quotation.promised_delivery_date
        reason: Optional[str] = None

        if promise < today:
            reason = f"Promised {promise}, still {fulfillment.status.value}"
        else:
            # A backorder that restocks after the promise date is slippage the
            # moment it is planned, not the day the promise is missed.
            late = (
                await db.execute(
                    select(func.max(FulfillmentAllocation.expected_restock_date)).where(
                        FulfillmentAllocation.fulfillment_id == fulfillment.id,
                        FulfillmentAllocation.status == AllocationStatus.BACKORDERED,
                    )
                )
            ).scalar_one_or_none()
            if late is not None and late > promise:
                reason = f"Backorder clears {late}, promised {promise}"

        if reason and await _raise(
            db,
            quotation_id=quotation.id,
            alert_type=AlertType.DELIVERY_SLIPPAGE,
            severity=RiskBand.HIGH,
            detail=reason,
        ):
            raised += 1

    # Always commit, even when nothing new was raised: `_suppressed` resolves a
    # superseded alert on its way to returning False, and committing only when
    # `raised` silently rolled that write back.
    await cache.set_value(
        cache.NS_REPORT, LAST_SWEEP_KEY, now.isoformat(), LAST_SWEEP_TTL
    )
    await db.commit()
    return raised


async def last_swept_at() -> Optional[str]:
    """When the sweep last ran, or None if it never has here.

    What separates "nothing is at risk" from "nobody has looked yet" - two
    states the screen used to render identically.
    """
    return await cache.get_value(cache.NS_REPORT, LAST_SWEEP_KEY)


async def list_alerts(
    db: AsyncSession, *, status: Optional[AlertStatus] = None, limit: int = 100
) -> Sequence[DealHealthAlert]:
    stmt = select(DealHealthAlert).order_by(DealHealthAlert.flagged_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(DealHealthAlert.status == status)
    else:
        stmt = stmt.where(DealHealthAlert.status != AlertStatus.RESOLVED)
    return (await db.execute(stmt)).scalars().all()


async def counts(
    db: AsyncSession, *, owner_id: Optional[uuid.UUID] = None
) -> dict[str, int]:
    """The three tiles at the top of the deal health dashboard.

    `owner_id` scopes them the way `GET /alerts` scopes its rows, so a rep's
    tiles agree with the table underneath rather than counting the whole
    company's flags.
    """
    stmt = (
        select(DealHealthAlert.alert_type, func.count())
        .where(DealHealthAlert.status != AlertStatus.RESOLVED)
        .group_by(DealHealthAlert.alert_type)
    )
    if owner_id is not None:
        stmt = stmt.join(
            Quotation, DealHealthAlert.quotation_id == Quotation.id
        ).where(Quotation.owner_id == owner_id)
    rows = (await db.execute(stmt)).all()
    result = {alert_type.value: 0 for alert_type in AlertType}
    for alert_type, count in rows:
        result[alert_type.value] = int(count)
    return result


async def act(
    db: AsyncSession,
    *,
    alert: DealHealthAlert,
    action: AlertStatus,
    user: Optional[User] = None,
    note: Optional[str] = None,
) -> DealHealthAlert:
    """Nudge, escalate or resolve. All three are the same shape of write."""
    if alert.status == AlertStatus.RESOLVED:
        raise ValueError("That alert is already resolved")

    alert.status = action
    alert.acted_by_id = user.id if user else None
    alert.acted_at = datetime.now(timezone.utc)
    alert.action_note = note
    db.add(alert)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_ALERT,
        entity_id=alert.id,
        action=AuditAction.EDITED,
        user=user,
        reason=note or action.value,
        context={"alert_type": alert.alert_type.value},
    )
    return alert
