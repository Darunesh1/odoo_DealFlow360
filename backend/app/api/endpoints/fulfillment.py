"""Fulfillment and warehouse splitting (mockup screens 7 and 8).

Reads are open to every internal role so a rep can watch their own order move.
Writes - accepting a split, overriding it, shipping - belong to Finance and
Operations, which is who the spec puts in charge of "warehouse fulfillment
splits and backorder decisions".
"""

from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, get_db, get_pagination, require_roles
from app.models.customer import Customer
from app.models.fulfillment import (
    AllocationStatus,
    Fulfillment,
    FulfillmentStatus,
    Shipment,
    ShipmentLine,
    ShipmentStatus,
)
from app.models.inventory import StockItem, Warehouse
from app.models.quotation import Quotation
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.fulfillment import (
    AllocationRead,
    ShipmentLineRead,
    WarehouseSplitRow,
    FulfillmentDetail,
    FulfillmentRow,
    OverrideInput,
    ShipmentRead,
)
from app.services import fulfillment_service, order_service
from app.services.quotation_service import ensure_quotation_loaded

router = APIRouter(
    dependencies=[
        Depends(
            require_roles(
                Role.ADMIN, Role.FINANCE, Role.SALES_MANAGER, Role.SALES_REP
            )
        )
    ]
)

# Accepting, overriding and shipping move real stock, so they are narrower than
# the reads above.
require_operations = require_roles(Role.ADMIN, Role.FINANCE)


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _missing() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Fulfillment not found"
    )


async def _row(
    db: AsyncSession, fulfillment: Fulfillment, quotation: Quotation
) -> dict:
    warehouse_ids = {a.warehouse_id for a in fulfillment.allocations}
    names = []
    if warehouse_ids:
        names = [
            name
            for (name,) in (
                await db.execute(
                    select(Warehouse.name)
                    .where(Warehouse.id.in_(warehouse_ids))
                    .order_by(Warehouse.name)
                )
            ).all()
        ]
    return {
        "id": fulfillment.id,
        "quotation_id": quotation.id,
        "quotation_number": quotation.number,
        "customer_name": quotation.customer.name,
        "quotation_status": quotation.status,
        "status": fulfillment.status,
        "strategy": fulfillment.strategy,
        "currency": quotation.currency,
        "estimated_shipping_cost": float(fulfillment.estimated_shipping_cost),
        "estimated_shipment_count": fulfillment.estimated_shipment_count,
        "warehouse_names": names,
        "has_backorder": any(
            a.status == AllocationStatus.BACKORDERED for a in fulfillment.allocations
        ),
        "requested_delivery_date": fulfillment.requested_delivery_date,
        "accepted_at": fulfillment.accepted_at,
        "created_at": fulfillment.created_at,
    }


@router.get("/fulfillments", response_model=Page[FulfillmentRow])
async def read_fulfillments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pagination: Pagination = Depends(get_pagination),
    status_filter: Optional[FulfillmentStatus] = Query(default=None, alias="status"),
    open_only: bool = Query(default=False, description="Hide finished orders"),
) -> Any:
    """Screen 7's "Orders Awaiting Fulfillment" table."""
    base = select(Fulfillment, Quotation).join(
        Quotation, Fulfillment.quotation_id == Quotation.id
    )
    if not current_user.has_role(Role.ADMIN, Role.FINANCE, Role.SALES_MANAGER):
        base = base.where(Quotation.owner_id == current_user.id)
    if status_filter is not None:
        base = base.where(Fulfillment.status == status_filter)
    if open_only:
        base = base.where(
            Fulfillment.status.notin_(
                [FulfillmentStatus.FULFILLED, FulfillmentStatus.CANCELLED]
            )
        )

    total = (
        await db.execute(
            select(func.count()).select_from(
                base.with_only_columns(Fulfillment.id).subquery()
            )
        )
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Fulfillment.created_at.desc())
            .offset(pagination.skip)
            .limit(pagination.limit)
        )
    ).all()

    return Page[FulfillmentRow](
        items=[
            FulfillmentRow(**await _row(db, fulfillment, quotation))
            for fulfillment, quotation in rows
        ],
        total=int(total),
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(int(total)),
    )


async def _detail(
    db: AsyncSession, fulfillment: Fulfillment, quotation: Quotation
) -> FulfillmentDetail:
    lines = {line.id: line for line in quotation.lines}
    warehouses = {
        warehouse.id: warehouse
        for warehouse in (await db.execute(select(Warehouse))).scalars().all()
    }

    allocations = []
    can_consolidate = False
    for allocation in sorted(
        fulfillment.allocations, key=lambda a: (str(a.quotation_line_id), a.status.value)
    ):
        line = lines.get(allocation.quotation_line_id)
        warehouse = warehouses.get(allocation.warehouse_id)
        allocations.append(
            AllocationRead(
                id=allocation.id,
                quotation_line_id=allocation.quotation_line_id,
                line_label=line.product_name if line else "—",
                sku=line.sku if line else None,
                warehouse_id=allocation.warehouse_id,
                warehouse_name=warehouse.name if warehouse else "—",
                warehouse_code=warehouse.code if warehouse else "—",
                quantity=allocation.quantity,
                quantity_shipped=allocation.quantity_shipped,
                status=allocation.status,
                estimated_shipping_cost=float(allocation.estimated_shipping_cost),
                expected_restock_date=allocation.expected_restock_date,
                is_manual=allocation.is_manual,
            )
        )
        if allocation.status == AllocationStatus.BACKORDERED:
            stock = (
                await db.execute(
                    select(StockItem).where(
                        StockItem.warehouse_id == allocation.warehouse_id,
                        StockItem.variant_id == allocation.variant_id,
                    )
                )
            ).scalars().first()
            if stock is not None and int(stock.quantity_available) >= allocation.quantity:
                can_consolidate = True

    # One row per warehouse - the shape mockup screen 8 asks for, and the unit
    # a shipment is actually planned in.
    shipment_counts: dict[uuid.UUID, int] = {}
    for shipment in await fulfillment_service.list_shipments(db, fulfillment.id):
        shipment_counts[shipment.warehouse_id] = (
            shipment_counts.get(shipment.warehouse_id, 0) + 1
        )

    rollup: dict[tuple[uuid.UUID, bool], WarehouseSplitRow] = {}
    for allocation in fulfillment.allocations:
        warehouse = warehouses.get(allocation.warehouse_id)
        backordered = allocation.status == AllocationStatus.BACKORDERED
        # Backorders are kept apart from what is actually going out: folding
        # them together would show a warehouse "sending" units it does not have.
        key = (allocation.warehouse_id, backordered)
        row = rollup.get(key)
        if row is None:
            row = WarehouseSplitRow(
                warehouse_id=allocation.warehouse_id,
                warehouse_name=warehouse.name if warehouse else "—",
                warehouse_code=warehouse.code if warehouse else "—",
                quantity=0,
                quantity_shipped=0,
                shipment_count=0 if backordered else shipment_counts.get(allocation.warehouse_id, 0),
                cost=0.0,
                is_backorder=backordered,
            )
            rollup[key] = row
        row.quantity += allocation.quantity
        row.quantity_shipped += allocation.quantity_shipped
        row.cost = round(row.cost + float(allocation.estimated_shipping_cost), 2)
        if allocation.expected_restock_date and (
            row.expected_restock_date is None
            or allocation.expected_restock_date > row.expected_restock_date
        ):
            row.expected_restock_date = allocation.expected_restock_date

    by_warehouse = sorted(
        rollup.values(), key=lambda r: (r.is_backorder, r.warehouse_name)
    )

    line_labels = {line.id: line for line in quotation.lines}
    shipments = []
    for shipment in await fulfillment_service.list_shipments(db, fulfillment.id):
        shipment_lines = (
            await db.execute(
                select(ShipmentLine).where(ShipmentLine.shipment_id == shipment.id)
            )
        ).scalars().all()
        units = sum(row.quantity_shipped for row in shipment_lines)
        warehouse = warehouses.get(shipment.warehouse_id)
        shipments.append(
            ShipmentRead(
                id=shipment.id,
                reference=shipment.reference,
                warehouse_id=shipment.warehouse_id,
                warehouse_name=warehouse.name if warehouse else "—",
                status=shipment.status,
                estimated_cost=float(shipment.estimated_cost),
                # Nullable until the carrier bills: unknown, not zero.
                actual_cost=float(shipment.actual_cost or 0),
                shipped_at=shipment.shipped_at,
                delivered_at=shipment.delivered_at,
                unit_count=int(units),
                lines=[
                    ShipmentLineRead(
                        id=row.id,
                        line_label=(
                            line_labels[row.quotation_line_id].product_name
                            if row.quotation_line_id in line_labels
                            else "—"
                        ),
                        sku=(
                            line_labels[row.quotation_line_id].sku
                            if row.quotation_line_id in line_labels
                            else None
                        ),
                        quantity_shipped=row.quantity_shipped,
                        quantity_invoiced=row.quantity_invoiced,
                    )
                    for row in shipment_lines
                ],
            )
        )

    return FulfillmentDetail(
        **await _row(db, fulfillment, quotation),
        by_warehouse=by_warehouse,
        allocations=allocations,
        shipments=shipments,
        can_consolidate=can_consolidate,
        consolidated_at=fulfillment.consolidated_at,
    )


async def _load(db: AsyncSession, fulfillment_id: uuid.UUID):
    fulfillment = await fulfillment_service.load_fulfillment(db, fulfillment_id)
    if fulfillment is None:
        raise _missing()
    quotation = await ensure_quotation_loaded(db, fulfillment.quotation_id)
    return fulfillment, quotation


@router.get("/fulfillments/{fulfillment_id}", response_model=FulfillmentDetail)
async def read_fulfillment(
    fulfillment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    """Screen 8: the recommended split, its cost, and the shipments behind it."""
    fulfillment, quotation = await _load(db, fulfillment_id)
    return await _detail(db, fulfillment, quotation)


@router.post("/quotations/{quotation_id}/confirm", response_model=FulfillmentDetail)
async def confirm_quotation(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Turns an approved quotation into an order and plans its split."""
    quotation = await ensure_quotation_loaded(db, quotation_id)
    # The same ownership rule GET /fulfillments applies. Without it any rep
    # could confirm any other rep's approved deal by id.
    if not current_user.has_role(Role.ADMIN, Role.FINANCE, Role.SALES_MANAGER):
        if quotation.owner_id != current_user.id:
            raise _missing()
    try:
        fulfillment = await order_service.confirm_quotation(
            db, quotation=quotation, user=current_user
        )
    except ValueError as exc:
        raise _bad(str(exc))
    quotation = await ensure_quotation_loaded(db, quotation_id)
    return await _detail(db, fulfillment, quotation)


@router.post(
    "/fulfillments/{fulfillment_id}/accept",
    response_model=FulfillmentDetail,
    dependencies=[Depends(require_operations)],
)
async def accept_split(
    fulfillment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Reserves the planned stock and opens one shipment per warehouse."""
    fulfillment, quotation = await _load(db, fulfillment_id)
    try:
        await fulfillment_service.accept_split(
            db, fulfillment=fulfillment, user=current_user
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    fulfillment, quotation = await _load(db, fulfillment_id)
    return await _detail(db, fulfillment, quotation)


@router.post(
    "/fulfillments/{fulfillment_id}/override",
    response_model=FulfillmentDetail,
    dependencies=[Depends(require_operations)],
)
async def override_split(
    fulfillment_id: uuid.UUID,
    body: OverrideInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Replaces the planner's split with a human one."""
    fulfillment, quotation = await _load(db, fulfillment_id)
    try:
        await fulfillment_service.manual_override(
            db,
            fulfillment=fulfillment,
            quotation=quotation,
            rows=[row.model_dump(mode="json") for row in body.rows],
            user=current_user,
        )
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    fulfillment, quotation = await _load(db, fulfillment_id)
    return await _detail(db, fulfillment, quotation)


@router.post(
    "/fulfillments/{fulfillment_id}/consolidate",
    response_model=FulfillmentDetail,
    dependencies=[Depends(require_operations)],
)
async def consolidate(
    fulfillment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    """"Consolidate Remaining Backorder", run on demand.

    The same sweep the scheduler runs every fifteen minutes, narrowed to this
    order - the button names one fulfillment, so it should not quietly touch
    every other order in the system.
    """
    await fulfillment_service.consolidate_backorders(db, fulfillment_id=fulfillment_id)
    fulfillment, quotation = await _load(db, fulfillment_id)
    return await _detail(db, fulfillment, quotation)


@router.post(
    "/shipments/{shipment_id}/ship",
    response_model=FulfillmentDetail,
    dependencies=[Depends(require_operations)],
)
async def ship_shipment(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Dispatches a shipment, which is what makes its units billable."""
    shipment = await db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found"
        )
    try:
        await fulfillment_service.ship(db, shipment=shipment, user=current_user)
    except ValueError as exc:
        raise _bad(str(exc))
    await db.commit()
    fulfillment, quotation = await _load(db, shipment.fulfillment_id)
    return await _detail(db, fulfillment, quotation)
