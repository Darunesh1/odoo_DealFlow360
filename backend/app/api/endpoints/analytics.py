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

async def _alert_row(db: AsyncSession, alert: DealHealthAlert) -> AlertRead:
    quotation = await db.get(Quotation, alert.quotation_id)
    customer = (
        await db.get(Customer, quotation.customer_id) if quotation else None
    )
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
    status_filter: Optional[AlertStatus] = Query(default=None, alias="status"),
) -> Any:
    """Screen 14's table. Resolved alerts are hidden unless asked for."""
    alerts = await health_service.list_alerts(db, status=status_filter)
    return [await _alert_row(db, alert) for alert in alerts]


@router.get("/alerts/counts", response_model=AlertCounts)
async def read_alert_counts(db: AsyncSession = Depends(get_db)) -> Any:
    counts = await health_service.counts(db)
    return AlertCounts(
        stalled_deals=counts.get(AlertType.STALLED_DEAL.value, 0),
        discount_anomalies=counts.get(AlertType.DISCOUNT_ANOMALY.value, 0),
        delivery_slippage=counts.get(AlertType.DELIVERY_SLIPPAGE.value, 0),
    )


@router.post("/alerts/sweep", response_model=AlertCounts)
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

    return await _alert_row(db, alert)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def _filters(
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
    both exports cannot drift apart."""
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
