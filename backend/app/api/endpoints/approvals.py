"""The approvals inbox and its decisions (mockup screens 5 and 6).

Reads are open to every internal role - a rep has to be able to watch their own
quote move - but a *decision* is restricted to the role of the step that is
actually waiting, which the service enforces rather than the router: whose turn
it is depends on the chain, not on the URL.
"""

from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, get_db, get_pagination, require_roles
from app.models.approval import Approval, ApprovalStatus
from app.models.customer import Customer
from app.models.quotation import Quotation
from app.models.user import Role, User
from app.schemas.approval import (
    ApprovalCounts,
    ApprovalRead,
    ApprovalDecision,
    ApprovalDecisionInput,
    ApprovalDetailRead,
    ApprovalListPage,
    ApprovalListRow,
    AuditEntryRead,
)
from app.services import approval_service, audit_service
from app.services.approval_service import Decision
from app.services.quotation_service import ensure_quotation_loaded

router = APIRouter(
    dependencies=[
        Depends(
            require_roles(
                Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER, Role.FINANCE
            )
        )
    ]
)


def _visible_to(stmt, viewer: User):
    """A rep sees the approvals for their own quotations only."""
    if viewer.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE):
        return stmt
    return stmt.where(Quotation.owner_id == viewer.id)


def _row(approval: Approval, quotation: Quotation, viewer: User) -> ApprovalListRow:
    step = approval_service.current_step(approval)
    return ApprovalListRow(
        id=approval.id,
        quotation_id=quotation.id,
        quotation_number=quotation.number,
        customer_name=quotation.customer.name,
        customer_tier=quotation.customer.tier.name if quotation.customer.tier else None,
        round_number=approval.round_number,
        rule_name=approval.rule_name,
        blended_risk_score=float(approval.blended_risk_score),
        risk_band=approval.risk_band,
        quotation_total=float(approval.quotation_total),
        currency=quotation.currency,
        status=approval.status,
        current_role=step.role if step else None,
        assigned_to=step.assignee_name if step else None,
        submitted_by_name=approval.submitted_by_name,
        submitted_at=approval.submitted_at,
        decided_at=approval.decided_at,
        can_act=approval_service.can_act(approval, viewer),
    )


@router.get("/approvals", response_model=ApprovalListPage)
async def read_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pagination: Pagination = Depends(get_pagination),
    status_filter: Optional[ApprovalStatus] = Query(default=None, alias="status"),
    mine: bool = Query(default=False, description="Only rounds waiting on me"),
    search: Optional[str] = Query(default=None),
) -> Any:
    """Screen 5. Every quotation that needed, needs, or went through approval."""
    base = _visible_to(
        select(Approval, Quotation)
        .join(Quotation, Approval.quotation_id == Quotation.id)
        .join(Customer, Quotation.customer_id == Customer.id),
        current_user,
    )
    if status_filter is not None:
        base = base.where(Approval.status == status_filter)
    if search:
        needle = f"%{search.strip()}%"
        base = base.where(
            or_(Quotation.number.ilike(needle), Customer.name.ilike(needle))
        )

    counts_stmt = _visible_to(
        select(Approval.status, func.count())
        .select_from(Approval)
        .join(Quotation, Approval.quotation_id == Quotation.id),
        current_user,
    ).group_by(Approval.status)
    raw_counts = {status_: int(count) for status_, count in (await db.execute(counts_stmt)).all()}
    counts = ApprovalCounts(
        pending=raw_counts.get(ApprovalStatus.PENDING, 0),
        returned=raw_counts.get(ApprovalStatus.RETURNED, 0),
        # Auto-approved rounds are approved rounds; splitting them in the tile
        # would make the numbers not add up to the list.
        approved=raw_counts.get(ApprovalStatus.APPROVED, 0)
        + raw_counts.get(ApprovalStatus.AUTO_APPROVED, 0),
        rejected=raw_counts.get(ApprovalStatus.REJECTED, 0),
    )

    ordered = base.order_by(Approval.submitted_at.desc())

    if mine:
        # "Waiting on me" depends on the current step's role, which is a
        # property of the loaded chain rather than a column, so it is filtered
        # after loading. Bounded by the pending set, which is small by nature.
        rows = [
            (approval, quotation)
            for approval, quotation in (await db.execute(ordered)).all()
            if approval_service.can_act(approval, current_user)
        ]
        total = len(rows)
        page_rows = rows[pagination.skip : pagination.skip + pagination.limit]
    else:
        total = (
            await db.execute(
                select(func.count()).select_from(
                    ordered.with_only_columns(Approval.id).subquery()
                )
            )
        ).scalar_one()
        page_rows = (
            await db.execute(ordered.offset(pagination.skip).limit(pagination.limit))
        ).all()

    return ApprovalListPage(
        items=[_row(approval, quotation, current_user) for approval, quotation in page_rows],
        total=int(total),
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(int(total)),
        counts=counts,
    )


async def _load(db: AsyncSession, approval_id: uuid.UUID) -> tuple[Approval, Quotation]:
    approval = await approval_service.load_approval(db, approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found"
        )
    quotation = await ensure_quotation_loaded(db, approval.quotation_id)
    return approval, quotation


def _guard_visibility(quotation: Quotation, viewer: User) -> None:
    if viewer.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE):
        return
    if quotation.owner_id != viewer.id:
        # 404 rather than 403: whether someone else's quotation exists is not
        # this user's business.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found"
        )


@router.get("/approvals/{approval_id}", response_model=ApprovalDetailRead)
async def read_approval(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Screen 6: the risk breakdown, the chain, and the audit trail.

    The "Why This Quote Was Flagged" table comes from the round's frozen line
    snapshots, never from the live lines.
    """
    approval, quotation = await _load(db, approval_id)
    _guard_visibility(quotation, current_user)

    step = approval_service.current_step(approval)
    trail = await audit_service.trail_for(
        db, entity_type=audit_service.ENTITY_QUOTATION, entity_id=quotation.id
    )

    return ApprovalDetailRead(
        # The approval's own fields validate straight off the ORM object; the
        # rest is context the screen needs and the row does not carry.
        **ApprovalRead.model_validate(approval).model_dump(),
        quotation_number=quotation.number,
        customer_name=quotation.customer.name,
        customer_tier=quotation.customer.tier.name if quotation.customer.tier else None,
        currency=quotation.currency,
        current_role=step.role if step else None,
        can_act=approval_service.can_act(approval, current_user),
        audit_trail=[AuditEntryRead.model_validate(entry) for entry in trail],
    )


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalDetailRead)
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecisionInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Approve, return for revision, or reject.

    A Sales Rep never reaches this: they hold neither the step's role nor
    admin, so the service refuses before anything is written.
    """
    approval, quotation = await _load(db, approval_id)

    try:
        await approval_service.decide(
            db,
            approval=approval,
            quotation=quotation,
            user=current_user,
            decision=Decision(body.decision.value),
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    await db.commit()

    # After the commit, in this order: plan the split so the order appears
    # under "Orders awaiting fulfillment" the moment it is approved, then tell
    # people. A rolled-back decision must have done neither.
    await approval_service.plan_if_approved(db, quotation, current_user)

    from app.services.approval_notifications import notify_decision

    await notify_decision(db, approval=approval, quotation=quotation, actor=current_user)

    return await read_approval(approval_id, db=db, current_user=current_user)
