"""Routing is configuration, and every submission leaves a record.

Two rules, both of which the previous hardcoded router got wrong: the chain
comes from approval_rules, and a quotation that needs no approval still writes
an approvals row so it can appear on the approvals list.
"""

from app.models.approval import ApprovalStatus, ApprovalTrigger
from app.models.quotation import QuotationStatus, RiskBand
from app.models.user import Role
from app.services import approval_service


async def _rule(db, name, low, high, band, roles, order):
    from app.models.approval import ApprovalRule, ApprovalRuleStep

    rule = ApprovalRule(
        name=name,
        min_score=low,
        max_score=high,
        risk_band=band,
        sort_order=order,
        is_active=True,
        steps=[
            ApprovalRuleStep(step_order=i, role=role)
            for i, role in enumerate(roles, start=1)
        ],
    )
    db.add(rule)
    await db.commit()
    return rule


async def test_the_chain_comes_from_the_rules_table(db_session):
    """An admin adding a Finance step to the medium band changes the routing.

    The old router hardcoded medium -> Sales Manager alone, so this is the
    behaviour that could not exist before.
    """
    await _rule(db_session, "Within limits", 0, 0.01, RiskBand.NONE, [], 1)
    await _rule(
        db_session,
        "Over limit",
        0.01,
        45,
        RiskBand.MEDIUM,
        [Role.SALES_MANAGER, Role.FINANCE],
        2,
    )

    rule = await approval_service.resolve_rule(db_session, 20.0)
    assert rule is not None
    assert [step.role for step in rule.steps] == [Role.SALES_MANAGER, Role.FINANCE]


async def test_bands_are_half_open_so_adjacent_rules_cannot_both_match(db_session):
    """45 belongs to the high band, not the medium one that ends there."""
    await _rule(db_session, "Medium", 0.01, 45, RiskBand.MEDIUM, [Role.SALES_MANAGER], 1)
    await _rule(
        db_session,
        "High",
        45,
        None,
        RiskBand.HIGH,
        [Role.SALES_MANAGER, Role.FINANCE],
        2,
    )

    assert (await approval_service.resolve_rule(db_session, 44.99)).name == "Medium"
    assert (await approval_service.resolve_rule(db_session, 45)).name == "High"
    assert (await approval_service.resolve_rule(db_session, 900)).name == "High"


async def test_a_quotation_within_limits_still_gets_an_approval_row(db_session):
    """"Auto-Approved" is a stage on the approvals list, so it needs a row.

    A zero-step rule is the whole mechanism - there is no no-approval branch.
    """
    from tests.conftest import make_user

    await _rule(db_session, "Within limits", 0, 0.01, RiskBand.NONE, [], 1)
    rep = await make_user(db_session, "rep-auto@example.com", roles=(Role.SALES_REP,))

    quotation = await _draft(db_session, rep)
    approval = await approval_service.open_round(
        db_session,
        quotation=quotation,
        submitted_by=rep,
        trigger=ApprovalTrigger.REP_SUBMIT,
    )
    await db_session.commit()

    assert approval.status == ApprovalStatus.AUTO_APPROVED
    assert approval.steps == []
    assert approval.decided_at is not None
    assert quotation.status == QuotationStatus.APPROVED


async def test_a_second_round_does_not_overwrite_the_first(db_session):
    """A resubmission opens round 2, so round 1 keeps its own chain and score."""
    from tests.conftest import make_user

    await _rule(db_session, "Over limit", 0, None, RiskBand.MEDIUM, [Role.SALES_MANAGER], 1)
    rep = await make_user(db_session, "rep-rounds@example.com", roles=(Role.SALES_REP,))
    quotation = await _draft(db_session, rep)

    first = await approval_service.open_round(
        db_session, quotation=quotation, submitted_by=rep,
        trigger=ApprovalTrigger.REP_SUBMIT,
    )
    await db_session.commit()
    second = await approval_service.open_round(
        db_session, quotation=quotation, submitted_by=rep,
        trigger=ApprovalTrigger.REP_RESUBMIT,
    )
    await db_session.commit()

    assert (first.round_number, second.round_number) == (1, 2)
    assert first.trigger == ApprovalTrigger.REP_SUBMIT
    assert second.trigger == ApprovalTrigger.REP_RESUBMIT
    latest = await approval_service.latest_for(db_session, quotation.id)
    assert latest.round_number == 2


async def _draft(db_session, owner):
    """A minimal draft quotation. No lines: routing depends on the score only."""
    from datetime import datetime, timezone

    from app.models.customer import Customer, CustomerTier
    from app.models.catalog import Currency
    from app.models.quotation import Quotation

    db_session.add(
        Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True)
    )
    tier = CustomerTier(name="Bronze", max_discount_percent=5)
    db_session.add(tier)
    await db_session.flush()
    customer = Customer(name="Acme Corp", tier_id=tier.id)
    db_session.add(customer)
    await db_session.flush()

    quotation = Quotation(
        number=f"Q-{datetime.now(timezone.utc).timestamp()}",
        customer_id=customer.id,
        owner_id=owner.id,
        owner_name=owner.full_name,
        status=QuotationStatus.DRAFT,
        currency="USD",
        customer_tier_id=tier.id,
        lines=[],
    )
    db_session.add(quotation)
    await db_session.commit()
    return quotation
