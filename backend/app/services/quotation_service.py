from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import secrets
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_invite_token, is_password_usable
from app.models.approval import Approval, ApprovalLineSnapshot, ApprovalStatus, ApprovalStep, ApprovalStepStatus, ApprovalTrigger
from app.models.catalog import CategoryDiscountLimit, Product, ProductStatus, ProductVariant
from app.models.customer import Customer
from app.models.quotation import LineSource, Quotation, QuotationLine, QuotationStatus, RiskBand
from app.models.user import Role, User
from app.schemas.quotation import (
    QuotationCreate,
    QuotationLineCreate,
    QuotationLineUpdate,
    QuotationUpdate,
)
from app.services.catalog_service import (
    get_category_limit,
    get_customer_by_id,
    get_product_by_id,
    get_variant_by_id,
    list_stock_for_variant,
)
from app.services.pricing_service import resolve_variant_price
from app.services.user_service import apply_roles, create_invited_user, get_user_by_email
from app.tasks.email_tasks import send_customer_portal_email


MONEY = Decimal("0.01")
UNIT = Decimal("0.0001")


def _money(value: Decimal | float | int) -> float:
    return float(Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP))


def _unit(value: Decimal | float | int) -> float:
    return float(Decimal(str(value)).quantize(UNIT, rounding=ROUND_HALF_UP))


def _generate_number() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"Q-{stamp}-{secrets.token_hex(2).upper()}"


def _risk_band(score: Decimal) -> RiskBand:
    """Bands over the blended score, not over raw points.

    Zero means every line sat inside its own ceiling, which is the only case
    that needs no approver at all.
    """
    if score <= 0:
        return RiskBand.NONE
    if score < 15:
        return RiskBand.LOW
    if score < 45:
        return RiskBand.MEDIUM
    return RiskBand.HIGH


def _approval_roles_for_band(band: RiskBand) -> list[Role]:
    """A Sales Rep is never an approver and Admin is never a step.

    Within every ceiling, nobody approves. Over a ceiling, a Sales Manager
    always does. Finance joins only on high risk.

    This is the last hardcoded copy of the chain: the next phase reads it from
    approval_rules / approval_rule_steps, which is what makes screen 18
    configuration rather than decoration.
    """
    if band in {RiskBand.LOW, RiskBand.MEDIUM}:
        return [Role.SALES_MANAGER]
    if band == RiskBand.HIGH:
        return [Role.SALES_MANAGER, Role.FINANCE]
    return []


async def _allocate_stock_line(
    db: AsyncSession,
    *,
    variant_id: uuid.UUID,
    quantity: int,
) -> tuple[Optional[uuid.UUID], Optional[str], Optional[str], Optional[str], int]:
    """Note the likeliest source warehouse and what is available in total.

    Deliberately does NOT refuse a short line. A 24-unit order that no single
    warehouse can cover is exactly the case B6 exists for - the split across
    warehouses, and the backorder when even the total is short, belong to
    fulfillment. Refusing here would make both unreachable, and would also
    block services and subscriptions, which carry no stock at all.
    """
    stock_items = await list_stock_for_variant(db, variant_id)
    total_available = sum(int(item.quantity_available) for item in stock_items)
    # Richest first (list_stock_for_variant orders by availability), so the
    # snapshot names the warehouse the planner will most likely pick.
    preferred = next(
        (item for item in stock_items if item.warehouse is not None and item.quantity_available > 0),
        None,
    )
    if preferred is None:
        return None, None, None, None, total_available
    return (
        preferred.warehouse.id,
        preferred.warehouse.name,
        preferred.warehouse.code,
        preferred.bin_location,
        total_available,
    )


def _apply_stock_snapshot(
    line: QuotationLine,
    *,
    warehouse_id: uuid.UUID,
    warehouse_name: str,
    warehouse_code: str,
    warehouse_bin_location: Optional[str],
    stock_available_at_entry: int,
) -> None:
    line.warehouse_id = warehouse_id
    line.warehouse_name = warehouse_name
    line.warehouse_code = warehouse_code
    line.warehouse_bin_location = warehouse_bin_location
    line.stock_available_at_entry = stock_available_at_entry


async def _load_quotation(db: AsyncSession, quotation_id: uuid.UUID) -> Optional[Quotation]:
    stmt = (
        select(Quotation)
        # populate_existing is load-bearing: without it a re-query returns the
        # identity-mapped instance with its ALREADY-LOADED lines collection,
        # so a recalculate straight after add_line would total the previous
        # set of lines and report the wrong risk band to the screen.
        .execution_options(populate_existing=True)
        .options(
            selectinload(Quotation.customer).selectinload(Customer.tier),
            selectinload(Quotation.customer_tier),
            selectinload(Quotation.lines),
        )
        .where(Quotation.id == quotation_id)
    )
    result = await db.execute(stmt)
    quotation = result.scalar_one_or_none()
    if quotation is not None:
        latest = await _load_latest_approval(db, quotation.id)
        quotation.approval = latest  # type: ignore[attr-defined]
    return quotation


async def _load_latest_approval(db: AsyncSession, quotation_id: uuid.UUID) -> Optional[Approval]:
    stmt = (
        select(Approval)
        .options(selectinload(Approval.steps), selectinload(Approval.line_snapshots))
        .where(Approval.quotation_id == quotation_id)
        .order_by(Approval.round_number.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_quotations(db: AsyncSession) -> Sequence[Quotation]:
    stmt = select(Quotation).order_by(Quotation.updated_at.desc())
    result = await db.execute(stmt)
    quotations = list(result.scalars().all())
    for quotation in quotations:
        quotation.approval = await _load_latest_approval(db, quotation.id)  # type: ignore[attr-defined]
    return quotations


async def create_draft_quotation(
    db: AsyncSession,
    *,
    owner: User,
    obj_in: QuotationCreate,
) -> Quotation:
    customer = await get_customer_by_id(db, obj_in.customer_id)
    if not customer:
        raise ValueError("Customer not found")

    recipient_email = obj_in.recipient_email or customer.contact_email

    quotation = Quotation(
        number=_generate_number(),
        customer_id=customer.id,
        recipient_email=str(recipient_email) if recipient_email else None,
        owner_id=owner.id,
        owner_name=owner.full_name or owner.email,
        sales_team_id=owner.sales_team_id,
        status=QuotationStatus.DRAFT,
        currency=obj_in.currency,
        customer_tier_id=customer.tier_id,
        tier_max_discount_percent=float(customer.tier.max_discount_percent),
        order_discount_percent=obj_in.order_discount_percent,
        requested_delivery_date=obj_in.requested_delivery_date,
        valid_until=obj_in.valid_until,
        notes=obj_in.notes,
        last_activity_at=datetime.now(timezone.utc),
    )
    db.add(quotation)
    await db.commit()
    await db.refresh(quotation)
    return await ensure_quotation_loaded(db, quotation.id)


async def ensure_quotation_loaded(db: AsyncSession, quotation_id: uuid.UUID) -> Quotation:
    quotation = await _load_quotation(db, quotation_id)
    if quotation is None:
        raise ValueError("Quotation not found")
    return quotation


async def _next_position(db: AsyncSession, quotation_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.max(QuotationLine.position), 0)).where(
        QuotationLine.quotation_id == quotation_id
    )
    result = await db.execute(stmt)
    return int(result.scalar_one()) + 1


async def recalculate_quotation(db: AsyncSession, quotation: Quotation) -> Quotation:
    customer = await get_customer_by_id(db, quotation.customer_id)
    if not customer:
        raise ValueError("Customer not found")

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    tax_total = Decimal("0")
    total = Decimal("0")
    margin_total = Decimal("0")
    subtotal_net = Decimal("0")
    max_over = Decimal("0")
    weighted_over = Decimal("0")

    for line in quotation.lines:
        if not line.product_id or not line.variant_id:
            continue
        product = await get_product_by_id(db, line.product_id)
        if not product:
            continue
        category_limit_row = await get_category_limit(db, product.category)
        tier_limit = Decimal(str(customer.tier.max_discount_percent))
        # A category with no row has NO ceiling. Treating it as zero would flag
        # every uncapped line the instant anyone discounted it.
        category_limit = (
            Decimal(str(category_limit_row.max_discount_percent))
            if category_limit_row is not None
            else Decimal("100")
        )
        allowed = min(tier_limit, category_limit)
        variant = await get_variant_by_id(db, line.variant_id)
        unit_cost = Decimal(str(variant.unit_cost)) if variant else Decimal("0")
        resolved = await resolve_variant_price(
            db,
            variant_id=line.variant_id,
            tier_id=customer.tier_id,
            currency_code=quotation.currency,
        )
        resolved_unit_price = resolved if resolved is not None else Decimal("0")
        line_discount = Decimal(str(line.line_discount_percent))
        order_discount = Decimal(str(quotation.order_discount_percent))
        discount_percent = line_discount + order_discount
        line_net = resolved_unit_price * Decimal(str(line.quantity)) * (Decimal("1") - discount_percent / Decimal("100"))
        line_tax = line_net * Decimal(str(product.tax_percent)) / Decimal("100")
        line_total = line_net + line_tax
        line_margin = line_net - (unit_cost * Decimal(str(line.quantity)))
        over = max(discount_percent - allowed, Decimal("0"))

        line.product_name = product.name
        line.variant_name = None if variant is None or variant.is_default else variant.name
        line.sku = variant.sku if variant else None
        line.category = product.category
        line.list_price_at_entry = _unit(resolved_unit_price)
        line.unit_price = _unit(resolved_unit_price)
        line.unit_cost = _money(unit_cost)
        line.tax_percent = float(product.tax_percent)
        line.tier_limit_percent = float(tier_limit)
        line.category_limit_percent = (
            float(category_limit_row.max_discount_percent)
            if category_limit_row is not None
            else None
        )
        line.allowed_discount_percent = float(allowed)
        line.discount_percent = float(discount_percent)
        line.line_net = _money(line_net)
        line.line_tax = _money(line_tax)
        line.line_total = _money(line_total)
        line.is_recurring = product.is_subscription
        line.recurring_interval = product.recurring_interval
        subtotal += resolved_unit_price * Decimal(str(line.quantity))
        discount_total += resolved_unit_price * Decimal(str(line.quantity)) - line_net
        tax_total += line_tax
        total += line_total
        margin_total += line_margin
        subtotal_net += line_net
        max_over = max(max_over, over)
        weighted_over += over * line_net

    quotation.customer_tier_id = customer.tier_id
    quotation.tier_max_discount_percent = float(customer.tier.max_discount_percent)
    quotation.subtotal = _money(subtotal)
    quotation.discount_total = _money(discount_total)
    quotation.tax_total = _money(tax_total)
    quotation.total = _money(total)
    quotation.margin_total = _money(margin_total)
    # Spec section 10: the worst single line AND the pattern across the order.
    # net_base is the discounted revenue the weighting divides by.
    weighted_mean = (weighted_over / subtotal_net) if subtotal_net else Decimal("0")
    score = min(Decimal("100"), Decimal("8") * max_over + Decimal("5") * weighted_mean)
    quotation.max_line_over_points = float(max_over)
    quotation.weighted_over_points = float(weighted_mean)
    quotation.blended_risk_score = float(score)
    quotation.risk_band = _risk_band(score)
    quotation.requires_approval = quotation.risk_band != RiskBand.NONE
    quotation.last_activity_at = datetime.now(timezone.utc)
    db.add(quotation)
    await db.commit()
    await db.refresh(quotation)
    return await ensure_quotation_loaded(db, quotation.id)


async def add_line(db: AsyncSession, quotation: Quotation, obj_in: QuotationLineCreate) -> Quotation:
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be edited")

    variant = await get_variant_by_id(db, obj_in.variant_id)
    if not variant or not variant.is_active:
        raise ValueError("Variant not found")
    product = await get_product_by_id(db, variant.product_id)
    if not product:
        raise ValueError("Product not found")
    # Re-checked server-side: the picker already hides archived products, but a
    # stale tab must not be able to quote one.
    if product.status != ProductStatus.ACTIVE:
        raise ValueError(f"{product.name} is archived and cannot be quoted")

    warehouse_id, warehouse_name, warehouse_code, warehouse_bin_location, stock_available_at_entry = await _allocate_stock_line(
        db,
        variant_id=variant.id,
        quantity=obj_in.quantity,
    )
    unit_price = await resolve_variant_price(
        db,
        variant_id=variant.id,
        tier_id=quotation.customer.tier_id,
        currency_code=quotation.currency,
    )
    if unit_price is None:
        raise ValueError(
            f"{variant.sku} has no {quotation.currency} price for the "
            f"{quotation.customer.tier.name} tier"
        )

    category_limit_row = await get_category_limit(db, product.category)
    category_limit = (
        Decimal(str(category_limit_row.max_discount_percent))
        if category_limit_row is not None
        else Decimal("100")
    )

    line = QuotationLine(
        quotation_id=quotation.id,
        position=await _next_position(db, quotation.id),
        product_id=product.id,
        variant_id=variant.id,
        warehouse_id=warehouse_id,
        product_name=product.name,
        variant_name=None if variant.is_default else variant.name,
        sku=variant.sku,
        category=product.category,
        warehouse_name=warehouse_name,
        warehouse_code=warehouse_code,
        warehouse_bin_location=warehouse_bin_location,
        stock_available_at_entry=stock_available_at_entry,
        quantity=obj_in.quantity,
        unit_price=_unit(unit_price),
        list_price_at_entry=_unit(unit_price),
        unit_cost=_money(variant.unit_cost),
        tax_percent=float(product.tax_percent),
        line_discount_percent=obj_in.line_discount_percent,
        discount_percent=obj_in.line_discount_percent + float(quotation.order_discount_percent),
        tier_limit_percent=float(quotation.customer.tier.max_discount_percent),
        category_limit_percent=(
            float(category_limit_row.max_discount_percent)
            if category_limit_row is not None
            else None
        ),
        allowed_discount_percent=float(min(
            Decimal(str(quotation.customer.tier.max_discount_percent)),
            category_limit,
        )),
        is_recurring=product.is_subscription,
        recurring_interval=product.recurring_interval,
        selected_options=variant.options,
        source=obj_in.source,
        line_net=0,
        line_tax=0,
        line_total=0,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    quotation = await ensure_quotation_loaded(db, quotation.id)
    return await recalculate_quotation(db, quotation)


async def update_line(db: AsyncSession, quotation: Quotation, line_id: uuid.UUID, obj_in: QuotationLineUpdate) -> Quotation:
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be edited")
    line = next((item for item in quotation.lines if item.id == line_id), None)
    if line is None:
        raise ValueError("Quotation line not found")
    if line.variant_id is None:
        raise ValueError("Quotation line variant is missing")
    quantity = obj_in.quantity if obj_in.quantity is not None else line.quantity
    if quantity != line.quantity or line.warehouse_id is None:
        warehouse_id, warehouse_name, warehouse_code, warehouse_bin_location, stock_available_at_entry = await _allocate_stock_line(
            db,
            variant_id=line.variant_id,
            quantity=quantity,
        )
        _apply_stock_snapshot(
            line,
            warehouse_id=warehouse_id,
            warehouse_name=warehouse_name,
            warehouse_code=warehouse_code,
            warehouse_bin_location=warehouse_bin_location,
            stock_available_at_entry=stock_available_at_entry,
        )
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    db.add(line)
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation.id)
    return await recalculate_quotation(db, quotation)


async def remove_line(db: AsyncSession, quotation: Quotation, line_id: uuid.UUID) -> Quotation:
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be edited")
    line = next((item for item in quotation.lines if item.id == line_id), None)
    if line is None:
        raise ValueError("Quotation line not found")
    await db.delete(line)
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation.id)
    return await recalculate_quotation(db, quotation)


async def update_quotation(db: AsyncSession, quotation: Quotation, obj_in: QuotationUpdate) -> Quotation:
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be edited")
    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quotation, field, value)
    db.add(quotation)
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation.id)
    return await recalculate_quotation(db, quotation)


async def submit_quotation(db: AsyncSession, quotation: Quotation, submitted_by: User) -> tuple[Quotation, Optional[Approval]]:
    quotation = await recalculate_quotation(db, quotation)
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be submitted")

    approval: Optional[Approval] = None
    if quotation.requires_approval:
        approval = Approval(
            quotation_id=quotation.id,
            round_number=1,
            rule_id=None,
            rule_name=f"{quotation.risk_band.value.title()} Risk Approval",
            blended_risk_score=quotation.blended_risk_score,
            risk_band=quotation.risk_band,
            quotation_total=quotation.total,
            discount_total=quotation.discount_total,
            status=ApprovalStatus.PENDING,
            trigger=ApprovalTrigger.REP_SUBMIT,
            submitted_by_id=submitted_by.id,
            submitted_by_name=submitted_by.full_name or submitted_by.email,
            submitted_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.flush()
        for position, role in enumerate(_approval_roles_for_band(quotation.risk_band), start=1):
            db.add(
                ApprovalStep(
                    approval_id=approval.id,
                    step_order=position,
                    role=role,
                    status=ApprovalStepStatus.PENDING,
                )
            )
        for position, line in enumerate(quotation.lines, start=1):
            over_points = max(Decimal(str(line.discount_percent)) - Decimal(str(line.allowed_discount_percent)), Decimal("0"))
            db.add(
                ApprovalLineSnapshot(
                    approval_id=approval.id,
                    line_id=line.id,
                    position=position,
                    line_label=line.product_name,
                    discount_percent=line.discount_percent,
                    allowed_discount_percent=line.allowed_discount_percent,
                    over_by_points=float(over_points),
                    line_net=line.line_net,
                )
            )
        quotation.status = QuotationStatus.PENDING_APPROVAL
    else:
        quotation.status = QuotationStatus.APPROVED
        quotation.confirmed_at = None

    quotation.current_round = 1
    quotation.last_activity_at = datetime.now(timezone.utc)
    db.add(quotation)
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation.id)
    if approval is not None:
        approval = await _load_latest_approval(db, quotation.id)
        quotation.approval = approval  # type: ignore[attr-defined]
    return quotation, approval


async def sync_customer_portal_email(
    db: AsyncSession,
    *,
    customer: Customer,
    recipient_email: Optional[str],
    quotation_number: str,
) -> None:
    if not recipient_email:
        return
    user = await get_user_by_email(db, email=recipient_email)
    if user:
        if user.customer_id is None:
            user.customer_id = customer.id
        if Role.CUSTOMER not in user.roles:
            apply_roles(user, [*user.roles, Role.CUSTOMER])
        db.add(user)
        await db.commit()
        send_customer_portal_email.delay(
            email=user.email,
            customer_name=customer.name,
            quotation_number=quotation_number,
            needs_invite=not is_password_usable(user.hashed_password),
            token=create_invite_token(user.id) if not is_password_usable(user.hashed_password) else None,
        )
        return

    invited = await create_invited_user(
        db,
        email=recipient_email,
        full_name=customer.name,
        roles=[Role.CUSTOMER],
        customer_id=customer.id,
    )
    send_customer_portal_email.delay(
        email=invited.email,
        customer_name=customer.name,
        quotation_number=quotation_number,
        needs_invite=True,
        token=create_invite_token(invited.id),
    )
