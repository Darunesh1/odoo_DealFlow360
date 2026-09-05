from datetime import datetime
import enum
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval import ApprovalStatus, ApprovalStepStatus, ApprovalTrigger
from app.models.quotation import RiskBand
from app.schemas.common import Page
from app.models.user import Role


class ApprovalStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    approval_id: uuid.UUID
    step_order: int
    role: Role
    status: ApprovalStepStatus
    assignee_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = None
    decided_by_id: Optional[uuid.UUID] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    note: Optional[str] = None


class ApprovalLineSnapshotRead(BaseModel):
    """One row of the approval screen's "Why This Quote Was Flagged" table.

    Read from the frozen snapshot, never from the live line - a rep who fixes
    the offending line and resubmits must not make a returned round render as
    if nothing was ever wrong with it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: Optional[uuid.UUID] = None
    position: int
    line_label: str
    discount_percent: float
    allowed_discount_percent: float
    over_by_points: float
    line_net: float


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_id: uuid.UUID
    round_number: int
    rule_id: Optional[uuid.UUID] = None
    rule_name: str
    blended_risk_score: float
    risk_band: RiskBand
    quotation_total: float
    discount_total: float
    status: ApprovalStatus
    trigger: ApprovalTrigger
    submitted_by_id: Optional[uuid.UUID] = None
    submitted_by_name: str
    submitted_at: datetime
    decided_at: Optional[datetime] = None
    steps: List[ApprovalStepRead] = Field(default_factory=list)
    line_snapshots: List[ApprovalLineSnapshotRead] = Field(default_factory=list)


class ApprovalRuleStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_order: int
    role: Role


class ApprovalRuleRead(BaseModel):
    """One row of screen 18's routing panel.

    Zero steps is "no approval needed" - not a special case, just an empty chain.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    min_score: float
    max_score: Optional[float] = None
    risk_band: RiskBand
    sort_order: int
    is_active: bool
    steps: List[ApprovalRuleStepRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# The approvals inbox and its decisions (screens 5 and 6)
# --------------------------------------------------------------------------- #


class ApprovalDecision(str, enum.Enum):
    APPROVE = "approve"
    RETURN = "return"
    REJECT = "reject"


class ApprovalDecisionInput(BaseModel):
    """A reviewer's verdict.

    The note is optional here and required by the service for a return or a
    reject - the rule is "give a reason when you send it back", not "always
    type something", and expressing that in the schema would need two schemas.
    """

    decision: ApprovalDecision
    note: Optional[str] = Field(default=None, max_length=2000)


class ApprovalListRow(BaseModel):
    """One row of the approvals list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quotation_id: uuid.UUID
    quotation_number: str
    customer_name: str
    customer_tier: Optional[str] = None
    round_number: int
    rule_name: str
    blended_risk_score: float
    risk_band: RiskBand
    quotation_total: float
    currency: str
    status: ApprovalStatus
    # Whose turn it is. None once the round is decided, which is what renders
    # as "Auto-Approved" or "-" in the mockup's Stage column.
    current_role: Optional[Role] = None
    assigned_to: Optional[str] = None
    submitted_by_name: str
    submitted_at: datetime
    decided_at: Optional[datetime] = None
    # Whether the caller may act on it, so the list can show the action buttons
    # without every row guessing at the role rules.
    can_act: bool = False


class ApprovalCounts(BaseModel):
    """The three tiles above the approvals list."""

    pending: int = 0
    returned: int = 0
    approved: int = 0
    rejected: int = 0


class ApprovalListPage(Page[ApprovalListRow]):
    counts: ApprovalCounts


class AuditEntryRead(BaseModel):
    """One line of the audit trail on the approval detail screen."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    actor_name: str
    reason: Optional[str] = None
    context: Optional[dict] = None
    created_at: datetime


class ApprovalDetailRead(ApprovalRead):
    """Everything screen 6 renders, in one response."""

    quotation_number: str
    customer_name: str
    customer_tier: Optional[str] = None
    currency: str
    current_role: Optional[Role] = None
    can_act: bool = False
    audit_trail: List[AuditEntryRead] = Field(default_factory=list)
