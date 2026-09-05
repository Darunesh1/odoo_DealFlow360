"""Emails between the rep and the customer portal.

Dispatched after the transaction commits, never inside it: a rolled-back
counter-offer must not have already told a rep it arrived.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quotation import Quotation
from app.models.user import User
from app.tasks.email_tasks import (
    send_change_request_email,
    send_quotation_link_email,
)

logger = logging.getLogger(__name__)


async def notify_change_requested(
    db: AsyncSession, *, quotation: Quotation
) -> None:
    """Tells the owning rep their customer has countered."""
    if not quotation.owner_id:
        return
    owner = await db.get(User, quotation.owner_id)
    if owner is None:
        return
    send_change_request_email.delay(
        email=owner.email,
        full_name=owner.full_name or "",
        quotation_number=quotation.number,
        customer_name=quotation.customer.name,
        quotation_id=str(quotation.id),
    )


async def notify_quotation_sent(
    db: AsyncSession, *, quotation: Quotation, recipient: Optional[str] = None
) -> None:
    """Sends the customer the link to their quotation in the portal."""
    address = recipient or quotation.recipient_email or quotation.customer.contact_email
    if not address:
        logger.info(f"No address to send {quotation.number} to")
        return
    send_quotation_link_email.delay(
        email=address,
        customer_name=quotation.customer.name,
        quotation_number=quotation.number,
        quotation_id=str(quotation.id),
        total=float(quotation.total),
        currency=quotation.currency,
    )
