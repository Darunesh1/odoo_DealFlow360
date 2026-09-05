"""Recording money against an invoice (mockup screen 13).

Manual only - a person enters what arrived, from where, and when. There is no
gateway, and an invoice's ``amount_paid`` is never typed: it is always the
signed sum of its payments, recomputed after every write, so the two can never
disagree.
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AuditAction
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentMethod
from app.models.user import User
from app.services import audit_service


async def payments_for(db: AsyncSession, invoice_id: uuid.UUID) -> Sequence[Payment]:
    result = await db.execute(
        select(Payment)
        .where(Payment.invoice_id == invoice_id)
        .order_by(Payment.received_at.asc())
    )
    return result.scalars().all()


async def record_payment(
    db: AsyncSession,
    *,
    invoice: Invoice,
    amount: float,
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER,
    reference: Optional[str] = None,
    received_on: Optional[date] = None,
    is_refund: bool = False,
    note: Optional[str] = None,
    user: Optional[User] = None,
) -> Payment:
    """Records one receipt or refund and re-derives the invoice's status."""
    if invoice.status == InvoiceStatus.VOID:
        raise ValueError("A void invoice cannot take a payment")
    if amount <= 0:
        # is_refund carries the direction; the amount is always positive.
        raise ValueError("Enter an amount greater than zero")

    outstanding = Decimal(str(invoice.total)) - Decimal(str(invoice.amount_paid))
    if not is_refund and Decimal(str(amount)) > outstanding:
        raise ValueError(
            f"That is more than the {outstanding:.2f} outstanding on this invoice"
        )
    if is_refund and Decimal(str(amount)) > Decimal(str(invoice.amount_paid)):
        raise ValueError("You cannot refund more than has been paid")

    received_at = datetime.combine(
        received_on or date.today(), time(12, 0), tzinfo=timezone.utc
    )
    payment = Payment(
        invoice_id=invoice.id,
        is_refund=is_refund,
        amount=amount,
        currency=invoice.currency,
        method=method,
        reference=reference,
        received_at=received_at,
        recorded_by_id=user.id if user else None,
        note=note,
    )
    db.add(payment)
    await db.flush()

    await _resettle(db, invoice)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_INVOICE,
        entity_id=invoice.id,
        action=AuditAction.EDITED,
        user=user,
        reason=f"{'Refund' if is_refund else 'Payment'} of {amount:.2f} recorded",
        context={
            "method": method.value,
            "reference": reference,
            "status": invoice.status.value,
        },
    )
    return payment


async def _resettle(db: AsyncSession, invoice: Invoice) -> None:
    """Re-derives amount_paid and the status from the payment list.

    Recomputed rather than incremented: an incremented total drifts the first
    time a write is retried, and drift here is money that does not add up.
    """
    paid = Decimal("0")
    for payment in await payments_for(db, invoice.id):
        amount = Decimal(str(payment.amount))
        paid += -amount if payment.is_refund else amount

    invoice.amount_paid = float(round(paid, 2))
    total = Decimal(str(invoice.total))

    if paid <= 0:
        invoice.status = InvoiceStatus.UNPAID
        invoice.paid_at = None
    elif paid >= total:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = invoice.paid_at or datetime.now(timezone.utc)
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
        invoice.paid_at = None

    db.add(invoice)
