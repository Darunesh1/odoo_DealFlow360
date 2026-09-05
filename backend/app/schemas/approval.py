from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval import ApprovalStatus, ApprovalStepStatus, ApprovalTrigger
from app.models.quotation import RiskBand
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
