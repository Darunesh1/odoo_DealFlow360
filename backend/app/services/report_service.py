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


def _apply_to_quotations(stmt: Select, filters: ReportFilters) -> Select:
    """The same filter set, expressed against quotations rather than history.

    Only the dimensions a quotation actually carries: period, rep and team.
    Category and product live on the line, so filtering a quotation count by
    them would need a join that changes what "a quote" means.
    """
    if filters.date_from:
        stmt = stmt.where(Quotation.created_at >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(
            Quotation.created_at < filters.date_to + timedelta(days=1)
        )
    if filters.rep_id:
        stmt = stmt.where(Quotation.owner_id == filters.rep_id)
    if filters.team_id:
        stmt = stmt.where(Quotation.sales_team_id == filters.team_id)
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

    # These three read quotations rather than sales history, so they take the
    # filters through _apply_to_quotations rather than _apply. Before this they
    # ignored every filter, and a conversion rate built from a filtered
    # numerator over an unfiltered denominator meant nothing at all.
    quotes_created = (
        await db.execute(
            _apply_to_quotations(select(func.count()).select_from(Quotation), filters)
        )
    ).scalar_one()
    quotes_confirmed = (
        await db.execute(
            _apply_to_quotations(
                select(func.count())
                .select_from(Quotation)
                .where(Quotation.status == QuotationStatus.CONFIRMED),
                filters,
            )
        )
    ).scalar_one()

    # Average approval time: how long a decided round actually took. Null
    # decided_at rows are still pending and would drag the average down.
    approval_stmt = (
        select(
            func.avg(
                func.extract("epoch", Approval.decided_at - Approval.submitted_at)
            )
        )
        .select_from(Approval)
        .join(Quotation, Approval.quotation_id == Quotation.id)
        .where(
            Approval.decided_at.isnot(None),
            Approval.status.in_([ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]),
        )
    )
    approval_seconds = (
        await db.execute(_apply_to_quotations(approval_stmt, filters))
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


# Which quotation states count as "still in play". Shared so the dashboard and
# the quotation list cannot drift into two different definitions of "open".
OPEN_STATES = [
    QuotationStatus.DRAFT,
    QuotationStatus.PENDING_APPROVAL,
    QuotationStatus.APPROVED,
    QuotationStatus.NEGOTIATION,
]
PIPELINE_STATES = [
    QuotationStatus.PENDING_APPROVAL,
    QuotationStatus.APPROVED,
    QuotationStatus.NEGOTIATION,
]


def _owned_by(stmt, viewer):
    """The same predicate the quotations and approvals lists apply.

    A rep's dashboard has to count what their own screens count. Before this,
    the tiles were company-wide while every list they linked to was
    owner-scoped, so a rep saw "4 pending approvals" and then an empty inbox.
    """
    from app.models.user import Role

    if viewer is None or viewer.has_role(
        Role.ADMIN, Role.SALES_MANAGER, Role.FINANCE
    ):
        return stmt
    return stmt.where(Quotation.owner_id == viewer.id)


async def dashboard(db: AsyncSession, viewer) -> dict[str, Any]:
    """The home screen, scoped to whoever is looking at it (mockup screen 2).

    Every figure is computed from the same query as the screen its tile links
    to, and the cache key carries the viewer - a single shared key would serve
    one person's scoped numbers to everybody.
    """
    from app.models.user import Role

    role_key = "admin"
    if viewer is not None:
        if viewer.has_role(Role.ADMIN):
            role_key = "admin"
        elif viewer.has_role(Role.FINANCE):
            role_key = "finance"
        elif viewer.has_role(Role.SALES_MANAGER):
            role_key = "manager"
        elif viewer.has_role(Role.SALES_REP):
            role_key = "rep"

    async def load() -> dict[str, Any]:
        from app.models.analytics import AlertStatus, DealHealthAlert
        from app.models.billing import CreditNote, CreditNoteStatus, Invoice, InvoiceStatus
        from app.models.fulfillment import Fulfillment, FulfillmentStatus
        from app.services import approval_service, audit_service

        # --- shared, all scoped the same way as the lists they link to ---- #
        open_quotes = (
            await db.execute(
                _owned_by(
                    select(func.count()).select_from(Quotation).where(
                        Quotation.status.in_(OPEN_STATES)
                    ),
                    viewer,
                )
            )
        ).scalar_one()
        pipeline_value = (
            await db.execute(
                _owned_by(
                    select(func.coalesce(func.sum(Quotation.total), 0)).where(
                        Quotation.status.in_(PIPELINE_STATES)
                    ),
                    viewer,
                )
            )
        ).scalar_one()
        awaiting = (
            await db.execute(
                _owned_by(
                    select(func.count())
                    .select_from(Approval)
                    .join(Quotation, Approval.quotation_id == Quotation.id)
                    .where(Approval.status == ApprovalStatus.PENDING),
                    viewer,
                )
            )
        ).scalar_one()
        returned = (
            await db.execute(
                _owned_by(
                    select(func.count())
                    .select_from(Approval)
                    .join(Quotation, Approval.quotation_id == Quotation.id)
                    .where(Approval.status == ApprovalStatus.RETURNED),
                    viewer,
                )
            )
        ).scalar_one()
        # DISTINCT quotations, not alerts: one deal with a stall and a slippage
        # is one deal at risk, and the tile says "deals".
        at_risk = (
            await db.execute(
                _owned_by(
                    select(func.count(func.distinct(DealHealthAlert.quotation_id)))
                    .select_from(DealHealthAlert)
                    .join(Quotation, DealHealthAlert.quotation_id == Quotation.id)
                    .where(DealHealthAlert.status != AlertStatus.RESOLVED),
                    viewer,
                )
            )
        ).scalar_one()

        # --- whose turn it is, using the inbox's own predicate ------------- #
        waiting_on_me = 0
        if viewer is not None:
            pending_rounds = (
                await db.execute(
                    select(Approval).where(Approval.status == ApprovalStatus.PENDING)
                )
            ).scalars().all()
            waiting_on_me = sum(
                1 for approval in pending_rounds
                if approval_service.can_act(approval, viewer)
            )

        # --- finance ------------------------------------------------------- #
        splits_to_accept = (
            await db.execute(
                select(func.count())
                .select_from(Fulfillment)
                .where(
                    Fulfillment.accepted_at.is_(None),
                    Fulfillment.status.notin_(
                        [FulfillmentStatus.FULFILLED, FulfillmentStatus.CANCELLED]
                    ),
                )
            )
        ).scalar_one()
        unpaid_invoices = (
            await db.execute(
                select(func.count())
                .select_from(Invoice)
                .where(
                    Invoice.status.in_(
                        [InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]
                    )
                )
            )
        ).scalar_one()
        outstanding = (
            await db.execute(
                select(
                    func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)
                ).where(
                    Invoice.status.in_(
                        [InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]
                    )
                )
            )
        ).scalar_one()
        credits_to_apply = (
            await db.execute(
                select(func.count())
                .select_from(CreditNote)
                .where(CreditNote.status == CreditNoteStatus.ISSUED)
            )
        ).scalar_one()

        activity = await audit_service.recent(db, limit=8)
        return {
            "role": role_key,
            "open_quotations": int(open_quotes),
            "pipeline_value": float(pipeline_value),
            "awaiting_approval": int(awaiting),
            "returned_to_me": int(returned),
            "waiting_on_me": int(waiting_on_me),
            "at_risk_deals": int(at_risk),
            "splits_to_accept": int(splits_to_accept),
            "unpaid_invoices": int(unpaid_invoices),
            "outstanding_amount": float(outstanding),
            "credits_to_apply": int(credits_to_apply),
            # Kept for the admin tile, and equal to awaiting_approval for
            # anyone whose scope is the whole company.
            "pending_approvals": int(awaiting),
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

    viewer_key = str(viewer.id) if viewer is not None else "anonymous"
    return await cached_json(
        cache.NS_DASHBOARD, f"home:{role_key}:{viewer_key}", cache.TTL_DASHBOARD, load
    )
