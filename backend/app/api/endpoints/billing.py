"""Subscriptions, invoices and payments (mockup screens 9, 10, 12 and 13).

Finance owns the writes - "reconciles recurring billing and credit notes" is
their line in the spec. Sales roles read, so a rep can answer "has my customer
been invoiced yet?" without asking anyone.
"""

from datetime import date
from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, get_db, get_pagination, require_roles
from app.models.billing import (
    CreditNote,
    CreditNoteStatus,
    Invoice,
    InvoiceLine,
    InvoiceLineType,
    InvoiceStatus,
    Subscription,
    SubscriptionStatus,
)
from app.models.customer import Customer
from app.models.fulfillment import Fulfillment, FulfillmentStatus
from app.models.quotation import Quotation, QuotationStatus
from app.models.user import Role, User
from app.schemas.billing import (
    ApplyCreditNoteInput,
    CancelInput,
    CreditNoteCounts,
    CreditNoteRead,
    InvoiceCounts,
    InvoiceDetail,
    InvoiceLineRead,
    InvoiceRow,
    OneTimeLineRead,
    PaymentRead,
    QuantityChangeInput,
    RecordPaymentInput,
    SubscriptionCounts,
    SubscriptionDetail,
    SubscriptionEventRead,
    SubscriptionRow,
    UpcomingBill,
)
from app.schemas.common import Page
from app.services import (
    invoice_service,
    order_service,
    payment_service,
    subscription_service,
)
from app.services.quotation_service import ensure_quotation_loaded

router = APIRouter(
    dependencies=[
        Depends(
            require_roles(
                Role.ADMIN, Role.FINANCE, Role.SALES_MANAGER, Role.SALES_REP
            )
        )
    ]
)

require_finance = require_roles(Role.ADMIN, Role.FINANCE)

UPCOMING_PERIODS = 6


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _missing(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found"
    )


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #

async def _subscription_row(
    db: AsyncSession, subscription: Subscription
) -> SubscriptionRow:
    customer = await db.get(Customer, subscription.customer_id)
    quotation = await db.get(Quotation, subscription.quotation_id)
    return SubscriptionRow(
        id=subscription.id,
        customer_id=subscription.customer_id,
        customer_name=customer.name if customer else "—",
        quotation_id=subscription.quotation_id,
        quotation_number=quotation.number if quotation else "—",
        plan_name=subscription.plan_name,
        interval=subscription.interval,
        quantity=subscription.quantity,
        unit_price=float(subscription.unit_price),
        currency=subscription.currency,
        status=subscription.status,
        start_date=subscription.start_date,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        next_billing_date=subscription.next_billing_date,
        cancel_at_period_end=subscription.cancel_at_period_end,
    )


@router.get("/subscriptions", response_model=Page[SubscriptionRow])
async def read_subscriptions(
    db: AsyncSession = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    status_filter: Optional[SubscriptionStatus] = Query(default=None, alias="status"),
) -> Any:
    """Screen 9: every recurring plan, whichever order it came from."""
    rows = await subscription_service.list_subscriptions(db, status=status_filter)
    page = rows[pagination.skip : pagination.skip + pagination.limit]
    return Page[SubscriptionRow](
        items=[await _subscription_row(db, row) for row in page],
        total=len(rows),
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(len(rows)),
    )


@router.get("/subscriptions/counts", response_model=SubscriptionCounts)
async def read_subscription_counts(db: AsyncSession = Depends(get_db)) -> Any:
    return SubscriptionCounts(**await subscription_service.counts(db))


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionDetail)
async def read_subscription(
    subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    """Screen 10: one-time lines and recurring lines from the same order, shown
    separately, plus the schedule ahead and the proration history."""
    subscription = await subscription_service.get(db, subscription_id)
    if subscription is None:
        raise _missing("Subscription")

    try:
        quotation = await ensure_quotation_loaded(db, subscription.quotation_id)
    except ValueError:
        raise _missing("Quotation")

    one_time = [
        OneTimeLineRead(
            id=line.id,
            description=line.product_name,
            quantity=line.quantity,
            unit_price=float(line.unit_price),
            amount=float(line.line_total),
        )
        for line in quotation.lines
        if not line.is_recurring
    ]

    siblings = await subscription_service.list_subscriptions(db)
    recurring = [
        await _subscription_row(db, row)
        for row in siblings
        if row.quotation_id == subscription.quotation_id
    ]

    # Projected, not materialised. Future periods are arithmetic; storing them
    # would create rows that a cancellation then has to go and delete.
    upcoming: list[UpcomingBill] = []
    period_start = subscription.current_period_start
    amount = float(subscription.unit_price) * subscription.quantity
    if subscription.status == SubscriptionStatus.ACTIVE:
        for _ in range(UPCOMING_PERIODS):
            period_end = order_service.advance(
                period_start, subscription.interval, subscription.interval_count
            )
            upcoming.append(
                UpcomingBill(
                    period_start=period_start,
                    period_end=period_end,
                    amount=round(amount, 2),
                )
            )
            period_start = period_end

    events = await subscription_service.events_for(db, subscription_id)

    return SubscriptionDetail(
        **(await _subscription_row(db, subscription)).model_dump(),
        one_time_lines=one_time,
        recurring_lines=recurring,
        upcoming=upcoming,
        events=[SubscriptionEventRead.model_validate(event) for event in events],
    )


@router.post(
    "/subscriptions/{subscription_id}/quantity",
    response_model=SubscriptionDetail,
    dependencies=[Depends(require_finance)],
)
async def change_subscription_quantity(
    subscription_id: uuid.UUID,
    body: QuantityChangeInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """A mid-cycle quantity change, prorated for the unused remainder."""
    subscription = await subscription_service.get(db, subscription_id)
    if subscription is None:
        raise _missing("Subscription")
    try:
        await subscription_service.change_quantity(
            db,
            subscription=subscription,
            new_quantity=body.quantity,
            effective=body.effective_date,
            reason=body.reason,
            user=current_user,
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await read_subscription(subscription_id, db=db)


@router.post(
    "/subscriptions/{subscription_id}/pause",
    response_model=SubscriptionDetail,
    dependencies=[Depends(require_finance)],
)
async def pause_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    subscription = await subscription_service.get(db, subscription_id)
    if subscription is None:
        raise _missing("Subscription")
    try:
        await subscription_service.pause(
            db, subscription=subscription, user=current_user
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await read_subscription(subscription_id, db=db)


@router.post(
    "/subscriptions/{subscription_id}/resume",
    response_model=SubscriptionDetail,
    dependencies=[Depends(require_finance)],
)
async def resume_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    subscription = await subscription_service.get(db, subscription_id)
    if subscription is None:
        raise _missing("Subscription")
    try:
        await subscription_service.resume(
            db, subscription=subscription, user=current_user
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await read_subscription(subscription_id, db=db)


@router.post(
    "/subscriptions/{subscription_id}/cancel",
    response_model=SubscriptionDetail,
    dependencies=[Depends(require_finance)],
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    body: CancelInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Cancelling immediately credits the days the customer paid for and will
    not receive."""
    subscription = await subscription_service.get(db, subscription_id)
    if subscription is None:
        raise _missing("Subscription")
    try:
        await subscription_service.cancel(
            db,
            subscription=subscription,
            at_period_end=body.at_period_end,
            reason=body.reason,
            user=current_user,
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await read_subscription(subscription_id, db=db)


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #

async def _invoice_row(db: AsyncSession, invoice: Invoice) -> InvoiceRow:
    customer = await db.get(Customer, invoice.customer_id)
    quotation = (
        await db.get(Quotation, invoice.quotation_id) if invoice.quotation_id else None
    )
    return InvoiceRow(
        id=invoice.id,
        number=invoice.number,
        customer_id=invoice.customer_id,
        customer_name=customer.name if customer else "—",
        quotation_id=invoice.quotation_id,
        quotation_number=quotation.number if quotation else None,
        kind=invoice.kind,
        status=invoice.status,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        total=float(invoice.total),
        amount_paid=float(invoice.amount_paid),
        paid_at=invoice.paid_at,
    )


@router.get("/invoices", response_model=Page[InvoiceRow])
async def read_invoices(
    db: AsyncSession = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    status_filter: Optional[InvoiceStatus] = Query(default=None, alias="status"),
) -> Any:
    """Screen 12: every invoice from one-time and recurring orders alike."""
    rows = await invoice_service.list_invoices(db, status=status_filter)
    page = rows[pagination.skip : pagination.skip + pagination.limit]
    return Page[InvoiceRow](
        items=[await _invoice_row(db, invoice) for invoice in page],
        total=len(rows),
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(len(rows)),
    )


@router.get("/invoices/counts", response_model=InvoiceCounts)
async def read_invoice_counts(db: AsyncSession = Depends(get_db)) -> Any:
    rows = (
        await db.execute(select(Invoice.status, func.count()).group_by(Invoice.status))
    ).all()
    counts = {status_.value: int(count) for status_, count in rows}
    return InvoiceCounts(
        unpaid=counts.get("unpaid", 0),
        partially_paid=counts.get("partially_paid", 0),
        paid=counts.get("paid", 0),
        draft=counts.get("draft", 0),
        void=counts.get("void", 0),
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def read_invoice(
    invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    """Screen 13: the lifecycle strip, the lines, and the payment trail."""
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None:
        raise _missing("Invoice")

    lines = (
        await db.execute(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.sort_order)
        )
    ).scalars().all()
    payments = await payment_service.payments_for(db, invoice.id)

    # The strip is derived from what actually happened to the order, not from a
    # status column that could disagree with it.
    confirmed = shipped = False
    related: list[InvoiceRow] = []
    if invoice.quotation_id:
        quotation = await db.get(Quotation, invoice.quotation_id)
        confirmed = quotation is not None and quotation.status == QuotationStatus.CONFIRMED
        fulfillment = (
            await db.execute(
                select(Fulfillment).where(Fulfillment.quotation_id == invoice.quotation_id)
            )
        ).scalars().first()
        shipped = fulfillment is not None and fulfillment.status in {
            FulfillmentStatus.PARTIALLY_SHIPPED,
            FulfillmentStatus.FULFILLED,
        }
        siblings = await invoice_service.list_invoices(
            db, quotation_id=invoice.quotation_id
        )
        related = [
            await _invoice_row(db, sibling)
            for sibling in siblings
            if sibling.id != invoice.id
        ]

    return InvoiceDetail(
        **(await _invoice_row(db, invoice)).model_dump(),
        lines=[InvoiceLineRead.model_validate(line) for line in lines],
        payments=[PaymentRead.model_validate(payment) for payment in payments],
        order_confirmed=confirmed,
        order_shipped=shipped,
        order_invoiced=True,
        order_paid=invoice.status == InvoiceStatus.PAID,
        related=related,
    )


@router.post(
    "/quotations/{quotation_id}/invoice",
    response_model=Optional[InvoiceDetail],
    dependencies=[Depends(require_finance)],
)
async def invoice_order(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Bills whatever has shipped and is not yet on an invoice.

    Answers null when nothing new has shipped - the ordinary outcome of a
    second click, not an error.
    """
    try:
        quotation = await ensure_quotation_loaded(db, quotation_id)
    except ValueError:
        raise _missing("Quotation")
    invoice = await invoice_service.invoice_shipped(
        db, quotation=quotation, user=current_user
    )
    if invoice is None:
        return None
    return await read_invoice(invoice.id, db=db)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=InvoiceDetail,
    dependencies=[Depends(require_finance)],
)
async def record_payment(
    invoice_id: uuid.UUID,
    body: RecordPaymentInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Screen 13's Record Payment."""
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None:
        raise _missing("Invoice")
    try:
        await payment_service.record_payment(
            db,
            invoice=invoice,
            amount=body.amount,
            method=body.method,
            reference=body.reference,
            received_on=body.received_on,
            is_refund=body.is_refund,
            note=body.note,
            user=current_user,
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await read_invoice(invoice_id, db=db)


# --------------------------------------------------------------------------- #
# Credit notes
# --------------------------------------------------------------------------- #

async def _credit_note_row(db: AsyncSession, note: CreditNote) -> CreditNoteRead:
    customer = await db.get(Customer, note.customer_id)
    subscription = (
        await db.get(Subscription, note.subscription_id)
        if note.subscription_id
        else None
    )
    invoice = await db.get(Invoice, note.invoice_id) if note.invoice_id else None
    return CreditNoteRead(
        id=note.id,
        number=note.number,
        customer_id=note.customer_id,
        customer_name=customer.name if customer else "—",
        amount=float(note.amount),
        currency=note.currency,
        reason=note.reason,
        status=note.status,
        issued_at=note.issued_at,
        subscription_id=note.subscription_id,
        plan_name=subscription.plan_name if subscription else None,
        invoice_id=note.invoice_id,
        invoice_number=invoice.number if invoice else None,
    )


@router.get("/credit-notes", response_model=List[CreditNoteRead])
async def read_credit_notes(
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[CreditNoteStatus] = Query(default=None, alias="status"),
) -> Any:
    """What the business owes back, and why.

    Written by downgrades and mid-cycle cancellations. Until now they were
    created and never shown anywhere, so Finance could not reconcile them.
    """
    stmt = select(CreditNote).order_by(CreditNote.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(CreditNote.status == status_filter)
    notes = (await db.execute(stmt)).scalars().all()
    return [await _credit_note_row(db, note) for note in notes]


@router.get("/credit-notes/counts", response_model=CreditNoteCounts)
async def read_credit_note_counts(db: AsyncSession = Depends(get_db)) -> Any:
    rows = (
        await db.execute(
            select(CreditNote.status, func.count(), func.coalesce(func.sum(CreditNote.amount), 0))
            .group_by(CreditNote.status)
        )
    ).all()
    counts = {status_: (int(n), float(total)) for status_, n, total in rows}
    return CreditNoteCounts(
        issued=counts.get(CreditNoteStatus.ISSUED, (0, 0))[0],
        applied=counts.get(CreditNoteStatus.APPLIED, (0, 0))[0],
        cancelled=counts.get(CreditNoteStatus.CANCELLED, (0, 0))[0],
        # Only unapplied notes are money still owed.
        outstanding_amount=round(counts.get(CreditNoteStatus.ISSUED, (0, 0))[1], 2),
    )


@router.post(
    "/credit-notes/{note_id}/apply",
    response_model=CreditNoteRead,
    dependencies=[Depends(require_finance)],
)
async def apply_credit_note(
    note_id: uuid.UUID,
    body: ApplyCreditNoteInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Settles part of an invoice with credit the customer is already owed."""
    note = await db.get(CreditNote, note_id)
    if note is None:
        raise _missing("Credit note")
    invoice = await db.get(Invoice, body.invoice_id)
    if invoice is None:
        raise _missing("Invoice")

    try:
        await payment_service.apply_credit_note(
            db, note=note, invoice=invoice, user=current_user
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    return await _credit_note_row(db, note)
