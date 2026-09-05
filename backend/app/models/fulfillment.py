"""Warehouse splitting, backorders and shipments."""

from datetime import date, datetime
import enum
from typing import Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, TimestampMixin


class FulfillmentStatus(str, enum.Enum):
    SPLIT_PENDING = "split_pending"
    RESERVED = "reserved"
    BACKORDER = "backorder"
    PARTIALLY_SHIPPED = "partially_shipped"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class AllocationStatus(str, enum.Enum):
    PLANNED = "planned"
    RESERVED = "reserved"
    BACKORDERED = "backordered"
    PARTIALLY_SHIPPED = "partially_shipped"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class ShipmentStatus(str, enum.Enum):
    PLANNED = "planned"
    PICKING = "picking"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class SplitStrategy(str, enum.Enum):
    SUGGESTED = "suggested"
    MANUAL_OVERRIDE = "manual_override"


class Fulfillment(Base, TimestampMixin):
    """The fulfillment side of a confirmed quotation - one per order."""

    __tablename__ = "fulfillments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    status: Mapped[FulfillmentStatus] = mapped_column(
        SAEnum(FulfillmentStatus, name="fulfillment_status",
               values_callable=lambda e: [m.value for m in e]),
        default=FulfillmentStatus.SPLIT_PENDING, index=True, nullable=False,
    )
    strategy: Mapped[SplitStrategy] = mapped_column(
        SAEnum(SplitStrategy, name="split_strategy",
               values_callable=lambda e: [m.value for m in e]),
        default=SplitStrategy.SUGGESTED, nullable=False,
    )
    estimated_shipping_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    estimated_shipment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Frozen copy of the planner's original recommendation, so Manual Override
    # can rewrite allocations destructively and Finance can still see what was
    # proposed. One nullable column instead of a plan-versions table.
    suggestion_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    requested_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    promised_ship_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    consolidated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    allocations: Mapped[list["FulfillmentAllocation"]] = relationship(
        back_populates="fulfillment", cascade="all, delete-orphan", lazy="selectin"
    )
    shipments: Mapped[list["Shipment"]] = relationship(
        back_populates="fulfillment", cascade="all, delete-orphan", lazy="selectin"
    )


class FulfillmentAllocation(Base, TimestampMixin):
    """How much of one line comes from one warehouse.

    RESERVED (stock held, counted in stock_items.quantity_reserved) and
    BACKORDERED (nothing held, waiting on a restock) are genuinely different
    states; a model that treats "allocated" as "reserved" cannot express a
    backorder at all.
    """

    __tablename__ = "fulfillment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    fulfillment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fulfillments.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    quotation_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    # Denormalised off the line so the reservation write is a single-table
    # lookup rather than a join through quotation_lines.
    #
    # The VARIANT is what stock is keyed on - stock_items has no product_id -
    # so the variant is what a reservation has to name. product_id rides along
    # for reporting rollups, where "how many laptops did we ship" should not
    # need a join through every SKU.
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_shipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[AllocationStatus] = mapped_column(
        SAEnum(AllocationStatus, name="allocation_status",
               values_callable=lambda e: [m.value for m in e]),
        default=AllocationStatus.PLANNED, nullable=False,
    )
    estimated_shipping_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    expected_restock_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Set by Manual Override, so human splits can be audited against planner ones.
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    fulfillment: Mapped["Fulfillment"] = relationship(back_populates="allocations")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_allocation_quantity_positive"),
        CheckConstraint(
            "quantity_shipped >= 0 AND quantity_shipped <= quantity",
            name="ck_allocation_shipped_within_quantity",
        ),
        # Makes the "Consolidate Remaining Backorder" sweep cheap.
        Index(
            "ix_allocation_backorder_sweep", "warehouse_id", "variant_id",
            postgresql_where=text("status = 'backordered'"),
        ),
    )


class Shipment(Base, TimestampMixin):
    """One physical dispatch from one warehouse.

    "Est. Shipments" on the split screen is COUNT(*) of these, not a stored
    integer: the planner materialises PLANNED rows at suggestion time, so the
    estimate and the reality are the same rows in two states. That is what
    makes consolidation a status change rather than a recalculation.
    """

    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    fulfillment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fulfillments.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(ShipmentStatus, name="shipment_status",
               values_callable=lambda e: [m.value for m in e]),
        default=ShipmentStatus.PLANNED, nullable=False,
    )
    estimated_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    actual_cost: Mapped[Optional[float]] = mapped_column(MONEY, nullable=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tracking_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # The gate on invoicing: nothing is billable until this is set.
    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when "Consolidate Remaining Backorder" merges this into another
    # dispatch. Keeps the original cost estimate so the saving is showable.
    consolidated_into_shipment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True
    )

    fulfillment: Mapped["Fulfillment"] = relationship(back_populates="shipments")
    lines: Mapped[list["ShipmentLine"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan", lazy="selectin"
    )


class ShipmentLine(Base, TimestampMixin):
    """The reconciliation ledger: the only thing that can say how many units of
    a line physically left the building.

    Invoicing reads quantity_shipped here, never quotation_line.quantity. That
    is what makes partial delivery drive partial invoicing.
    """

    __tablename__ = "shipment_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    # RESTRICT: once something has shipped against an allocation, a Manual
    # Override must not delete that allocation out from under the history.
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fulfillment_allocations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quotation_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_shipped: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_invoiced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    shipment: Mapped["Shipment"] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity_shipped > 0", name="ck_shipment_line_quantity_positive"),
        # "Nothing is billed before it ships", as a database invariant rather
        # than a service-layer convention.
        CheckConstraint(
            "quantity_invoiced >= 0 AND quantity_invoiced <= quantity_shipped",
            name="ck_shipment_line_invoiced_within_shipped",
        ),
        Index(
            "ix_shipment_line_uninvoiced", "quotation_line_id",
            postgresql_where=text("quantity_invoiced < quantity_shipped"),
        ),
    )
