"""Products, variants, price lists and upsell pairings."""

import enum
from typing import Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Enum as SAEnum, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, PERCENT, RATIO, TimestampMixin


class RecurringInterval(str, enum.Enum):
    """How often a subscription product bills."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ProductUnit(str, enum.Enum):
    """The unit a product is sold in."""

    EACH = "each"
    HOUR = "hour"
    DAY = "day"
    LICENSE = "license"
    RECURRING = "recurring"


class PairingSource(str, enum.Enum):
    """Where an upsell suggestion came from."""

    CO_PURCHASE = "co_purchase"
    MANUAL = "manual"


class ProductCategory(Base, TimestampMixin):
    """Hardware / Services / Subscriptions, each with its own discount ceiling."""

    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL means "no category ceiling", which is NOT the same as zero. The
    # mockup gives Hardware 15 and Services 10 and says nothing about
    # Subscriptions; defaulting that to 0.00 would flag every subscription line
    # the instant anyone discounted it.
    max_discount_percent: Mapped[Optional[float]] = mapped_column(PERCENT, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "max_discount_percent IS NULL OR "
            "(max_discount_percent >= 0 AND max_discount_percent <= 100)",
            name="ck_product_category_percent_range",
        ),
    )


class Product(Base, TimestampMixin):
    """A sellable item. Carries no stock column: stock is per warehouse, and a
    product-level total would drift from the warehouse rows within one demo."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_categories.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_price: Mapped[float] = mapped_column(MONEY, nullable=False)
    # Not in the original field list. Margin is revenue minus cost, and the UI
    # shows a live margin indicator plus "Margin +$18" on upsell chips, so
    # without a cost those features are not inaccurate - they are uncomputable.
    unit_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    unit: Mapped[ProductUnit] = mapped_column(
        SAEnum(ProductUnit, name="product_unit",
               values_callable=lambda e: [m.value for m in e]),
        default=ProductUnit.EACH, nullable=False,
    )
    tax_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurring_interval: Mapped[Optional[RecurringInterval]] = mapped_column(
        SAEnum(RecurringInterval, name="recurring_interval",
               values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    # Drives the "Promo: 12% off" tag on upsell suggestions.
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promotion_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["ProductCategory"] = relationship(lazy="selectin")
    variant_options: Mapped[list["ProductVariantOption"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # The mockup's "if subscription yes then recurring will be visible",
        # enforced in the database rather than left to the form.
        CheckConstraint(
            "(recurring_interval IS NOT NULL) = is_subscription",
            name="ck_product_recurring_matches_subscription",
        ),
        CheckConstraint("list_price >= 0 AND unit_cost >= 0", name="ck_product_amounts_non_negative"),
        CheckConstraint(
            "tax_percent >= 0 AND tax_percent <= 100", name="ck_product_tax_range"
        ),
        Index("ix_products_category_active", "category_id", "is_active"),
    )


class ProductVariantOption(Base, TimestampMixin):
    """One (attribute, value) pair with its price delta.

    Grouping by attribute renders the mockup's row exactly:
    "Color | Blue, Black | +$10/+$30". The "340 SKUs" stat on the catalog
    screen is a count of these option rows - it is not a combination matrix,
    which this table deliberately cannot describe.
    """

    __tablename__ = "product_variant_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    attribute: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    price_delta: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variant_options")

    __table_args__ = (
        UniqueConstraint("product_id", "attribute", "value", name="uq_variant_option"),
    )


class PriceList(Base, TimestampMixin):
    """Tier- and currency-scoped pricing.

    adjustment_percent expresses the mockup's "Price Rule" column: 0 is
    "Price, no adjustment" and 10 is "Price minus 10 percent base".
    """

    __tablename__ = "price_lists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL tier = the global fallback list.
    tier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_tiers.id", ondelete="RESTRICT"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    adjustment_percent: Mapped[float] = mapped_column(PERCENT, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list["PriceListItem"]] = relationship(
        back_populates="price_list", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "adjustment_percent >= -100 AND adjustment_percent <= 100",
            name="ck_price_list_adjustment_range",
        ),
        # Two active lists for the same tier and currency make price resolution
        # non-deterministic, and you would only find out when a demo quote
        # priced differently on a refresh.
        Index(
            "uq_price_list_active_tier_currency", "tier_id", "currency",
            unique=True, postgresql_where=text("is_active"),
        ),
    )


class PriceListItem(Base, TimestampMixin):
    """An absolute per-product override. Replaces the list rule; does not stack."""

    __tablename__ = "price_list_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    price_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("price_lists.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    unit_price: Mapped[float] = mapped_column(MONEY, nullable=False)

    price_list: Mapped["PriceList"] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("price_list_id", "product_id", name="uq_price_list_item"),
        CheckConstraint("unit_price >= 0", name="ck_price_list_item_non_negative"),
    )


class ProductPairing(Base, TimestampMixin):
    """Backs the upsell / cross-sell panel. Ranking logic is a later phase."""

    __tablename__ = "product_pairings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    suggested_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[float] = mapped_column(RATIO, default=1, nullable=False)
    source: Mapped[PairingSource] = mapped_column(
        SAEnum(PairingSource, name="pairing_source",
               values_callable=lambda e: [m.value for m in e]),
        default=PairingSource.MANUAL, nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("product_id", "suggested_product_id", name="uq_product_pairing"),
        CheckConstraint("product_id <> suggested_product_id", name="ck_pairing_not_self"),
    )
