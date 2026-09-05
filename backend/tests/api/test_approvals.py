"""Approval decisions.

The rules that matter: the chain is sequential, a Sales Rep is never an
approver, a return needs a reason, and a returned round keeps its own frozen
breakdown after the rep fixes the line.
"""

import pytest

from app.models.approval import ApprovalStatus, ApprovalStepStatus, ApprovalTrigger
from app.models.quotation import QuotationStatus
from app.models.user import Role
from app.services import approval_service
from app.services.approval_service import Decision
from tests.api.test_approval_routing import _draft, _rule
from tests.conftest import make_user

from app.models.quotation import RiskBand


async def _submitted(db_session):
    """A quotation sitting on a Sales Manager then Finance chain."""
    await _rule(
        db_session,
        "High risk",
        0,
        None,
        RiskBand.HIGH,
        [Role.SALES_MANAGER, Role.FINANCE],
        1,
    )
    rep = await make_user(db_session, "rep-dec@example.com", roles=(Role.SALES_REP,))
    manager = await make_user(
        db_session, "mgr-dec@example.com", roles=(Role.SALES_MANAGER,)
    )
    finance = await make_user(db_session, "fin-dec@example.com", roles=(Role.FINANCE,))

    quotation = await _draft(db_session, rep)
    approval = await approval_service.open_round(
        db_session,
        quotation=quotation,
        submitted_by=rep,
        trigger=ApprovalTrigger.REP_SUBMIT,
    )
    await db_session.commit()
    return quotation, approval, rep, manager, finance


async def test_a_rep_can_never_approve(db_session):
    quotation, approval, rep, _, _ = await _submitted(db_session)

    with pytest.raises(ValueError, match="waiting on sales manager"):
        await approval_service.decide(
            db_session,
            approval=approval,
            quotation=quotation,
            user=rep,
            decision=Decision.APPROVE,
        )


async def test_finance_cannot_jump_the_queue(db_session):
    """"Sales Manager, then Finance" is sequential, not two parallel inboxes."""
    quotation, approval, _, _, finance = await _submitted(db_session)

    with pytest.raises(ValueError, match="waiting on sales manager"):
        await approval_service.decide(
            db_session,
            approval=approval,
            quotation=quotation,
            user=finance,
            decision=Decision.APPROVE,
        )


async def test_the_chain_advances_rather_than_finishing(db_session):
    quotation, approval, _, manager, finance = await _submitted(db_session)

    await approval_service.decide(
        db_session,
        approval=approval,
        quotation=quotation,
        user=manager,
        decision=Decision.APPROVE,
    )
    await db_session.commit()

    # Manager approved, but Finance still owes an answer.
    assert approval.status == ApprovalStatus.PENDING
    assert quotation.status == QuotationStatus.PENDING_APPROVAL
    assert approval_service.current_step(approval).role == Role.FINANCE

    await approval_service.decide(
        db_session,
        approval=approval,
        quotation=quotation,
        user=finance,
        decision=Decision.APPROVE,
    )
    await db_session.commit()

    assert approval.status == ApprovalStatus.APPROVED
    assert quotation.status == QuotationStatus.APPROVED


async def test_a_return_needs_a_reason_and_skips_the_rest(db_session):
    quotation, approval, _, manager, _ = await _submitted(db_session)

    with pytest.raises(ValueError, match="Give a reason"):
        await approval_service.decide(
            db_session,
            approval=approval,
            quotation=quotation,
            user=manager,
            decision=Decision.RETURN,
            note="   ",
        )

    await approval_service.decide(
        db_session,
        approval=approval,
        quotation=quotation,
        user=manager,
        decision=Decision.RETURN,
        note="Justify the service discount.",
    )
    await db_session.commit()

    assert approval.status == ApprovalStatus.RETURNED
    # Back in the rep's hands.
    assert quotation.status == QuotationStatus.DRAFT
    # Finance is skipped, not left looking as if it owes an answer.
    statuses = {step.role: step.status for step in approval.steps}
    assert statuses[Role.SALES_MANAGER] == ApprovalStepStatus.RETURNED
    assert statuses[Role.FINANCE] == ApprovalStepStatus.SKIPPED


async def test_a_decided_round_cannot_be_decided_twice(db_session):
    quotation, approval, _, manager, _ = await _submitted(db_session)

    await approval_service.decide(
        db_session,
        approval=approval,
        quotation=quotation,
        user=manager,
        decision=Decision.REJECT,
        note="Margin is unrecoverable.",
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="already been decided"):
        await approval_service.decide(
            db_session,
            approval=approval,
            quotation=quotation,
            user=manager,
            decision=Decision.APPROVE,
        )
