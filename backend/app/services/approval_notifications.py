"""Who gets told when an approval moves.

Kept out of approval_service so the decision logic stays testable without a
mail server, and so the emails are dispatched only after the transaction has
committed - a rolled-back approval must not send "your quote was rejected".
"""

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalStatus
from app.models.quotation import Quotation
from app.models.user import Role, User, UserRole
from app.services import approval_service
from app.tasks.email_tasks import (
    send_approval_decision_email,
    send_approval_requested_email,
)

logger = logging.getLogger(__name__)


async def _holders_of(db: AsyncSession, role: Role) -> Sequence[User]:
    """Everyone who could act on a step.

    Assignment is by role at runtime rather than to a named person, so a
    manager on holiday never blocks a deal.
    """
    result = await db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role == role, User.is_active.is_(True))
    )
    return result.scalars().unique().all()


async def notify_submitted(
    db: AsyncSession, *, approval: Approval, quotation: Quotation
) -> None:
    """Tells the first step's role that something is waiting on them."""
    step = approval_service.current_step(approval)
    if step is None:
        return
    for user in await _holders_of(db, step.role):
        send_approval_requested_email.delay(
            email=user.email,
            full_name=user.full_name or "",
            quotation_number=quotation.number,
            customer_name=quotation.customer.name,
            risk_band=approval.risk_band.value,
            score=float(approval.blended_risk_score),
            approval_id=str(approval.id),
        )


async def notify_decision(
    db: AsyncSession, *, approval: Approval, quotation: Quotation, actor: User
) -> None:
    """Tells the rep what happened, and the next approver that it is their turn."""
    if quotation.owner_id:
        owner = await db.get(User, quotation.owner_id)
        if owner is not None:
            step = next(
                (
                    s
                    for s in approval.steps
                    if s.decided_by_id == actor.id and s.decided_at is not None
                ),
                None,
            )
            send_approval_decision_email.delay(
                email=owner.email,
                full_name=owner.full_name or "",
                quotation_number=quotation.number,
                outcome=approval.status.value,
                decided_by=actor.full_name or actor.email,
                note=(step.note if step else None) or "",
                quotation_id=str(quotation.id),
            )

    # Still pending means the chain advanced rather than finished, so the next
    # role now owes an answer.
    if approval.status == ApprovalStatus.PENDING:
        await notify_submitted(db, approval=approval, quotation=quotation)
