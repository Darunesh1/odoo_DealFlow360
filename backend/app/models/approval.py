"""The configurable approval chain, and the rounds a quotation goes through."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, PERCENT, POINTS, TimestampMixin
from app.models.quotation import RiskBand
from app.models.user import Role

if TYPE_CHECKING:
    from app.models.quotation import Quotation

# The Role enum already owns a Postgres type created for user_roles. Build ONE
# instance and reuse this same object on every column below - two separately
# constructed SAEnum instances sharing a name risk a duplicate CREATE TYPE
# under create_all.
ROLE_ENUM = SAEnum(
    Role, name="user_role", values_callable=lambda e: [m.value for m in e]
)


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    # Auto-approval writes a real row with zero steps rather than skipping the
    # table: the mockup's approvals list shows a "Stage: Auto-Approved" row,
    # which could not exist otherwise, and it keeps "why did this not need
    # approval?" answerable months later.
    AUTO_APPROVED = "auto_approved"
    RETURNED = "returned"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalStepStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    RETURNED = "returned"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ApprovalTrigger(str, enum.Enum):
    """What opened this round."""

    REP_SUBMIT = "rep_submit"
    REP_RESUBMIT = "rep_resubmit"
    CUSTOMER_COUNTER = "customer_counter"


class ApprovalRule(Base, TimestampMixin):
    """One row of the admin's approval-chain screen.

    Scores are matched in sort_order and the first match wins. "No approval
    needed" is simply a rule with zero steps - no special-case boolean, no NULL
    stage, no branch in the router.
    """

    __tablename__ = "approval_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    min_score: Mapped[float] = mapped_column(POINTS, default=0, nullable=False)
    # NULL means unbounded.
    max_score: Mapped[Optional[float]] = mapped_column(POINTS, nullable=True)
    risk_band: Mapped[RiskBand] = mapped_column(
        SAEnum(
            RiskBand, name="risk_band", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    steps: Mapped[list["ApprovalRuleStep"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApprovalRuleStep.step_order",
    )

    __table_args__ = (
        CheckConstraint(
            "max_score IS NULL OR max_score > min_score",
            name="ck_approval_rule_score_range",
        ),
    )


class ApprovalRuleStep(Base, TimestampMixin):
    """One stage of a chain. "Sales manager then finance" is two rows."""

    __tablename__ = "approval_rule_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_rules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[Role] = mapped_column(ROLE_ENUM, nullable=False)
    # Optional fixed approver; otherwise assignment is by role at runtime.
    assignee_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    rule: Mapped["ApprovalRule"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("rule_id", "step_order", name="uq_approval_rule_step_order"),
    )


class Approval(Base, TimestampMixin):
    """One submission round for a quotation.

    round_number is why negotiation works: a customer counter-offer opens
    round 2 rather than mutating round 1, so each round keeps its own score,
    chain and decisions, and the audit trail spans all of them.
    """

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # The score AS AT this round. The live figure on the quotation moves as the
    # rep revises; a round's routing decision must stay explainable forever.
    blended_risk_score: Mapped[float] = mapped_column(POINTS, default=0, nullable=False)
    risk_band: Mapped[RiskBand] = mapped_column(
        SAEnum(
            RiskBand, name="risk_band", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    quotation_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    discount_total: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)

    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(
            ApprovalStatus,
            name="approval_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ApprovalStatus.PENDING,
        index=True,
        nullable=False,
    )
    trigger: Mapped[ApprovalTrigger] = mapped_column(
        SAEnum(
            ApprovalTrigger,
            name="approval_trigger",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ApprovalTrigger.REP_SUBMIT,
        nullable=False,
    )
    submitted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    quotation: Mapped["Quotation"] = relationship(back_populates="approvals")
    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="approval",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApprovalStep.step_order",
    )
    line_snapshots: Mapped[list["ApprovalLineSnapshot"]] = relationship(
        back_populates="approval",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApprovalLineSnapshot.position",
    )

    __table_args__ = (
        UniqueConstraint("quotation_id", "round_number", name="uq_approval_round"),
    )


class ApprovalStep(Base, TimestampMixin):
    """A stage of the chain, COPIED from the rule at submit time rather than
    pointing at it - an in-flight approval keeps the chain it was routed onto
    even if an admin edits the rule five minutes later."""

    __tablename__ = "approval_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[Role] = mapped_column(ROLE_ENUM, nullable=False)
    status: Mapped[ApprovalStepStatus] = mapped_column(
        SAEnum(
            ApprovalStepStatus,
            name="approval_step_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ApprovalStepStatus.PENDING,
        nullable=False,
    )
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignee_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    approval: Mapped["Approval"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("approval_id", "step_order", name="uq_approval_step_order"),
    )


class ApprovalLineSnapshot(Base, TimestampMixin):
    """The "Why This Quote Was Flagged" table, frozen per round.

    Reading live lines here breaks the most important demo flow: a rep who is
    returned for revision, drops the offending line to 9% and resubmits would
    leave round 1 rendering "9% / 10% / OK" - a rejected round showing no
    reason for its rejection. line_id is SET-NULL-able because a revision may
    delete the offending line outright.
    """

    __tablename__ = "approval_line_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotation_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_label: Mapped[str] = mapped_column(String(255), nullable=False)
    discount_percent: Mapped[float] = mapped_column(PERCENT, nullable=False)
    allowed_discount_percent: Mapped[float] = mapped_column(PERCENT, nullable=False)
    over_by_points: Mapped[float] = mapped_column(POINTS, nullable=False)
    line_net: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    approval: Mapped["Approval"] = relationship(back_populates="line_snapshots")
