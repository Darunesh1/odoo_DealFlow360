"""Warehouses and per-warehouse stock."""

from typing import Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Computed, ForeignKey, Index, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class Warehouse(Base, TimestampMixin):
    """A stocking location: where it is, and what it holds.

    Carries no shipping cost configuration. The split planner therefore
    minimises the NUMBER of shipments and prefers the warehouse with deeper
    stock, rather than a monetary cost.
    """

    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stock: Mapped[list["StockItem"]] = relationship(
        back_populates="warehouse", cascade="all, delete-orphan", lazy="selectin"
    )


class StockItem(Base, TimestampMixin):
    """Stock for one variant at one warehouse - the Stock screen's row.

    Keyed on the variant, not the product: the admin enters a quantity per
    warehouse for every generated SKU, and the split planner allocates the SKU
    the rep actually put on the line.
    """

    __tablename__ = "stock_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # A stored generated column rather than a Python property: the stock screen
    # stays a plain SELECT, the split planner can filter and ORDER BY on it in
    # SQL, and it can never disagree with the two columns it derives from.
    quantity_available: Mapped[int] = mapped_column(
        Integer, Computed("quantity_on_hand - quantity_reserved", persisted=True),
        nullable=False,
    )
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bin_location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    warehouse: Mapped["Warehouse"] = relationship(back_populates="stock")
    variant: Mapped["ProductVariant"] = relationship(lazy="selectin")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "variant_id", name="uq_stock_item"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_stock_on_hand_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="ck_stock_reserved_non_negative"),
        # The last line of defence against two people accepting a split at once:
        # the loser's transaction aborts here rather than over-reserving.
        CheckConstraint(
            "quantity_reserved <= quantity_on_hand", name="ck_stock_reserved_within_on_hand"
        ),
        Index("ix_stock_items_available", "variant_id", "quantity_available"),
    )
