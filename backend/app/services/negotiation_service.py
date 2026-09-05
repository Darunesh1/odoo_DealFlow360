"""Customer negotiation, and the re-approval it triggers (spec B8).

The rule that matters: *"If final terms exceed approval thresholds, the
quotation automatically re-enters the approval flow."* That is implemented as
a real routing decision - apply the counter, recalculate, and open a fresh
round if the new score needs one - rather than as a status flip. If the
counter happens to land inside every ceiling, it auto-approves and goes
straight on to fulfillment, which is the same code path a rep's own submission
takes.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AuditAction
from app.models.approval import Approval, ApprovalTrigger
from app.models.quotation import (
    ChangeRequestStatus,
    Quotation,
    QuotationChangeRequest,
    QuotationComment,
    QuotationStatus,
)
from app.models.user import User
from app.services import approval_service, audit_service, quotation_service

# The states a customer may act on. A draft is not theirs to see, and a
# confirmed order is past negotiating.
NEGOTIABLE = {QuotationStatus.APPROVED, QuotationStatus.NEGOTIATION}


async def comments_for(
    db: AsyncSession, quotation_id: uuid.UUID, *, include_internal: bool = False
) -> Sequence[QuotationComment]:
    """Line-level Q&A. Internal notes never reach the portal."""
    stmt = (
        select(QuotationComment)
        .where(QuotationComment.quotation_id == quotation_id)
        .order_by(QuotationComment.created_at.asc())
    )
    if not include_internal:
        stmt = stmt.where(QuotationComment.is_internal.is_(False))
    return (await db.execute(stmt)).scalars().all()


async def change_requests_for(
    db: AsyncSession, quotation_id: uuid.UUID
) -> Sequence[QuotationChangeRequest]:
    result = await db.execute(
        select(QuotationChangeRequest)
        .where(QuotationChangeRequest.quotation_id == quotation_id)
        .order_by(QuotationChangeRequest.created_at.desc())
    )
    return result.scalars().all()


async def add_comment(
    db: AsyncSession,
    *,
    quotation: Quotation,
    author: User,
    body: str,
    line_id: Optional[uuid.UUID] = None,
    is_internal: bool = False,
) -> QuotationComment:
    if line_id is not None and not any(line.id == line_id for line in quotation.lines):
        raise ValueError("That line is not on this quotation")

    comment = QuotationComment(
        quotation_id=quotation.id,
        quotation_line_id=line_id,
        author_id=author.id,
        author_name=author.full_name or author.email,
        body=body.strip(),
        is_internal=is_internal,
    )
    db.add(comment)
    quotation.last_activity_at = datetime.now(timezone.utc)
    db.add(quotation)
    return comment


async def open_change_request(
    db: AsyncSession,
    *,
    quotation: Quotation,
    requested_by: User,
    counter_discount_percent: Optional[float] = None,
    requested_delivery_date=None,
    note: Optional[str] = None,
) -> QuotationChangeRequest:
    """Records a counter-offer and moves the deal into negotiation.

    Does not itself change any price. The rep decides whether to accept, and
    accepting is what re-runs the governance.
    """
    if quotation.status not in NEGOTIABLE:
        raise ValueError("This quotation is not open for negotiation")
    if (
        counter_discount_percent is None
        and requested_delivery_date is None
        and not (note or "").strip()
    ):
        raise ValueError("Say what you would like changed")

    request = QuotationChangeRequest(
        quotation_id=quotation.id,
        requested_by_id=requested_by.id,
        requested_by_name=requested_by.full_name or requested_by.email,
        counter_discount_percent=counter_discount_percent,
        requested_delivery_date=requested_delivery_date,
        note=note,
        status=ChangeRequestStatus.OPEN,
    )
    db.add(request)

    quotation.status = QuotationStatus.NEGOTIATION
    quotation.last_activity_at = datetime.now(timezone.utc)
    db.add(quotation)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_QUOTATION,
        entity_id=quotation.id,
        action=AuditAction.CUSTOMER_COUNTERED,
        user=requested_by,
        reason=note,
        context={
            "counter_discount_percent": counter_discount_percent,
            "requested_delivery_date": (
                str(requested_delivery_date) if requested_delivery_date else None
            ),
        },
    )
    return request


async def accept_change_request(
    db: AsyncSession,
    *,
    quotation: Quotation,
    request: QuotationChangeRequest,
    user: User,
) -> tuple[Quotation, Optional[Approval]]:
    """Applies a counter-offer and re-runs the governance on the new terms.

    Returns the quotation and the approval round the new terms opened - which
    may be an auto-approved one with no steps, when the counter turns out to
    sit inside every ceiling after all.
    """
    if request.status != ChangeRequestStatus.OPEN:
        raise ValueError("That request has already been resolved")

    if request.counter_discount_percent is not None:
        # Applied at the order level so it is folded into every line and
        # therefore governed by each line's own ceiling - a header discount
        # that bypassed the line checks would defeat the whole mechanism.
        quotation.order_discount_percent = float(request.counter_discount_percent)
    if request.requested_delivery_date is not None:
        quotation.requested_delivery_date = request.requested_delivery_date

    request.status = ChangeRequestStatus.ACCEPTED
    request.resolved_by_id = user.id
    request.resolved_at = datetime.now(timezone.utc)
    db.add(request)

    quotation = await quotation_service.recalculate_quotation(db, quotation)

    approval = await approval_service.open_round(
        db,
        quotation=quotation,
        submitted_by=user,
        trigger=ApprovalTrigger.CUSTOMER_COUNTER,
    )

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_QUOTATION,
        entity_id=quotation.id,
        action=AuditAction.RESUBMITTED,
        user=user,
        reason="Customer counter-offer accepted",
        context={
            "counter_discount_percent": (
                float(request.counter_discount_percent)
                if request.counter_discount_percent is not None
                else None
            ),
            "risk_band": quotation.risk_band.value,
            "requires_approval": quotation.requires_approval,
            "round": approval.round_number,
        },
    )
    await db.commit()

    # The quantities and the discount just moved, so any split planned against
    # the old terms is stale. Re-planned if it has not been accepted yet;
    # refused if it has, because stock is already held against it.
    await approval_service.plan_if_approved(db, quotation, user)

    return await quotation_service.ensure_quotation_loaded(db, quotation.id), approval


async def reject_change_request(
    db: AsyncSession,
    *,
    quotation: Quotation,
    request: QuotationChangeRequest,
    user: User,
    note: Optional[str] = None,
) -> QuotationChangeRequest:
    """Declines a counter. The quotation goes back to the terms it had."""
    if request.status != ChangeRequestStatus.OPEN:
        raise ValueError("That request has already been resolved")

    request.status = ChangeRequestStatus.REJECTED
    request.resolved_by_id = user.id
    request.resolved_at = datetime.now(timezone.utc)
    db.add(request)

    # Back to approved: the terms the customer was sent still stand.
    quotation.status = QuotationStatus.APPROVED
    quotation.last_activity_at = datetime.now(timezone.utc)
    db.add(quotation)

    if note:
        await add_comment(
            db, quotation=quotation, author=user, body=note, is_internal=False
        )

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_QUOTATION,
        entity_id=quotation.id,
        action=AuditAction.EDITED,
        user=user,
        reason=note or "Counter-offer declined",
    )
    await db.commit()
    return request
