"""Dashboard, deal health and reporting (mockup screens 2, 14 and 15)."""

from datetime import date
from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.models.analytics import AlertStatus, AlertType, DealHealthAlert
from app.models.approval import ApprovalStatus
from app.models.customer import Customer
from app.models.quotation import Quotation
from app.models.user import Role, User
from app.schemas.analytics import (
    AlertAction,
    AlertActionInput,
    AlertCounts,
    AlertRead,
    DashboardRead,
    ReportRead,
)
from app.services import export_service, health_service, report_service
from app.services.report_service import ReportFilters

router = APIRouter(
    dependencies=[
        Depends(
            require_roles(
                Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER, Role.FINANCE
            )
        )
    ]
)

# Nudging and escalating are management actions; a rep does not nudge himself.
require_manager = require_roles(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE)


@router.get("/dashboard", response_model=DashboardRead)
async def read_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Screen 2: the tiles and the activity feed."""
    return await report_service.dashboard(db, current_user)


# --------------------------------------------------------------------------- #
# Deal health
# --------------------------------------------------------------------------- #

def _alert_row(alert: DealHealthAlert, quotation, customer) -> AlertRead:
    return AlertRead(
        id=alert.id,
        quotation_id=alert.quotation_id,
        quotation_number=quotation.number if quotation else "—",
        customer_name=customer.name if customer else "—",
        owner_name=quotation.owner_name if quotation else None,
        alert_type=alert.alert_type,
        severity=alert.severity,
        detail=alert.detail,
        status=alert.status,
        flagged_at=alert.flagged_at,
        acted_at=alert.acted_at,
        action_note=alert.action_note,
    )


@router.get("/alerts", response_model=List[AlertRead])
async def read_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[AlertStatus] = Query(default=None, alias="status"),
) -> Any:
    """Screen 14's table. Resolved alerts are hidden unless asked for.

    Scoped like every other list: a rep sees flags on their own deals, not
    their colleagues' discount anomalies. Joined rather than fetched per row -
    it was two queries per alert, so a hundred alerts meant two hundred and one.
    """
    stmt = (
        select(DealHealthAlert, Quotation, Customer)
        .join(Quotation, DealHealthAlert.quotation_id == Quotation.id)
        .join(Customer, Quotation.customer_id == Customer.id)
        .order_by(DealHealthAlert.flagged_at.desc())
        .limit(200)
    )
    if status_filter is not None:
        stmt = stmt.where(DealHealthAlert.status == status_filter)
    else:
        stmt = stmt.where(DealHealthAlert.status != AlertStatus.RESOLVED)
    if not current_user.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE):
        stmt = stmt.where(Quotation.owner_id == current_user.id)

    rows = (await db.execute(stmt)).all()
    return [_alert_row(alert, quotation, customer) for alert, quotation, customer in rows]


@router.get("/alerts/counts", response_model=AlertCounts)
async def read_alert_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Scoped like the table below them: a rep's tiles count their own flags."""
    owner_id = (
        None
        if current_user.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE)
        else current_user.id
    )
    counts = await health_service.counts(db, owner_id=owner_id)
    return AlertCounts(
        stalled_deals=counts.get(AlertType.STALLED_DEAL.value, 0),
        discount_anomalies=counts.get(AlertType.DISCOUNT_ANOMALY.value, 0),
        delivery_slippage=counts.get(AlertType.DELIVERY_SLIPPAGE.value, 0),
        last_swept_at=await health_service.last_swept_at(),
    )


@router.post(
    "/alerts/sweep",
    response_model=AlertCounts,
    dependencies=[Depends(require_manager)],
)
async def run_sweep(db: AsyncSession = Depends(get_db)) -> Any:
    """Runs the detection now rather than waiting for the hourly schedule.

    Same function the scheduler calls - there is one implementation of the
    rules, not a manual copy that drifts.
    """
    await health_service.sweep(db)
    return await read_alert_counts(db=db)


@router.post(
    "/alerts/{alert_id}/action",
    response_model=AlertRead,
    dependencies=[Depends(require_manager)],
)
async def act_on_alert(
    alert_id: uuid.UUID,
    body: AlertActionInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Nudge the rep, escalate to their manager, or resolve it."""
    alert = await db.get(DealHealthAlert, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    mapping = {
        AlertAction.NUDGE: AlertStatus.NUDGED,
        AlertAction.ESCALATE: AlertStatus.ESCALATED,
        AlertAction.RESOLVE: AlertStatus.RESOLVED,
    }
    try:
        await health_service.act(
            db,
            alert=alert,
            action=mapping[body.action],
            user=current_user,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    await db.commit()

    if body.action in {AlertAction.NUDGE, AlertAction.ESCALATE}:
        from app.services.alert_notifications import notify_alert_action

        await notify_alert_action(db, alert=alert, action=body.action.value)

    quotation = await db.get(Quotation, alert.quotation_id)
    customer = await db.get(Customer, quotation.customer_id) if quotation else None
    return _alert_row(alert, quotation, customer)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def _filters(
    current_user: User = Depends(get_current_user),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    rep_id: Optional[uuid.UUID] = Query(default=None, alias="rep"),
    team_id: Optional[uuid.UUID] = Query(default=None, alias="team"),
    category: Optional[str] = Query(default=None),
    product_id: Optional[uuid.UUID] = Query(default=None, alias="product"),
    approval_status: Optional[ApprovalStatus] = Query(
        default=None, alias="approval_status"
    ),
) -> ReportFilters:
    """Spec A7's four filter dimensions, as one dependency so the report and
    both exports cannot drift apart.

    A sales rep is pinned to their own figures. `rep_id` already filters both
    the sales history and the quotation counts and is already part of the cache
    key, so forcing it here scopes the screen and both exports at once - and a
    rep passing somebody else's `?rep=` gets their own numbers, not a refusal
    that tells them the id was real.
    """
    if not current_user.has_role(Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE):
        rep_id = current_user.id
    return ReportFilters(
        date_from=date_from,
        date_to=date_to,
        rep_id=rep_id,
        team_id=team_id,
        category=category,
        product_id=product_id,
        approval_status=approval_status,
    )


@router.get("/reports", response_model=ReportRead)
async def read_report(
    db: AsyncSession = Depends(get_db),
    filters: ReportFilters = Depends(_filters),
) -> Any:
    """Screen 15."""
    return await report_service.build(db, filters)


@router.get("/reports/export.xlsx")
async def export_xlsx(
    db: AsyncSession = Depends(get_db),
    filters: ReportFilters = Depends(_filters),
) -> Response:
    rows = await report_service.rows_for_export(db, filters)
    return Response(
        content=export_service.to_xlsx(rows),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="dealflow-sales-{date.today()}.xlsx"'
            )
        },
    )


@router.get("/reports/export.pdf")
async def export_pdf(
    db: AsyncSession = Depends(get_db),
    filters: ReportFilters = Depends(_filters),
) -> Response:
    summary = await report_service.build(db, filters)
    rows = await report_service.rows_for_export(db, filters)
    return Response(
        content=export_service.to_pdf(summary, rows),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="dealflow-sales-{date.today()}.pdf"'
            )
        },
    )
