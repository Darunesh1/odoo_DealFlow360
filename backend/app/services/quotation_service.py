from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import secrets
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_invite_token, is_password_usable
from app.models.analytics import AuditAction
from app.models.approval import Approval, ApprovalTrigger
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
from app.services import approval_service, audit_service
from app.core.config import settings
from app.services.pricing_service import convert, resolve_variant_price
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


async def _allocate_stock_line(
    db: AsyncSession,
    *,
    variant_id: uuid.UUID,
    quantity: int,
) -> tuple[Optional[uuid.UUID], Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Note the likeliest source warehouse and what is available in total.

    Deliberately does NOT refuse a short line. A 24-unit order that no single
    warehouse can cover is exactly the case B6 exists for - the split across
    warehouses, and the backorder when even the total is short, belong to
    fulfillment. Refusing here would make both unreachable, and would also
    block services and subscriptions, which carry no stock at all.

    Availability is **None when the variant has no stock rows at all** and 0
    when it has rows that are empty. That distinction is the difference between
    "not stocked" - a plan or a service, which will never ship from a warehouse
    - and "out of stock". Collapsing them made every subscription line announce
    "Only 0 in stock, the rest backorders", which `plan_split` then contradicted
    by skipping the line entirely.
    """
    stock_items = await list_stock_for_variant(db, variant_id)
    if not stock_items:
        return None, None, None, None, None
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
    stock_available_at_entry: Optional[int],
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
            selectinload(Quotation.approvals),
        )
        .where(Quotation.id == quotation_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_quotations(db: AsyncSession) -> Sequence[Quotation]:
    # Quotation.approvals is selectin-loaded at the mapper, so the rounds come
    # back in one extra query for the whole page rather than one per row.
    stmt = select(Quotation).order_by(Quotation.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


_SORT_COLUMNS = {
    "number": Quotation.number,
    "customer": Customer.name,
    "total": Quotation.total,
    "status": Quotation.status,
    "risk": Quotation.blended_risk_score,
    "updated": Quotation.updated_at,
}


def _visible_to(stmt, viewer: User):
    """A rep sees their own deals; managers, finance and admin see everything.

    Applied in the query rather than filtered afterwards, so the row count and
    the pagination stay honest.
    """
    if viewer.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE):
        return stmt
    return stmt.where(Quotation.owner_id == viewer.id)


async def stage_counts(db: AsyncSession, viewer: User) -> dict[str, int]:
    """One grouped query behind every stage chip and Kanban column header."""
    stmt = _visible_to(
        select(Quotation.status, func.count()).select_from(Quotation), viewer
    ).group_by(Quotation.status)
    rows = (await db.execute(stmt)).all()
    counts = {status.value: 0 for status in QuotationStatus}
    for status, count in rows:
        counts[status.value] = int(count)
    return counts


async def search_quotations(
    db: AsyncSession,
    *,
    viewer: User,
    skip: int,
    limit: int,
    search: Optional[str] = None,
    status: Optional[QuotationStatus] = None,
    sort: str = "updated",
    order: str = "desc",
) -> tuple[Sequence[Quotation], int]:
    """The quotations list, paginated server-side.

    Joins the customer once so a search can match the company name and the
    sort can order by it, rather than loading every quotation to filter in
    Python.
    """
    base = _visible_to(select(Quotation).join(Customer, Quotation.customer_id == Customer.id), viewer)

    if status is not None:
        base = base.where(Quotation.status == status)
    if search:
        needle = f"%{search.strip()}%"
        base = base.where(
            or_(Quotation.number.ilike(needle), Customer.name.ilike(needle))
        )

    total = (
        await db.execute(
            select(func.count()).select_from(base.with_only_columns(Quotation.id).subquery())
        )
    ).scalar_one()

    column = _SORT_COLUMNS.get(sort, Quotation.updated_at)
    direction = column.asc() if order == "asc" else column.desc()
    # Number as the tiebreak so two quotations updated in the same millisecond
    # do not swap places between pages and hide a row.
    stmt = base.order_by(direction, Quotation.number.desc()).offset(skip).limit(limit)

    return list((await db.execute(stmt)).scalars().all()), int(total)


async def reload_quotation(db: AsyncSession, quotation: Quotation) -> Quotation:
    """The workspace's "Reload Data" action.

    Re-snapshots stock and re-runs the pricing and ceiling calculation from
    live catalog data. **Draft only**: nearly every column on a quotation line
    is a snapshot precisely so that an admin raising a ceiling while a quote
    sits with Finance cannot make the "Why This Quote Was Flagged" screen
    re-render as "OK".
    """
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only a draft can be reloaded from the catalog")

    for line in quotation.lines:
        if not line.variant_id:
            continue
        (
            warehouse_id,
            warehouse_name,
            warehouse_code,
            bin_location,
            available,
        ) = await _allocate_stock_line(
            db, variant_id=line.variant_id, quantity=line.quantity
        )
        _apply_stock_snapshot(
            line,
            warehouse_id=warehouse_id,
            warehouse_name=warehouse_name,
            warehouse_code=warehouse_code,
            warehouse_bin_location=bin_location,
            stock_available_at_entry=available,
        )
        db.add(line)

    quotation.last_activity_at = datetime.now(timezone.utc)
    return await recalculate_quotation(db, quotation)


async def delete_quotation(db: AsyncSession, quotation: Quotation) -> None:
    """Drafts only. Anything that has been submitted is part of an audit trail."""
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only a draft quotation can be deleted")
    await db.delete(quotation)
    await db.commit()


def _check_delivery_date(requested: date) -> None:
    """A date already gone is not a request, it is a mistake.

    Caught here rather than in the schema so the message names the field in
    the same voice as every other business rule.
    """
    if requested < date.today():
        raise ValueError("The requested delivery date is in the past")


async def create_draft_quotation(
    db: AsyncSession,
    *,
    owner: User,
    obj_in: QuotationCreate,
) -> Quotation:
    _check_delivery_date(obj_in.requested_delivery_date)
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


def _cost_in(amount, base_currency, target_currency) -> Decimal:
    """A base-currency cost expressed in the quote's currency."""
    value = Decimal(str(amount or 0))
    if not value or base_currency is None or target_currency is None:
        return value
    return convert(value, base_currency, target_currency)


async def _currency_pair(db: AsyncSession, currency_code: str):
    """This quote's currency and the base one, read once per recalculation.

    Two conversions need them. A variant's `unit_cost` is typed in the base
    currency while the line is denominated in the quote's, so margin has to
    bring the cost across or it subtracts dollars from rupees. And the risk
    exposure threshold is a single number, so the amounts compared against it
    have to share a unit.
    """
    from app.services.catalog_service import list_currencies

    currencies = list(await list_currencies(db))
    return (
        next((c for c in currencies if c.code == currency_code), None),
        next((c for c in currencies if c.is_base), None),
    )


async def recalculate_quotation(db: AsyncSession, quotation: Quotation) -> Quotation:
    customer = await get_customer_by_id(db, quotation.customer_id)
    if not customer:
        raise ValueError("Customer not found")

    quote_currency, base_currency = await _currency_pair(db, quotation.currency)
    exposure = Decimal("0")
    lines_counted = 0
    lines_over = 0
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
        # `unit_cost` is typed in the base currency; the line is priced in the
        # quote's. Subtracting one from the other without converting reported a
        # 15% margin as 88% on any quote not in the base currency - and the same
        # number gates the upsell panel and is snapshotted into sales_records.
        unit_cost = _cost_in(
            variant.unit_cost if variant else 0, base_currency, quote_currency
        )
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
        # The money actually being given away above policy, in the quote's
        # currency. This is what makes deal size count.
        exposure += over / Decimal("100") * line_net
        lines_counted += 1
        if over > 0:
            lines_over += 1

    quotation.customer_tier_id = customer.tier_id
    quotation.tier_max_discount_percent = float(customer.tier.max_discount_percent)
    quotation.subtotal = _money(subtotal)
    quotation.discount_total = _money(discount_total)
    quotation.tax_total = _money(tax_total)
    quotation.total = _money(total)
    quotation.margin_total = _money(margin_total)
    # Spec section 10, in four parts. The old score was
    # `8 x worst + 5 x weighted`, and on a single-line quotation the weighted
    # term equals the worst term - so it collapsed to 13 x points_over. Three
    # and a half points over the ceiling was already HIGH, seven and a half hit
    # the cap, and quantity cancelled out of a weighted mean entirely: a 1-unit
    # line and a 500-unit line at the same discount scored the same. "Slightly
    # over" and "wildly over on a huge order" were indistinguishable, so the
    # routing between Manager and Manager-then-Finance meant nothing.
    #
    #   severity  how far the worst single line is over
    #   spread    the revenue-weighted average breach
    #   exposure  the money given away above policy, the size signal
    #   breadth   one slip, or a pattern across the order
    weighted_mean = (weighted_over / subtotal_net) if subtotal_net else Decimal("0")
    exposure_in_base = (
        convert(exposure, quote_currency, base_currency)
        if exposure and quote_currency and base_currency
        else exposure
    )
    exposure_full = Decimal(str(settings.RISK_EXPOSURE_FULL))
    exposure_ratio = (
        min(Decimal("1"), exposure_in_base / exposure_full)
        if exposure_full > 0
        else Decimal("0")
    )
    breadth = (
        Decimal(lines_over) / Decimal(lines_counted) if lines_counted else Decimal("0")
    )
    score = min(
        Decimal("100"),
        Decimal(str(settings.RISK_WEIGHT_SEVERITY)) * max_over
        + Decimal(str(settings.RISK_WEIGHT_SPREAD)) * weighted_mean
        + Decimal(str(settings.RISK_WEIGHT_EXPOSURE)) * exposure_ratio
        + Decimal(str(settings.RISK_WEIGHT_BREADTH)) * breadth,
    )
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


async def _check_plan_capacity(
    db: AsyncSession,
    *,
    product: Product,
    variant: ProductVariant,
    quantity: int,
) -> None:
    """Refuses a subscription line that would oversell the plan.

    A plan is capped rather than stocked, so the limit is checked against the
    subscriptions already open on it - not against a warehouse. Paused ones
    still count: the seat is allocated, it is simply not billing.

    Measured against CONFIRMED subscriptions only. Two drafts could each pass
    and then both confirm; holding capacity from draft would need reservation
    semantics the plan does not ask for, and the confirm path is where a real
    system would take the seat.

    Physical products fall through untouched: their limit is stock, and line
    entry deliberately never refuses a short physical line, because that is
    exactly what the warehouse split and backorders exist for.
    """
    if not product.is_subscription or variant.available_quantity is None:
        return

    from app.models.billing import Subscription, SubscriptionStatus

    sold = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(Subscription.quantity), 0)).where(
                    Subscription.variant_id == variant.id,
                    Subscription.status.in_(
                        [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]
                    ),
                )
            )
        ).scalar_one()
    )

    remaining = max(int(variant.available_quantity) - sold, 0)
    if quantity > remaining:
        raise ValueError(
            f"{product.name}: only {remaining} of {variant.available_quantity} "
            f"licences are left to sell"
        )


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

    await _check_plan_capacity(
        db, product=product, variant=variant, quantity=obj_in.quantity
    )

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

    # An accepted upsell swaps the line to a dearer variant of the same product
    # rather than adding a second line. Doing it here means one path re-prices,
    # re-checks capacity and stock, and recalculates - the alternative was a
    # delete-then-add that leaves the quote briefly wrong and loses the
    # discount the rep had already agreed.
    if obj_in.variant_id is not None and obj_in.variant_id != line.variant_id:
        await _swap_variant(db, quotation, line, obj_in.variant_id, quantity)

    if quantity != line.quantity and line.is_recurring and line.product_id:
        product = await get_product_by_id(db, line.product_id)
        variant = await get_variant_by_id(db, line.variant_id)
        if product is not None and variant is not None:
            await _check_plan_capacity(
                db, product=product, variant=variant, quantity=quantity
            )

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
        # Already applied, along with everything a new variant changes.
        if field == "variant_id":
            continue
        setattr(line, field, value)
    db.add(line)
    await db.commit()
    quotation = await ensure_quotation_loaded(db, quotation.id)
    return await recalculate_quotation(db, quotation)


async def _swap_variant(
    db: AsyncSession,
    quotation: Quotation,
    line: QuotationLine,
    variant_id: uuid.UUID,
    quantity: int,
) -> None:
    """Move a line onto a different variant of the same product.

    Everything the line snapshotted from the old variant has to move with it -
    sku, name, cost, options and the price for this tier - or the quote would
    show one SKU at another's price. The product itself may not change: that is
    a different line, not an upgrade.
    """
    variant = await get_variant_by_id(db, variant_id)
    if not variant or not variant.is_active:
        raise ValueError("Variant not found")
    if variant.product_id != line.product_id:
        raise ValueError("That variant belongs to a different product")

    product = await get_product_by_id(db, variant.product_id)
    if not product or product.status != ProductStatus.ACTIVE:
        raise ValueError("Product not found")

    await _check_plan_capacity(db, product=product, variant=variant, quantity=quantity)

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

    line.variant_id = variant.id
    line.variant_name = None if variant.is_default else variant.name
    line.sku = variant.sku
    line.unit_price = _unit(unit_price)
    line.list_price_at_entry = _unit(unit_price)
    line.unit_cost = _money(variant.unit_cost)
    line.selected_options = variant.options

    # A different SKU may sit in a different warehouse, or nowhere at all.
    (
        warehouse_id,
        warehouse_name,
        warehouse_code,
        warehouse_bin_location,
        stock_available_at_entry,
    ) = await _allocate_stock_line(db, variant_id=variant.id, quantity=quantity)
    _apply_stock_snapshot(
        line,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        warehouse_code=warehouse_code,
        warehouse_bin_location=warehouse_bin_location,
        stock_available_at_entry=stock_available_at_entry,
    )


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


async def submit_quotation(
    db: AsyncSession, quotation: Quotation, submitted_by: User
) -> tuple[Quotation, Optional[Approval]]:
    """Submits a draft for approval, or auto-approves it.

    Both paths write a real approval round - see approval_service.open_round
    for why the no-approval case is a rule with zero steps rather than a
    branch. The routing decision itself is read from approval_rules.
    """
    quotation = await recalculate_quotation(db, quotation)
    if quotation.status != QuotationStatus.DRAFT:
        raise ValueError("Only draft quotations can be submitted")

    # Round 1 is a submit; anything after a return is a resubmit, which is what
    # the audit trail on the approval screen distinguishes.
    trigger = (
        ApprovalTrigger.REP_SUBMIT
        if not quotation.current_round
        else ApprovalTrigger.REP_RESUBMIT
    )
    approval = await approval_service.open_round(
        db, quotation=quotation, submitted_by=submitted_by, trigger=trigger
    )
    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_QUOTATION,
        entity_id=quotation.id,
        action=(
            AuditAction.SUBMITTED
            if trigger == ApprovalTrigger.REP_SUBMIT
            else AuditAction.RESUBMITTED
        ),
        user=submitted_by,
        context={
            "round": approval.round_number,
            "risk_band": quotation.risk_band.value,
            "blended_risk_score": float(quotation.blended_risk_score),
            "chain": [step.role.value for step in approval.steps],
        },
    )
    await db.commit()

    # After the commit, never before: a rolled-back submission must not have
    # already told a manager that something is waiting on them.
    #
    # A quotation inside every ceiling is approved by this point, so its split
    # is planned here rather than waiting for someone to press Confirm.
    await approval_service.plan_if_approved(db, quotation, submitted_by)

    from app.services.approval_notifications import notify_submitted

    await notify_submitted(db, approval=approval, quotation=quotation)

    quotation = await ensure_quotation_loaded(db, quotation.id)
    return quotation, quotation.approval


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
