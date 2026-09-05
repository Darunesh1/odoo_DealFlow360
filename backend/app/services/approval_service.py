"""Approval routing and decisions.

Routing is *configuration*, not code. Section A3 requires an admin to decide
which discount range needs a Sales Manager and which needs Sales Manager then
Finance, so the chain is read from ``approval_rules`` / ``approval_rule_steps``
at submit time and **copied** onto the approval. A rule edited five minutes
later cannot rewrite an in-flight chain.

Two invariants the seeded rules encode and nothing here may break:

* A Sales Rep is never an approver.
* Admin is never an approval step.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import (
    Approval,
    ApprovalLineSnapshot,
    ApprovalRule,
    ApprovalStatus,
    ApprovalStep,
    ApprovalStepStatus,
    ApprovalTrigger,
)
from app.models.quotation import Quotation, QuotationStatus, RiskBand
from app.models.user import Role, User


async def list_rules(db: AsyncSession) -> Sequence[ApprovalRule]:
    result = await db.execute(
        select(ApprovalRule)
        .where(ApprovalRule.is_active.is_(True))
        .order_by(ApprovalRule.sort_order)
    )
    return result.scalars().all()


async def resolve_rule(db: AsyncSession, score: float) -> Optional[ApprovalRule]:
    """The first active rule whose band contains the score.

    Bands are half-open - ``min_score <= score < max_score`` - so adjacent
    rules meeting at 45 cannot both match, and a NULL ``max_score`` is
    unbounded. Ordered by ``sort_order``, so an admin controls precedence
    directly rather than relying on the numbers happening not to overlap.
    """
    value = Decimal(str(score))
    for rule in await list_rules(db):
        low = Decimal(str(rule.min_score))
        if value < low:
            continue
        if rule.max_score is None or value < Decimal(str(rule.max_score)):
            return rule
    return None


def _fallback_roles(band: RiskBand) -> list[Role]:
    """Only reached when an admin has deleted every matching rule.

    Failing open here would let an over-ceiling quote approve itself, so the
    safe direction is the strictest chain the spec defines.
    """
    if band == RiskBand.NONE:
        return []
    if band == RiskBand.HIGH:
        return [Role.SALES_MANAGER, Role.FINANCE]
    return [Role.SALES_MANAGER]


async def open_round(
    db: AsyncSession,
    *,
    quotation: Quotation,
    submitted_by: User,
    trigger: ApprovalTrigger,
) -> Approval:
    """Opens the next approval round for a quotation.

    A round is opened whether or not approval is actually needed. An
    auto-approved quotation gets a real row with **zero steps**, because the
    approvals list has to be able to show it as "Auto-Approved", and because
    "why did this not need approval?" must stay answerable months later. That
    is also why there is no branch here: a rule with no steps *is* the
    no-approval case.
    """
    rule = await resolve_rule(db, float(quotation.blended_risk_score))
    if rule is not None:
        roles = [(step.role, step.assignee_user_id) for step in rule.steps]
        rule_id, rule_name = rule.id, rule.name
    else:
        roles = [(role, None) for role in _fallback_roles(quotation.risk_band)]
        rule_id = None
        rule_name = f"{quotation.risk_band.value.title()} risk (no matching rule)"

    round_number = int(quotation.current_round or 0) + 1
    now = datetime.now(timezone.utc)

    steps = [
        ApprovalStep(
            step_order=position,
            role=role,
            status=ApprovalStepStatus.PENDING,
            assignee_id=assignee_id,
        )
        for position, (role, assignee_id) in enumerate(roles, start=1)
    ]

    # Frozen per round. Reading live lines here would let a rep who dropped the
    # offending line to 9% and resubmitted leave round 1 rendering "OK" - a
    # returned round showing no reason for its return.
    snapshots = []
    for position, line in enumerate(quotation.lines, start=1):
        over = max(
            Decimal(str(line.discount_percent))
            - Decimal(str(line.allowed_discount_percent)),
            Decimal("0"),
        )
        snapshots.append(
            ApprovalLineSnapshot(
                line_id=line.id,
                position=position,
                line_label=line.product_name,
                discount_percent=line.discount_percent,
                allowed_discount_percent=line.allowed_discount_percent,
                over_by_points=float(over),
                line_net=line.line_net,
            )
        )

    # Children are attached through the relationships rather than db.add()ed
    # individually. That cascades the inserts AND leaves the collections
    # populated on the returned object - reading approval.steps straight after
    # a flush would otherwise fire a lazy load, which under asyncpg is a
    # MissingGreenlet rather than a query.
    approval = Approval(
        quotation_id=quotation.id,
        round_number=round_number,
        rule_id=rule_id,
        rule_name=rule_name,
        blended_risk_score=quotation.blended_risk_score,
        risk_band=quotation.risk_band,
        quotation_total=quotation.total,
        discount_total=quotation.discount_total,
        status=ApprovalStatus.PENDING if roles else ApprovalStatus.AUTO_APPROVED,
        trigger=trigger,
        submitted_by_id=submitted_by.id,
        submitted_by_name=submitted_by.full_name or submitted_by.email,
        submitted_at=now,
        decided_at=None if roles else now,
        steps=steps,
        line_snapshots=snapshots,
    )
    db.add(approval)
    await db.flush()

    quotation.current_round = round_number
    quotation.status = (
        QuotationStatus.PENDING_APPROVAL if roles else QuotationStatus.APPROVED
    )
    quotation.last_activity_at = now
    db.add(quotation)
    return approval


async def load_approval(db: AsyncSession, approval_id: uuid.UUID) -> Optional[Approval]:
    result = await db.execute(
        select(Approval)
        .where(Approval.id == approval_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def latest_for(db: AsyncSession, quotation_id: uuid.UUID) -> Optional[Approval]:
    result = await db.execute(
        select(Approval)
        .where(Approval.quotation_id == quotation_id)
        .order_by(Approval.round_number.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()
