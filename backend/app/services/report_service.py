"""Reporting (mockup screen 15, spec A7).

Every figure comes from ``sales_records`` rather than from live quotation
lines. That is the whole reason the table exists: lines stay editable after
confirmation, so a report derived from them would silently change, and a "top
product" that shifts retroactively is worse than none. The reporting
dimensions - category, tier, team - are snapshotted there too, so a product
moving category cannot rewrite last quarter.

Results are cached on the filter set. Confirmation is the only thing that adds
a row, so a five-minute TTL is generous.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.cache import cached_json
from app.models.analytics import SalesRecord
from app.models.approval import Approval, ApprovalStatus
from app.models.quotation import Quotation, QuotationStatus


@dataclass(frozen=True)
class ReportFilters:
    """Spec A7's four dimensions: Period, Sales Team or Rep, Approval Status,
    Product or Category."""

    date_from: Optional[date] = None
    date_to: Optional[date] = None
    rep_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    category: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    approval_status: Optional[ApprovalStatus] = None

    def key(self) -> str:
        return "|".join(
            str(value) if value is not None else "-"
            for value in (
                self.date_from,
                self.date_to,
                self.rep_id,
                self.team_id,
                self.category,
                self.product_id,
                self.approval_status,
            )
        )


def _apply(stmt: Select, filters: ReportFilters) -> Select:
    if filters.date_from:
        stmt = stmt.where(SalesRecord.sold_at >= filters.date_from)
    if filters.date_to:
        # Inclusive of the end date: a report "to 31 March" that silently
        # excludes 31 March is a support ticket waiting to happen.
        stmt = stmt.where(
            SalesRecord.sold_at < filters.date_to + timedelta(days=1)
        )
    if filters.rep_id:
        stmt = stmt.where(SalesRecord.sales_rep_id == filters.rep_id)
    if filters.team_id:
        stmt = stmt.where(SalesRecord.sales_team_id == filters.team_id)
    if filters.category:
        stmt = stmt.where(SalesRecord.category == filters.category)
    if filters.product_id:
        stmt = stmt.where(SalesRecord.product_id == filters.product_id)
    return stmt


async def build(db: AsyncSession, filters: ReportFilters) -> dict[str, Any]:
    """The whole reporting screen in one cached payload."""

    async def load() -> dict[str, Any]:
        return await _build(db, filters)

    return await cached_json(
        cache.NS_REPORT, f"report:{filters.key()}", cache.TTL_REPORT, load
    )


async def _build(db: AsyncSession, filters: ReportFilters) -> dict[str, Any]:
    totals = (
        await db.execute(
            _apply(
                select(
                    func.count(func.distinct(SalesRecord.quotation_id)),
                    func.coalesce(func.sum(SalesRecord.line_total), 0),
                    func.coalesce(func.sum(SalesRecord.margin_amount), 0),
                    func.coalesce(func.avg(SalesRecord.discount_percent), 0),
                    func.coalesce(func.sum(SalesRecord.quantity), 0),
                ),
                filters,
            )
        )
    ).one()

    quotes_created = (
        await db.execute(select(func.count()).select_from(Quotation))
    ).scalar_one()
    quotes_confirmed = (
        await db.execute(
            select(func.count())
            .select_from(Quotation)
            .where(Quotation.status == QuotationStatus.CONFIRMED)
        )
    ).scalar_one()

    # Average approval time: how long a decided round actually took. Null
    # decided_at rows are still pending and would drag the average down.
    approval_seconds = (
        await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Approval.decided_at - Approval.submitted_at)
                )
            ).where(
                Approval.decided_at.isnot(None),
                Approval.status.in_(
                    [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]
                ),
            )
        )
    ).scalar_one_or_none()

    top_upsold = (
        await db.execute(
            _apply(
                select(
                    SalesRecord.product_name,
                    func.sum(SalesRecord.quantity).label("units"),
                    func.sum(SalesRecord.line_total).label("revenue"),
                ).where(SalesRecord.came_from_upsell.is_(True)),
                filters,
            )
            .group_by(SalesRecord.product_name)
            .order_by(func.sum(SalesRecord.line_total).desc())
            .limit(5)
        )
    ).all()

    best_selling = (
        await db.execute(
            _apply(
                select(
                    SalesRecord.product_name,
                    func.sum(SalesRecord.quantity).label("units"),
                    func.sum(SalesRecord.line_total).label("revenue"),
                ),
                filters,
            )
            .group_by(SalesRecord.product_name)
            .order_by(func.sum(SalesRecord.line_total).desc())
            .limit(10)
        )
    ).all()

    most_discounted = (
        await db.execute(
            _apply(
                select(
                    SalesRecord.product_name,
                    func.avg(SalesRecord.discount_percent).label("average"),
                    func.count().label("lines"),
                ),
                filters,
            )
            .group_by(SalesRecord.product_name)
            .order_by(func.avg(SalesRecord.discount_percent).desc())
            .limit(10)
        )
    ).all()

    by_rep = (
        await db.execute(
            _apply(
                select(
                    SalesRecord.sales_rep_name,
                    func.sum(SalesRecord.line_total).label("revenue"),
                    func.sum(SalesRecord.margin_amount).label("margin"),
                    func.avg(SalesRecord.discount_percent).label("discount"),
                ),
                filters,
            )
            .group_by(SalesRecord.sales_rep_name)
            .order_by(func.sum(SalesRecord.line_total).desc())
        )
    ).all()

    by_category = (
        await db.execute(
            _apply(
                select(
                    SalesRecord.category,
                    func.sum(SalesRecord.line_total).label("revenue"),
                    func.sum(SalesRecord.margin_amount).label("margin"),
                ),
                filters,
            )
            .group_by(SalesRecord.category)
            .order_by(func.sum(SalesRecord.line_total).desc())
        )
    ).all()

    return {
        "quotes_created": int(quotes_created),
        "quotes_confirmed": int(quotes_confirmed),
        "conversion_rate": (
            round(quotes_confirmed / quotes_created * 100, 1) if quotes_created else 0.0
        ),
        "orders": int(totals[0]),
        "revenue": float(totals[1]),
        "margin": float(totals[2]),
        "average_discount": round(float(totals[3]), 2),
        "units_sold": int(totals[4]),
        "average_approval_hours": (
            round(float(approval_seconds) / 3600, 1) if approval_seconds else None
        ),
        "top_upsold": [
            {"name": name, "units": int(units), "revenue": float(revenue)}
            for name, units, revenue in top_upsold
        ],
        "best_selling": [
            {"name": name, "units": int(units), "revenue": float(revenue)}
            for name, units, revenue in best_selling
        ],
        "most_discounted": [
            {"name": name, "average_discount": round(float(average), 2), "lines": int(lines)}
            for name, average, lines in most_discounted
        ],
        "by_rep": [
            {
                "name": name or "Unassigned",
                "revenue": float(revenue),
                "margin": float(margin),
                "average_discount": round(float(discount), 2),
            }
            for name, revenue, margin, discount in by_rep
        ],
        "by_category": [
            {
                "name": name or "Uncategorised",
                "revenue": float(revenue),
                "margin": float(margin),
            }
            for name, revenue, margin in by_category
        ],
    }


async def rows_for_export(
    db: AsyncSession, filters: ReportFilters
) -> list[dict[str, Any]]:
    """The flat line-level table behind the CSV and XLSX exports."""
    records = (
        await db.execute(
            _apply(select(SalesRecord), filters).order_by(SalesRecord.sold_at.desc())
        )
    ).scalars().all()

    return [
        {
            "Sold at": record.sold_at.strftime("%Y-%m-%d %H:%M"),
            "Product": record.product_name,
            "SKU": record.sku or "",
            "Category": record.category or "",
            "Rep": record.sales_rep_name or "",
            "Quantity": record.quantity,
            "Unit price": float(record.unit_price),
            "Discount %": float(record.discount_percent),
            "Line total": float(record.line_total),
            "Margin": float(record.margin_amount),
            "From upsell": "yes" if record.came_from_upsell else "no",
            "Recurring": "yes" if record.is_recurring else "no",
        }
        for record in records
    ]


async def dashboard(db: AsyncSession, viewer_id: Optional[uuid.UUID]) -> dict[str, Any]:
    """The home screen's tiles and activity feed (mockup screen 2)."""

    async def load() -> dict[str, Any]:
        from app.models.analytics import AlertStatus, DealHealthAlert
        from app.services import audit_service

        pending = (
            await db.execute(
                select(func.count())
                .select_from(Approval)
                .where(Approval.status == ApprovalStatus.PENDING)
            )
        ).scalar_one()
        open_quotes = (
            await db.execute(
                select(func.count())
                .select_from(Quotation)
                .where(
                    Quotation.status.in_(
                        [
                            QuotationStatus.DRAFT,
                            QuotationStatus.PENDING_APPROVAL,
                            QuotationStatus.APPROVED,
                            QuotationStatus.NEGOTIATION,
                        ]
                    )
                )
            )
        ).scalar_one()
        at_risk = (
            await db.execute(
                select(func.count())
                .select_from(DealHealthAlert)
                .where(DealHealthAlert.status != AlertStatus.RESOLVED)
            )
        ).scalar_one()
        pipeline_value = (
            await db.execute(
                select(func.coalesce(func.sum(Quotation.total), 0)).where(
                    Quotation.status.in_(
                        [
                            QuotationStatus.PENDING_APPROVAL,
                            QuotationStatus.APPROVED,
                            QuotationStatus.NEGOTIATION,
                        ]
                    )
                )
            )
        ).scalar_one()

        activity = await audit_service.recent(db, limit=8)
        return {
            "pending_approvals": int(pending),
            "open_quotations": int(open_quotes),
            "at_risk_deals": int(at_risk),
            "pipeline_value": float(pipeline_value),
            "recent_activity": [
                {
                    "id": str(entry.id),
                    "actor_name": entry.actor_name,
                    "action": entry.action.value,
                    "entity_type": entry.entity_type,
                    "entity_id": str(entry.entity_id),
                    "reason": entry.reason,
                    "context": entry.context,
                    "created_at": entry.created_at.isoformat(),
                }
                for entry in activity
            ],
        }

    return await cached_json(
        cache.NS_DASHBOARD, "home", cache.TTL_DASHBOARD, load
    )
