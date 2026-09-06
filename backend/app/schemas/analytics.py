"""Dashboard, deal health and reporting (mockup screens 2, 14 and 15)."""

from datetime import datetime
import enum
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.analytics import AlertStatus, AlertType
from app.models.quotation import RiskBand


class ActivityEntry(BaseModel):
    id: str
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    reason: Optional[str] = None
    context: Optional[dict] = None
    created_at: str


class DashboardRead(BaseModel):
    """Screen 2's tiles and its Recent Activity list.

    Every figure is scoped to whoever asked, and computed from the same query
    as the screen its tile links to - the point being that clicking a number
    lands on a list that shows that number.
    """

    # Which set of tiles to render.
    role: str = "admin"

    open_quotations: int = 0
    pipeline_value: float = 0
    awaiting_approval: int = 0
    returned_to_me: int = 0
    waiting_on_me: int = 0
    at_risk_deals: int = 0

    splits_to_accept: int = 0
    unpaid_invoices: int = 0
    outstanding_amount: float = 0
    credits_to_apply: int = 0

    pending_approvals: int = 0
    recent_activity: List[ActivityEntry] = Field(default_factory=list)


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_id: uuid.UUID
    quotation_number: str
    customer_name: str
    owner_name: Optional[str] = None
    alert_type: AlertType
    severity: RiskBand
    detail: str
    status: AlertStatus
    flagged_at: datetime
    acted_at: Optional[datetime] = None
    action_note: Optional[str] = None


class AlertCounts(BaseModel):
    stalled_deals: int = 0
    discount_anomalies: int = 0
    delivery_slippage: int = 0
    # None means the sweep has never run here, which is not the same as "no
    # alerts" - the screen says so rather than claiming everything is fine.
    last_swept_at: Optional[str] = None


class AlertAction(str, enum.Enum):
    NUDGE = "nudge"
    ESCALATE = "escalate"
    RESOLVE = "resolve"


class AlertActionInput(BaseModel):
    action: AlertAction
    note: Optional[str] = Field(default=None, max_length=255)


class NamedFigure(BaseModel):
    name: str
    units: int = 0
    revenue: float = 0


class DiscountFigure(BaseModel):
    name: str
    average_discount: float = 0
    lines: int = 0


class RepFigure(BaseModel):
    name: str
    revenue: float = 0
    margin: float = 0
    average_discount: float = 0


class CategoryFigure(BaseModel):
    name: str
    revenue: float = 0
    margin: float = 0


class ReportRead(BaseModel):
    """Screen 15, in one response."""

    quotes_created: int = 0
    quotes_confirmed: int = 0
    conversion_rate: float = 0
    orders: int = 0
    revenue: float = 0
    margin: float = 0
    average_discount: float = 0
    units_sold: int = 0
    # None while nothing has been decided yet - an average of no decisions is
    # not zero hours.
    average_approval_hours: Optional[float] = None
    top_upsold: List[NamedFigure] = Field(default_factory=list)
    best_selling: List[NamedFigure] = Field(default_factory=list)
    most_discounted: List[DiscountFigure] = Field(default_factory=list)
    by_rep: List[RepFigure] = Field(default_factory=list)
    by_category: List[CategoryFigure] = Field(default_factory=list)
