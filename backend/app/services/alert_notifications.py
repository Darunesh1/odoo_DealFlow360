"""Nudges and escalations from the deal health dashboard."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DealHealthAlert
from app.models.quotation import Quotation
from app.models.user import Role, User, UserRole
from app.tasks.email_tasks import send_deal_alert_email

logger = logging.getLogger(__name__)


async def notify_alert_action(
    db: AsyncSession, *, alert: DealHealthAlert, action: str
) -> None:
    """A nudge goes to the rep who owns the deal; an escalation to the
    managers, because escalating to the person who is already stuck is not
    escalation."""
    quotation = await db.get(Quotation, alert.quotation_id)
    if quotation is None:
        return

    if action == "nudge":
        if not quotation.owner_id:
            return
        recipients = [await db.get(User, quotation.owner_id)]
    else:
        recipients = list(
            (
                await db.execute(
                    select(User)
                    .join(UserRole, UserRole.user_id == User.id)
                    .where(
                        UserRole.role == Role.SALES_MANAGER,
                        User.is_active.is_(True),
                    )
                )
            ).scalars().unique().all()
        )

    for user in recipients:
        if user is None:
            continue
        send_deal_alert_email.delay(
            email=user.email,
            full_name=user.full_name or "",
            quotation_number=quotation.number,
            quotation_id=str(quotation.id),
            alert_type=alert.alert_type.value,
            detail=alert.detail,
            action=action,
        )
