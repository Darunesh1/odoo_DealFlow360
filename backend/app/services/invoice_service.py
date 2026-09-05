"""Invoicing.

Two invariants the schema already enforces and this module must not try to
work around:

* **Nothing is billed before it ships.** A ONE_TIME invoice line has to point
  at a shipment line, and a shipment line's ``quantity_invoiced`` cannot exceed
  its ``quantity_shipped``. Partial delivery therefore drives partial
  invoicing by construction.
* **One recurring charge per subscription per period, ever.** A partial unique
  index on ``(subscription_id, service_period_start)`` means a retried task or
  a duplicate scheduler tick raises rather than double-bills.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import LockNotAcquired, with_lock
from app.models.analytics import AuditAction
from app.models.billing import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceLineType,
    InvoiceStatus,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from app.models.fulfillment import Shipment, ShipmentLine
from app.models.quotation import Quotation, QuotationLine
from app.models.user import User
from app.services import audit_service, order_service

logger = logging.getLogger(__name__)

# How long a customer has to pay. One setting rather than per-customer terms,
# which the spec never asks for.
PAYMENT_TERMS_DAYS = 30


async def get_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> Optional[Invoice]:
    """Re-reads an invoice with its lines loaded.

    Lines are written by foreign key rather than appended to the collection,
    so the object that created them has an unloaded `lines` - and under
    asyncpg reading that is a MissingGreenlet, not a query. Every function
    here returns an invoice through this.
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def _next_number(db: AsyncSession) -> str:
    """INV-1042, continuing from whatever exists.

    Read under the caller's lock; a sequence would be tidier but would make the
    numbers jump on every rolled-back attempt.
    """
    count = (await db.execute(select(func.count()).select_from(Invoice))).scalar_one()
    return f"INV-{1000 + int(count) + 1}"


def _money(value: Decimal | float) -> float:
    return float(round(Decimal(str(value)), 2))


def _total_up(invoice: Invoice, lines: Sequence[InvoiceLine]) -> None:
    subtotal = sum(Decimal(str(line.line_subtotal)) for line in lines)
    tax = sum(Decimal(str(line.tax_amount)) for line in lines)
    invoice.subtotal = _money(subtotal)
    invoice.tax_total = _money(tax)
    invoice.total = _money(subtotal + tax)


async def invoice_shipped(
    db: AsyncSession, *, quotation: Quotation, user: Optional[User] = None
) -> Optional[Invoice]:
    """Bills the one-time units that have actually left the building.

    Returns None when nothing new has shipped, which is the ordinary case for a
    second click rather than an error.
    """
    async with with_lock(f"invoice:{quotation.id}", ttl=60):
        rows = (
            await db.execute(
                select(ShipmentLine, QuotationLine)
                .join(QuotationLine, ShipmentLine.quotation_line_id == QuotationLine.id)
                .join(Shipment, ShipmentLine.shipment_id == Shipment.id)
                .where(
                    QuotationLine.quotation_id == quotation.id,
                    ShipmentLine.quantity_invoiced < ShipmentLine.quantity_shipped,
                )
                .order_by(QuotationLine.position)
            )
        ).all()
        if not rows:
            return None

        today = date.today()
        invoice = Invoice(
            number=await _next_number(db),
            customer_id=quotation.customer_id,
            quotation_id=quotation.id,
            kind=InvoiceKind.ONE_TIME,
            status=InvoiceStatus.UNPAID,
            issue_date=today,
            due_date=today + timedelta(days=PAYMENT_TERMS_DAYS),
            currency=quotation.currency,
        )
        db.add(invoice)
        await db.flush()

        lines: list[InvoiceLine] = []
        for position, (shipment_line, quotation_line) in enumerate(rows, start=1):
            quantity = shipment_line.quantity_shipped - shipment_line.quantity_invoiced
            unit_price = Decimal(str(quotation_line.unit_price)) * (
                Decimal("1") - Decimal(str(quotation_line.discount_percent)) / 100
            )
            subtotal = unit_price * quantity
            tax = subtotal * Decimal(str(quotation_line.tax_percent)) / 100

            line = InvoiceLine(
                invoice_id=invoice.id,
                line_type=InvoiceLineType.ONE_TIME,
                description=quotation_line.product_name,
                product_id=quotation_line.product_id,
                variant_id=quotation_line.variant_id,
                quotation_line_id=quotation_line.id,
                shipment_line_id=shipment_line.id,
                quantity=quantity,
                unit_price=_money(unit_price),
                discount_percent=float(quotation_line.discount_percent),
                tax_percent=float(quotation_line.tax_percent),
                tax_amount=_money(tax),
                line_subtotal=_money(subtotal),
                line_total=_money(subtotal + tax),
                sort_order=position,
            )
            db.add(line)
            lines.append(line)

            # Marks these units billed, so a second run bills nothing.
            shipment_line.quantity_invoiced += quantity
            db.add(shipment_line)

        _total_up(invoice, lines)
        db.add(invoice)

        audit_service.record(
            db,
            entity_type=audit_service.ENTITY_INVOICE,
            entity_id=invoice.id,
            action=AuditAction.CREATED,
            user=user,
            reason=f"Invoiced {len(lines)} shipped line(s)",
            context={"number": invoice.number, "total": invoice.total},
        )
        await db.commit()

    return await get_invoice(db, invoice.id)


async def bill_subscription(
    db: AsyncSession, *, subscription: Subscription, on: Optional[date] = None
) -> Optional[Invoice]:
    """Issues one recurring invoice for the subscription's current period.

    Any prorations still waiting on an invoice are swept onto the same one -
    the nullable ``resulting_invoice_id`` on the event *is* the pending queue,
    so there is no queue table and no job state.
    """
    today = on or date.today()
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end

    invoice = Invoice(
        number=await _next_number(db),
        customer_id=subscription.customer_id,
        quotation_id=subscription.quotation_id,
        subscription_id=subscription.id,
        kind=InvoiceKind.RECURRING,
        status=InvoiceStatus.UNPAID,
        issue_date=today,
        due_date=today + timedelta(days=PAYMENT_TERMS_DAYS),
        currency=subscription.currency,
    )
    db.add(invoice)
    await db.flush()

    unit_price = Decimal(str(subscription.unit_price))
    subtotal = unit_price * subscription.quantity
    lines = [
        InvoiceLine(
            invoice_id=invoice.id,
            line_type=InvoiceLineType.RECURRING,
            description=f"{subscription.plan_name} ({period_start} – {period_end})",
            product_id=subscription.product_id,
            variant_id=subscription.variant_id,
            subscription_id=subscription.id,
            service_period_start=period_start,
            service_period_end=period_end,
            quantity=subscription.quantity,
            unit_price=_money(unit_price),
            line_subtotal=_money(subtotal),
            line_total=_money(subtotal),
            sort_order=1,
        )
    ]
    db.add(lines[0])

    pending = (
        await db.execute(
            select(SubscriptionEvent).where(
                SubscriptionEvent.subscription_id == subscription.id,
                SubscriptionEvent.resulting_invoice_id.is_(None),
                SubscriptionEvent.proration_amount.isnot(None),
            )
        )
    ).scalars().all()

    for position, event in enumerate(pending, start=2):
        amount = Decimal(str(event.proration_amount))
        if amount == 0:
            continue
        charge = amount > 0
        line = InvoiceLine(
            invoice_id=invoice.id,
            line_type=(
                InvoiceLineType.PRORATION_CHARGE
                if charge
                else InvoiceLineType.PRORATION_CREDIT
            ),
            description=(
                f"{'Additional' if charge else 'Credit for'} "
                f"{subscription.plan_name} — {event.effective_date} to {event.period_end}"
            ),
            product_id=subscription.product_id,
            subscription_id=subscription.id,
            service_period_start=event.effective_date,
            service_period_end=event.period_end,
            quantity=1,
            unit_price=_money(amount),
            line_subtotal=_money(amount),
            line_total=_money(amount),
            sort_order=position,
        )
        db.add(line)
        await db.flush()
        lines.append(line)
        event.resulting_invoice_id = invoice.id
        event.resulting_invoice_line_id = line.id
        db.add(event)

    _total_up(invoice, lines)
    db.add(invoice)

    # Roll the period forward. Doing it here rather than in the scheduler means
    # a period can never be billed without also being advanced.
    subscription.current_period_start = period_end
    subscription.current_period_end = order_service.advance(
        period_end, subscription.interval, subscription.interval_count
    )
    subscription.next_billing_date = period_end
    if subscription.cancel_at_period_end:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.now(timezone.utc)
        subscription.next_billing_date = None
    db.add(subscription)
    await db.flush()

    return await get_invoice(db, invoice.id)


async def bill_due_subscriptions(
    db: AsyncSession, on: Optional[date] = None
) -> int:
    """The daily run. Bills every active subscription whose date has arrived.

    One transaction per subscription: a single bad row must not stop the rest
    of the book from being billed.
    """
    today = on or date.today()
    due = (
        await db.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_billing_date.isnot(None),
                Subscription.next_billing_date <= today,
            )
        )
    ).scalars().all()

    issued = 0
    for subscription in due:
        try:
            async with with_lock(f"bill:{subscription.id}", ttl=60):
                await bill_subscription(db, subscription=subscription, on=today)
                await db.commit()
            issued += 1
        except IntegrityError:
            # The partial unique index caught a period already billed. Exactly
            # what it is there for; skip and carry on.
            await db.rollback()
            logger.info(
                f"Subscription {subscription.id} already billed for this period"
            )
        except LockNotAcquired:
            logger.info(f"Subscription {subscription.id} is being billed elsewhere")
        except Exception as exc:
            await db.rollback()
            logger.warning(f"Billing {subscription.id} failed: {exc}")

    return issued


async def list_invoices(
    db: AsyncSession,
    *,
    customer_id: Optional[uuid.UUID] = None,
    quotation_id: Optional[uuid.UUID] = None,
    status: Optional[InvoiceStatus] = None,
) -> Sequence[Invoice]:
    stmt = select(Invoice).order_by(Invoice.issue_date.desc(), Invoice.number.desc())
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if quotation_id:
        stmt = stmt.where(Invoice.quotation_id == quotation_id)
    if status:
        stmt = stmt.where(Invoice.status == status)
    return (await db.execute(stmt)).scalars().all()
