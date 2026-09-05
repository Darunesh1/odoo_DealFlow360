"""The audit trail.

Section A3 of the spec: *"All approvals, rejections, and edits must be logged
with user, timestamp, and reason."* One generic table rather than a trail per
entity, so a quotation's history can span its approvals, its fulfillment and
its invoices in a single ordered read.
"""

from typing import Any, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AuditAction, AuditLog
from app.models.user import User

# Entity type constants, so a typo cannot silently split one entity's trail in
# two.
ENTITY_QUOTATION = "quotation"
ENTITY_APPROVAL = "approval"
ENTITY_FULFILLMENT = "fulfillment"
ENTITY_SUBSCRIPTION = "subscription"
ENTITY_INVOICE = "invoice"
ENTITY_ALERT = "deal_health_alert"


def record(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: AuditAction,
    user: Optional[User] = None,
    reason: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Stages one audit row. The caller commits.

    Not async and does not flush: an audit entry belongs to the same
    transaction as the change it describes, so that a rolled-back approval
    leaves no record of having happened.

    ``actor_name`` is snapshotted because ``user_id`` is SET NULL - the trail
    has to stay readable after the user is deleted.
    """
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user.id if user else None,
        actor_name=(user.full_name or user.email) if user else "System",
        reason=reason,
        context=context,
    )
    db.add(entry)
    return entry


async def trail_for(
    db: AsyncSession, *, entity_type: str, entity_id: uuid.UUID, limit: int = 100
) -> Sequence[AuditLog]:
    """One entity's history, oldest first - the order the mockup renders."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def recent(db: AsyncSession, *, limit: int = 10) -> Sequence[AuditLog]:
    """The dashboard's "Recent Activity" list."""
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    return result.scalars().all()
