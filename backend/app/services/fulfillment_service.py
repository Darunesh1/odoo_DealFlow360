"""Warehouse splitting, reservations, backorders and shipments (spec B6).

The planner's objective, in order:

1. **Fewest warehouses touched.** Every extra warehouse is another shipment,
   another tracking number and another thing to go wrong. Deepest stock first
   is what minimises that count.
2. **Cheaper warehouse breaks a tie.** Two warehouses that can both cover the
   line are decided on the rates a human entered.
3. **The remainder backorders.** A line no warehouse can cover is not an
   error - it is the case this whole module exists for.

Reservations are taken under a row lock, because two reps confirming the last
three laptops at the same instant must not both succeed.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analytics import AuditAction
from app.models.fulfillment import (
    AllocationStatus,
    Fulfillment,
    FulfillmentAllocation,
    FulfillmentStatus,
    Shipment,
    ShipmentLine,
    ShipmentStatus,
    SplitStrategy,
)
from app.models.inventory import StockItem, Warehouse
from app.models.quotation import Quotation, QuotationLine
from app.models.user import User
from app.services import audit_service


def shipping_cost(warehouse: Warehouse, units: int) -> float:
    """What one shipment of `units` from this warehouse costs.

    Straight arithmetic over the two figures an admin typed - nothing here is
    invented.
    """
    return round(
        float(warehouse.shipping_base_cost)
        + float(warehouse.shipping_cost_per_unit) * units,
        2,
    )


async def load_fulfillment(
    db: AsyncSession, fulfillment_id: uuid.UUID
) -> Optional[Fulfillment]:
    result = await db.execute(
        select(Fulfillment)
        .options(selectinload(Fulfillment.allocations))
        .where(Fulfillment.id == fulfillment_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def get_for_quotation(
    db: AsyncSession, quotation_id: uuid.UUID
) -> Optional[Fulfillment]:
    result = await db.execute(
        select(Fulfillment)
        .options(selectinload(Fulfillment.allocations))
        .where(Fulfillment.quotation_id == quotation_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def _stock_for(
    db: AsyncSession, variant_id: uuid.UUID
) -> list[tuple[StockItem, Warehouse]]:
    """Availability per warehouse, deepest first then cheapest."""
    result = await db.execute(
        select(StockItem, Warehouse)
        .join(Warehouse, StockItem.warehouse_id == Warehouse.id)
        .where(StockItem.variant_id == variant_id, Warehouse.is_active.is_(True))
        .order_by(
            StockItem.quantity_available.desc(),
            Warehouse.shipping_base_cost.asc(),
            Warehouse.name.asc(),
        )
    )
    return list(result.all())


async def plan_split(
    db: AsyncSession, *, fulfillment: Fulfillment, quotation: Quotation
) -> Fulfillment:
    """Builds the recommended split, replacing any previous plan.

    Subscription lines are skipped entirely: a recurring plan has no stock and
    nothing to ship, and putting it on the split screen would invite someone to
    wait for a warehouse to send it.

    Allocations are written by foreign key rather than appended to
    ``fulfillment.allocations``. Reading that collection here would fire a lazy
    load - the autoflush from the first stock query makes the fulfillment
    persistent without marking its collections loaded - and under asyncpg a
    lazy load outside an await is a MissingGreenlet, not a query.
    """
    await db.execute(
        delete(FulfillmentAllocation).where(
            FulfillmentAllocation.fulfillment_id == fulfillment.id
        )
    )

    today = date.today()
    total_cost = 0.0
    warehouses_used: set[uuid.UUID] = set()
    planned: list[FulfillmentAllocation] = []

    for line in quotation.lines:
        if line.is_recurring or not line.variant_id:
            continue

        remaining = int(line.quantity)
        for stock, warehouse in await _stock_for(db, line.variant_id):
            if remaining <= 0:
                break
            take = min(remaining, int(stock.quantity_available))
            if take <= 0:
                continue
            cost = shipping_cost(warehouse, take)
            total_cost += cost
            warehouses_used.add(warehouse.id)
            planned.append(
                FulfillmentAllocation(
                    quotation_line_id=line.id,
                    warehouse_id=warehouse.id,
                    variant_id=line.variant_id,
                    product_id=line.product_id,
                    quantity=take,
                    status=AllocationStatus.PLANNED,
                    estimated_shipping_cost=cost,
                )
            )
            remaining -= take

        if remaining > 0:
            # Nothing on hand anywhere. A backorder holds no stock and has no
            # warehouse cost yet, so it is charged when it actually ships.
            fallback = await _default_warehouse(db)
            planned.append(
                FulfillmentAllocation(
                    quotation_line_id=line.id,
                    warehouse_id=fallback.id,
                    variant_id=line.variant_id,
                    product_id=line.product_id,
                    quantity=remaining,
                    status=AllocationStatus.BACKORDERED,
                    estimated_shipping_cost=0,
                    expected_restock_date=today
                    + timedelta(days=int(fallback.default_lead_time_days)),
                )
            )

    fulfillment.estimated_shipping_cost = round(total_cost, 2)
    fulfillment.estimated_shipment_count = len(warehouses_used)
    fulfillment.strategy = SplitStrategy.SUGGESTED
    fulfillment.status = (
        FulfillmentStatus.BACKORDER
        if any(a.status == AllocationStatus.BACKORDERED for a in planned)
        else FulfillmentStatus.SPLIT_PENDING
    )
    # Frozen so Manual Override can rewrite allocations destructively and
    # Finance can still see what was proposed.
    fulfillment.suggestion_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "estimated_shipping_cost": fulfillment.estimated_shipping_cost,
        "estimated_shipment_count": fulfillment.estimated_shipment_count,
        "allocations": [
            {
                "quotation_line_id": str(a.quotation_line_id),
                "warehouse_id": str(a.warehouse_id),
                "quantity": a.quantity,
                "status": a.status.value,
            }
            for a in planned
        ],
    }
    db.add(fulfillment)
    # The id has to exist before the children can point at it.
    await db.flush()
    for allocation in planned:
        allocation.fulfillment_id = fulfillment.id
        db.add(allocation)
    await db.flush()
    return fulfillment


async def _default_warehouse(db: AsyncSession) -> Warehouse:
    """Where a backorder is booked against when nothing is on hand anywhere."""
    result = await db.execute(
        select(Warehouse)
        .where(Warehouse.is_active.is_(True))
        .order_by(Warehouse.shipping_base_cost.asc(), Warehouse.name.asc())
        .limit(1)
    )
    warehouse = result.scalars().first()
    if warehouse is None:
        raise ValueError("No active warehouse to fulfil from")
    return warehouse


async def accept_split(
    db: AsyncSession, *, fulfillment: Fulfillment, user: Optional[User] = None
) -> Fulfillment:
    """Turns the plan into held stock and planned shipments.

    Every planned allocation moves to RESERVED and its units are added to
    stock_items.quantity_reserved under a row lock, so two confirmations of the
    last three laptops cannot both succeed.
    """
    if fulfillment.accepted_at is not None:
        raise ValueError("This split has already been accepted")

    by_warehouse: dict[uuid.UUID, int] = {}

    for allocation in fulfillment.allocations:
        if allocation.status != AllocationStatus.PLANNED:
            continue

        stock = (
            await db.execute(
                select(StockItem)
                .where(
                    StockItem.warehouse_id == allocation.warehouse_id,
                    StockItem.variant_id == allocation.variant_id,
                )
                .with_for_update()
            )
        ).scalars().first()

        if stock is None or int(stock.quantity_available) < allocation.quantity:
            # Someone else took it between planning and accepting. Backorder
            # rather than fail: the order is still good, the stock is not.
            allocation.status = AllocationStatus.BACKORDERED
            allocation.expected_restock_date = date.today() + timedelta(days=7)
            db.add(allocation)
            continue

        stock.quantity_reserved = int(stock.quantity_reserved) + allocation.quantity
        allocation.status = AllocationStatus.RESERVED
        db.add(stock)
        db.add(allocation)
        by_warehouse[allocation.warehouse_id] = (
            by_warehouse.get(allocation.warehouse_id, 0) + allocation.quantity
        )

    # One PLANNED shipment per warehouse. "Est. Shipments" on the split screen
    # is COUNT(*) of these rather than a stored integer, so the estimate and
    # the reality are the same rows in two states.
    for warehouse_id, units in by_warehouse.items():
        warehouse = await db.get(Warehouse, warehouse_id)
        db.add(
            Shipment(
                fulfillment_id=fulfillment.id,
                warehouse_id=warehouse_id,
                reference=_shipment_reference(),
                status=ShipmentStatus.PLANNED,
                estimated_cost=shipping_cost(warehouse, units) if warehouse else 0,
            )
        )

    fulfillment.accepted_at = datetime.now(timezone.utc)
    if user is not None:
        fulfillment.accepted_by_id = user.id
    fulfillment.status = _roll_up(fulfillment)

    # The promise is made here, once the split is real, because until stock is
    # actually reserved there is nothing to promise against. It is the later of
    # what the customer asked for and the earliest everything can be dispatched
    # - promising their date when a backorder clears after it would be a
    # promise we already know we cannot keep.
    earliest = max(
        [date.today()]
        + [
            allocation.expected_restock_date
            for allocation in fulfillment.allocations
            if allocation.status == AllocationStatus.BACKORDERED
            and allocation.expected_restock_date is not None
        ]
    )
    requested = fulfillment.requested_delivery_date
    fulfillment.promised_ship_date = earliest
    db.add(fulfillment)

    quotation = await db.get(Quotation, fulfillment.quotation_id)
    if quotation is not None:
        quotation.promised_delivery_date = (
            max(earliest, requested) if requested else earliest
        )
        db.add(quotation)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_FULFILLMENT,
        entity_id=fulfillment.id,
        action=AuditAction.CONFIRMED,
        user=user,
        reason="Suggested split accepted",
        context={"shipments": len(by_warehouse)},
    )
    return fulfillment


def _shipment_reference() -> str:
    import secrets

    return f"SHP-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2).upper()}"


def _roll_up(fulfillment: Fulfillment) -> FulfillmentStatus:
    """The fulfillment's status is whatever its allocations collectively say."""
    return _roll_up_from(fulfillment.allocations)


def _roll_up_from(allocations) -> FulfillmentStatus:
    statuses = {allocation.status for allocation in allocations}
    if not statuses:
        return FulfillmentStatus.FULFILLED
    if statuses == {AllocationStatus.SHIPPED}:
        return FulfillmentStatus.FULFILLED
    if AllocationStatus.SHIPPED in statuses or AllocationStatus.PARTIALLY_SHIPPED in statuses:
        return FulfillmentStatus.PARTIALLY_SHIPPED
    if AllocationStatus.BACKORDERED in statuses:
        return FulfillmentStatus.BACKORDER
    if AllocationStatus.RESERVED in statuses:
        return FulfillmentStatus.RESERVED
    return FulfillmentStatus.SPLIT_PENDING


async def manual_override(
    db: AsyncSession,
    *,
    fulfillment: Fulfillment,
    quotation: Quotation,
    rows: Sequence[dict],
    user: Optional[User] = None,
) -> Fulfillment:
    """Replaces the planner's split with a human one.

    Validated hard, because this is the one place a person can invent numbers:
    every line's allocations must still total that line's quantity, and no
    warehouse may be drawn below what it actually holds. A split that ships
    fewer units than were sold is an invoice that will never reconcile.
    """
    if fulfillment.accepted_at is not None:
        raise ValueError("Accepted splits cannot be re-planned; ship or consolidate instead")

    lines = {line.id: line for line in quotation.lines if not line.is_recurring}

    wanted: dict[uuid.UUID, int] = {}
    for row in rows:
        line_id = uuid.UUID(str(row["quotation_line_id"]))
        if line_id not in lines:
            raise ValueError("A row names a line that is not on this order")
        quantity = int(row["quantity"])
        if quantity <= 0:
            raise ValueError("Every row needs a positive quantity")
        wanted[line_id] = wanted.get(line_id, 0) + quantity

    for line_id, line in lines.items():
        supplied = wanted.get(line_id, 0)
        if supplied != int(line.quantity):
            raise ValueError(
                f"{line.product_name}: allocated {supplied} of {line.quantity} units"
            )

    # Availability check per (warehouse, variant), summed across rows so two
    # rows drawing on the same shelf cannot each pass on their own.
    drawn: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for row in rows:
        if str(row.get("status", "")) == AllocationStatus.BACKORDERED.value:
            continue
        line = lines[uuid.UUID(str(row["quotation_line_id"]))]
        key = (uuid.UUID(str(row["warehouse_id"])), line.variant_id)
        drawn[key] = drawn.get(key, 0) + int(row["quantity"])

    for (warehouse_id, variant_id), units in drawn.items():
        stock = (
            await db.execute(
                select(StockItem).where(
                    StockItem.warehouse_id == warehouse_id,
                    StockItem.variant_id == variant_id,
                )
            )
        ).scalars().first()
        available = int(stock.quantity_available) if stock else 0
        if units > available:
            warehouse = await db.get(Warehouse, warehouse_id)
            raise ValueError(
                f"{warehouse.name if warehouse else 'That warehouse'} holds "
                f"{available}, not {units}"
            )

    # Same reason as plan_split: written by foreign key, not through the
    # relationship, so nothing here depends on the collection being loaded.
    await db.execute(
        delete(FulfillmentAllocation).where(
            FulfillmentAllocation.fulfillment_id == fulfillment.id
        )
    )

    total_cost = 0.0
    warehouses_used: set[uuid.UUID] = set()
    replacements: list[FulfillmentAllocation] = []
    for row in rows:
        line = lines[uuid.UUID(str(row["quotation_line_id"]))]
        warehouse_id = uuid.UUID(str(row["warehouse_id"]))
        quantity = int(row["quantity"])
        backordered = str(row.get("status", "")) == AllocationStatus.BACKORDERED.value
        warehouse = await db.get(Warehouse, warehouse_id)
        # Finance may state the cost outright; otherwise it comes from the rates.
        cost = (
            0.0
            if backordered
            else float(row.get("estimated_shipping_cost") or shipping_cost(warehouse, quantity))
        )
        total_cost += cost
        if not backordered:
            warehouses_used.add(warehouse_id)
        replacements.append(
            FulfillmentAllocation(
                quotation_line_id=line.id,
                warehouse_id=warehouse_id,
                variant_id=line.variant_id,
                product_id=line.product_id,
                quantity=quantity,
                status=(
                    AllocationStatus.BACKORDERED
                    if backordered
                    else AllocationStatus.PLANNED
                ),
                estimated_shipping_cost=cost,
                expected_restock_date=(
                    date.today() + timedelta(days=int(warehouse.default_lead_time_days))
                    if backordered and warehouse
                    else None
                ),
                is_manual=True,
            )
        )

    for allocation in replacements:
        allocation.fulfillment_id = fulfillment.id
        db.add(allocation)
    await db.flush()

    fulfillment.estimated_shipping_cost = round(total_cost, 2)
    fulfillment.estimated_shipment_count = len(warehouses_used)
    fulfillment.strategy = SplitStrategy.MANUAL_OVERRIDE
    fulfillment.status = _roll_up_from(replacements)
    db.add(fulfillment)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_FULFILLMENT,
        entity_id=fulfillment.id,
        action=AuditAction.EDITED,
        user=user,
        reason="Split overridden by hand",
        context={"rows": len(rows), "cost": fulfillment.estimated_shipping_cost},
    )
    return fulfillment


async def ship(
    db: AsyncSession, *, shipment: Shipment, user: Optional[User] = None
) -> Shipment:
    """Dispatches everything reserved at this shipment's warehouse.

    Writes the ShipmentLines that invoicing reads. Until this runs, an order
    has nothing billable on it at all - which is the whole of "nothing is
    billed before it ships".
    """
    if shipment.status not in {ShipmentStatus.PLANNED, ShipmentStatus.PICKING}:
        raise ValueError("That shipment has already gone out")

    fulfillment = await load_fulfillment(db, shipment.fulfillment_id)
    if fulfillment is None:
        raise ValueError("Fulfillment not found")

    shipped_any = False
    for allocation in fulfillment.allocations:
        if allocation.warehouse_id != shipment.warehouse_id:
            continue
        if allocation.status != AllocationStatus.RESERVED:
            continue

        outstanding = allocation.quantity - allocation.quantity_shipped
        if outstanding <= 0:
            continue

        stock = (
            await db.execute(
                select(StockItem)
                .where(
                    StockItem.warehouse_id == allocation.warehouse_id,
                    StockItem.variant_id == allocation.variant_id,
                )
                .with_for_update()
            )
        ).scalars().first()
        if stock is not None:
            # Both counters drop: the units leave the building and stop being
            # held. Decrementing only one would leak reserved stock forever.
            stock.quantity_on_hand = int(stock.quantity_on_hand) - outstanding
            stock.quantity_reserved = max(
                int(stock.quantity_reserved) - outstanding, 0
            )
            db.add(stock)

        allocation.quantity_shipped += outstanding
        allocation.status = AllocationStatus.SHIPPED
        db.add(allocation)

        db.add(
            ShipmentLine(
                shipment_id=shipment.id,
                allocation_id=allocation.id,
                quotation_line_id=allocation.quotation_line_id,
                variant_id=allocation.variant_id,
                product_id=allocation.product_id,
                quantity_shipped=outstanding,
            )
        )
        shipped_any = True

    if not shipped_any:
        raise ValueError("Nothing is reserved at that warehouse to ship")

    shipment.status = ShipmentStatus.SHIPPED
    shipment.shipped_at = datetime.now(timezone.utc)
    db.add(shipment)

    fulfillment.status = _roll_up(fulfillment)
    db.add(fulfillment)

    audit_service.record(
        db,
        entity_type=audit_service.ENTITY_FULFILLMENT,
        entity_id=fulfillment.id,
        action=AuditAction.CONFIRMED,
        user=user,
        reason=f"Shipment {shipment.reference} dispatched",
    )
    return shipment


async def consolidate_backorders(
    db: AsyncSession, *, fulfillment_id: Optional[uuid.UUID] = None
) -> int:
    """The sweep behind the mockup's automatic prompt.

    When stock arrives at a warehouse a backordered allocation is waiting on,
    it is reserved and folded into that warehouse's existing planned shipment
    rather than opening a second one - which is exactly what "Consolidate
    Remaining Backorder" means.

    `fulfillment_id` narrows it to one order, which is what the button on the
    split screen means; the scheduler calls it with none and sweeps everything.
    """
    stmt = (
        select(FulfillmentAllocation)
        .where(FulfillmentAllocation.status == AllocationStatus.BACKORDERED)
        .order_by(FulfillmentAllocation.created_at.asc())
    )
    if fulfillment_id is not None:
        stmt = stmt.where(FulfillmentAllocation.fulfillment_id == fulfillment_id)

    backordered = (await db.execute(stmt)).scalars().all()

    merged = 0
    touched: set[uuid.UUID] = set()

    for allocation in backordered:
        stock = (
            await db.execute(
                select(StockItem)
                .where(
                    StockItem.warehouse_id == allocation.warehouse_id,
                    StockItem.variant_id == allocation.variant_id,
                )
                .with_for_update()
            )
        ).scalars().first()
        if stock is None or int(stock.quantity_available) < allocation.quantity:
            continue

        stock.quantity_reserved = int(stock.quantity_reserved) + allocation.quantity
        allocation.status = AllocationStatus.RESERVED
        db.add(stock)
        db.add(allocation)
        merged += 1
        touched.add(allocation.fulfillment_id)

        existing = (
            await db.execute(
                select(Shipment).where(
                    Shipment.fulfillment_id == allocation.fulfillment_id,
                    Shipment.warehouse_id == allocation.warehouse_id,
                    Shipment.status == ShipmentStatus.PLANNED,
                )
            )
        ).scalars().first()
        if existing is None:
            warehouse = await db.get(Warehouse, allocation.warehouse_id)
            db.add(
                Shipment(
                    fulfillment_id=allocation.fulfillment_id,
                    warehouse_id=allocation.warehouse_id,
                    reference=_shipment_reference(),
                    status=ShipmentStatus.PLANNED,
                    estimated_cost=(
                        shipping_cost(warehouse, allocation.quantity) if warehouse else 0
                    ),
                )
            )

    for fulfillment_id in touched:
        fulfillment = await load_fulfillment(db, fulfillment_id)
        if fulfillment is not None:
            fulfillment.consolidated_at = datetime.now(timezone.utc)
            fulfillment.status = _roll_up(fulfillment)
            db.add(fulfillment)

    if merged:
        await db.commit()
    return merged


async def list_shipments(
    db: AsyncSession, fulfillment_id: uuid.UUID
) -> Sequence[Shipment]:
    result = await db.execute(
        select(Shipment)
        .where(Shipment.fulfillment_id == fulfillment_id)
        .order_by(Shipment.created_at.asc())
    )
    return result.scalars().all()
