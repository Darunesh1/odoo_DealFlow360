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
import enum
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
from app.models.analytics import AuditAction
from app.models.quotation import Quotation, QuotationStatus, RiskBand
from app.models.user import Role, User
from app.services import audit_service


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


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #

class Decision(str, enum.Enum):
    APPROVE = "approve"
    RETURN = "return"
    REJECT = "reject"


def current_step(approval: Approval) -> Optional[ApprovalStep]:
    """The step whose turn it is: the first one still pending.

    The chain is sequential by definition - "Sales Manager, then Finance" -
    so Finance cannot act before the manager has, and this is what enforces it.
    """
    return next(
        (step for step in approval.steps if step.status == ApprovalStepStatus.PENDING),
        None,
    )


def can_act(approval: Approval, user: User) -> bool:
    """Whether this user may decide the step that is currently waiting."""
    step = current_step(approval)
    if step is None or approval.status != ApprovalStatus.PENDING:
        return False
    # Admin is never an approval *step*, but an admin must still be able to
    # unblock a chain whose approver has left the company.
    return user.has_role(step.role, Role.ADMIN)


async def pending_for(
    db: AsyncSession, user: User, *, limit: int = 100
) -> Sequence[Approval]:
    """Approvals waiting on this user, newest first.

    Filtered by the role of the step that is actually current, so a Finance
    user does not see a high-risk quote still sitting with the Sales Manager.
    """
    result = await db.execute(
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING)
        .order_by(Approval.submitted_at.desc())
        .limit(limit)
    )
    return [
        approval for approval in result.scalars().all() if can_act(approval, user)
    ]


async def decide(
    db: AsyncSession,
    *,
    approval: Approval,
    quotation: Quotation,
    user: User,
    decision: "Decision",
    note: Optional[str] = None,
) -> Approval:
    """Records one reviewer's verdict and moves the chain on.

    Approving the last step approves the quotation. Approving any earlier step
    simply leaves the next one pending, which is the whole of "Sales Manager,
    then Finance" - there is no separate advance step to forget to call.
    """
    if approval.status != ApprovalStatus.PENDING:
        raise ValueError("This approval round has already been decided")

    step = current_step(approval)
    if step is None:
        raise ValueError("There is no step waiting on a decision")
    if not user.has_role(step.role, Role.ADMIN):
        raise ValueError(f"This step is waiting on {step.role.value.replace('_', ' ')}")

    # A rejection or a return without a reason is unreviewable later, and A3
    # requires the reason to be logged.
    if decision in {Decision.RETURN, Decision.REJECT} and not (note or "").strip():
        raise ValueError("Give a reason when returning or rejecting")

    now = datetime.now(timezone.utc)
    step.decided_by_id = user.id
    step.decided_by_name = user.full_name or user.email
    step.decided_at = now
    step.note = note

    if decision == Decision.APPROVE:
        step.status = ApprovalStepStatus.APPROVED
        remaining = current_step(approval)
        if remaining is None:
            approval.status = ApprovalStatus.APPROVED
            approval.decided_at = now
            quotation.status = QuotationStatus.APPROVED
    elif decision == Decision.RETURN:
        step.status = ApprovalStepStatus.RETURNED
        approval.status = ApprovalStatus.RETURNED
        approval.decided_at = now
        # Back to the rep's hands. Resubmitting opens round N+1 rather than
        # reopening this one, so this round keeps its own reason forever.
        quotation.status = QuotationStatus.DRAFT
        _skip_remaining(approval)
    else:
        step.status = ApprovalStepStatus.REJECTED
        approval.status = ApprovalStatus.REJECTED
        approval.decided_at = now
        quotation.status = QuotationStatus.REJECTED
        _skip_remaining(approval)

    quotation.last_activity_at = now
    db.add(step)
    db.add(approval)
    db.add(quotation)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_QUOTATION,
        entity_id=quotation.id,
        action=_AUDIT_ACTION[decision],
        user=user,
        reason=note,
        context={
            "round": approval.round_number,
            "step": step.step_order,
            "role": step.role.value,
            "quotation_number": quotation.number,
        },
    )
    return approval


def _skip_remaining(approval: Approval) -> None:
    """Marks later steps skipped rather than leaving them pending.

    A returned round with a Finance step still showing "pending" reads as if
    Finance owes an answer they will never be asked for.
    """
    for step in approval.steps:
        if step.status == ApprovalStepStatus.PENDING:
            step.status = ApprovalStepStatus.SKIPPED


_AUDIT_ACTION = {
    Decision.APPROVE: AuditAction.APPROVED,
    Decision.RETURN: AuditAction.RETURNED,
    Decision.REJECT: AuditAction.REJECTED,
}
