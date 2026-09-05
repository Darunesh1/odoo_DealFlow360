"""The customer portal (mockup screen 11).

A genuinely separate, restricted surface, as section 7 of the spec requires.
Three things enforce that and are worth stating plainly:

1. The router guard admits **only** ``Role.CUSTOMER``. An admin browsing here
   gets a 403, not a god view - the portal is not an internal screen.
2. Every query is filtered by ``current_user.customer_id``. A customer cannot
   name another customer's quotation id, and an unknown id answers 404 rather
   than 403, so the portal is not an existence oracle either.
3. The response schemas have nowhere to put cost, margin, risk score or the
   approval chain. Leaking them would take a code change, not a slip.
"""

from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.models.billing import Invoice
from app.models.quotation import Quotation, QuotationStatus
from app.models.user import Role, User
from app.schemas.portal import (
    ChangeRequestInput,
    CommentInput,
    PortalChangeRequest,
    PortalComment,
    PortalInvoiceRow,
    PortalLine,
    PortalQuotation,
    PortalQuotationRow,
)
from app.services import negotiation_service, order_service
from app.services.quotation_service import ensure_quotation_loaded

router = APIRouter(dependencies=[Depends(require_roles(Role.CUSTOMER))])

# What a customer may see. A draft is not theirs to look at, and a rejected or
# cancelled quotation is not something to show them at all.
VISIBLE = {
    QuotationStatus.PENDING_APPROVAL,
    QuotationStatus.APPROVED,
    QuotationStatus.NEGOTIATION,
    QuotationStatus.CONFIRMED,
}


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found"
    )


def _no_account() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This login is not attached to a customer account yet.",
    )


async def _own_quotation(
    db: AsyncSession, quotation_id: uuid.UUID, user: User
) -> Quotation:
    """Loads a quotation only if it belongs to the caller's company.

    The customer_id filter is what makes the id in the URL untrusted input
    rather than an authorisation decision.
    """
    if user.customer_id is None:
        raise _no_account()
    try:
        quotation = await ensure_quotation_loaded(db, quotation_id)
    except ValueError:
        raise _not_found()
    if quotation.customer_id != user.customer_id or quotation.status not in VISIBLE:
        raise _not_found()
    return quotation


@router.get("/portal/quotations", response_model=List[PortalQuotationRow])
async def read_my_quotations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    if current_user.customer_id is None:
        raise _no_account()
    rows = (
        await db.execute(
            select(Quotation)
            .where(
                Quotation.customer_id == current_user.customer_id,
                Quotation.status.in_(VISIBLE),
            )
            .order_by(Quotation.updated_at.desc())
        )
    ).scalars().all()
    return [
        PortalQuotationRow(
            id=row.id,
            number=row.number,
            status=row.status,
            currency=row.currency,
            total=float(row.total),
            valid_until=row.valid_until,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


async def _detail(db: AsyncSession, quotation: Quotation) -> PortalQuotation:
    comments = await negotiation_service.comments_for(db, quotation.id)
    requests = await negotiation_service.change_requests_for(db, quotation.id)
    open_request = any(request.status.value == "open" for request in requests)

    return PortalQuotation(
        id=quotation.id,
        number=quotation.number,
        status=quotation.status,
        currency=quotation.currency,
        total=float(quotation.total),
        valid_until=quotation.valid_until,
        updated_at=quotation.updated_at,
        customer_name=quotation.customer.name,
        subtotal=float(quotation.subtotal),
        discount_total=float(quotation.discount_total),
        tax_total=float(quotation.tax_total),
        order_discount_percent=float(quotation.order_discount_percent),
        requested_delivery_date=quotation.requested_delivery_date,
        promised_delivery_date=quotation.promised_delivery_date,
        notes=quotation.notes,
        lines=[
            PortalLine(
                id=line.id,
                product_name=line.product_name,
                variant_name=(
                    line.variant_name if line.variant_name != "Default" else None
                ),
                quantity=line.quantity,
                unit_price=float(line.unit_price),
                discount_percent=float(line.discount_percent),
                line_total=float(line.line_total),
                is_recurring=line.is_recurring,
                recurring_interval=line.recurring_interval,
            )
            for line in quotation.lines
        ],
        comments=[PortalComment.model_validate(comment) for comment in comments],
        change_requests=[
            PortalChangeRequest.model_validate(request) for request in requests
        ],
        can_negotiate=quotation.status in negotiation_service.NEGOTIABLE
        and not open_request,
        # Confirming while a counter is still open would be ambiguous: which
        # terms did they just agree to?
        can_confirm=quotation.status == QuotationStatus.APPROVED and not open_request,
    )


@router.get("/portal/quotations/{quotation_id}", response_model=PortalQuotation)
async def read_my_quotation(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    quotation = await _own_quotation(db, quotation_id, current_user)
    return await _detail(db, quotation)


@router.post(
    "/portal/quotations/{quotation_id}/comments",
    response_model=PortalQuotation,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    quotation_id: uuid.UUID,
    body: CommentInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """A line-level question or comment. Forced non-internal."""
    quotation = await _own_quotation(db, quotation_id, current_user)
    try:
        await negotiation_service.add_comment(
            db,
            quotation=quotation,
            author=current_user,
            body=body.body,
            line_id=body.quotation_line_id,
            is_internal=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation_id)
    return await _detail(db, quotation)


@router.post(
    "/portal/quotations/{quotation_id}/change-requests",
    response_model=PortalQuotation,
    status_code=status.HTTP_201_CREATED,
)
async def request_changes(
    quotation_id: uuid.UUID,
    body: ChangeRequestInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """The counter-offer. Moves the deal into negotiation and tells the rep."""
    quotation = await _own_quotation(db, quotation_id, current_user)
    try:
        await negotiation_service.open_change_request(
            db,
            quotation=quotation,
            requested_by=current_user,
            counter_discount_percent=body.counter_discount_percent,
            requested_delivery_date=body.requested_delivery_date,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    await db.commit()

    from app.services.portal_notifications import notify_change_requested

    await notify_change_requested(db, quotation=quotation)

    quotation = await ensure_quotation_loaded(db, quotation_id)
    return await _detail(db, quotation)


@router.post("/portal/quotations/{quotation_id}/confirm", response_model=PortalQuotation)
async def confirm_my_quotation(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """"Confirm Quotation" - the customer accepting the terms as they stand.

    Runs exactly the same confirmation the rep's own button runs, so an order
    confirmed from the portal reserves stock and opens subscriptions
    identically. There is no second, weaker path.
    """
    quotation = await _own_quotation(db, quotation_id, current_user)
    try:
        await order_service.confirm_quotation(
            db, quotation=quotation, user=current_user
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    quotation = await ensure_quotation_loaded(db, quotation_id)
    return await _detail(db, quotation)


@router.get("/portal/invoices", response_model=List[PortalInvoiceRow])
async def read_my_invoices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    if current_user.customer_id is None:
        raise _no_account()
    rows = (
        await db.execute(
            select(Invoice)
            .where(Invoice.customer_id == current_user.customer_id)
            .order_by(Invoice.issue_date.desc())
        )
    ).scalars().all()
    return [
        PortalInvoiceRow(
            id=row.id,
            number=row.number,
            status=row.status.value,
            issue_date=row.issue_date,
            due_date=row.due_date,
            currency=row.currency,
            total=float(row.total),
            amount_paid=float(row.amount_paid),
        )
        for row in rows
    ]
