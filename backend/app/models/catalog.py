"""Products, their generated variants, tier pricing and upsell pairings."""

import enum
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import MONEY, PERCENT, RATIO, UNIT_PRICE, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import CustomerTier


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


class ProductStatus(str, enum.Enum):
    """Active is currently sellable. Archived is kept for history but cannot be
    put on a new quotation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class PairingSource(str, enum.Enum):
    """Where an upsell suggestion came from."""

    CO_PURCHASE = "co_purchase"
    MANUAL = "manual"


class Currency(Base, TimestampMixin):
    """A currency the catalog can be priced in.

    rate_to_base converts one unit of this currency into the base currency, so
    the base row is 1.0. Exactly one row may be the base.
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    rate_to_base: Mapped[float] = mapped_column(Numeric(16, 6), default=1, nullable=False)
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("rate_to_base > 0", name="ck_currency_rate_positive"),
        CheckConstraint(
            "NOT is_base OR rate_to_base = 1", name="ck_currency_base_rate_is_one"
        ),
        # One base currency, enforced in the database rather than by convention.
        Index(
            "uq_currency_single_base", "is_base",
            unique=True, postgresql_where=text("is_base"),
        ),
    )


class CategoryDiscountLimit(Base, TimestampMixin):
    """Screen 18's category ceiling panel, keyed by the free-text category name.

    A category absent from this table has NO ceiling, which is not the same as a
    ceiling of zero: defaulting to zero would flag every uncapped line the
    instant anyone discounted it.
    """

    __tablename__ = "category_discount_limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    category: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    max_discount_percent: Mapped[float] = mapped_column(PERCENT, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "max_discount_percent >= 0 AND max_discount_percent <= 100",
            name="ck_category_limit_percent_range",
        ),
    )


class Product(Base, TimestampMixin):
    """A sellable item.

    Carries neither a price nor a stock column: price is per (variant, tier,
    currency) and stock is per (variant, warehouse). Category is free text -
    the admin types it and the form suggests names already in use.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    has_variants: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Drives the "Promo: 12% off" tag on upsell suggestions.
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promotion_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status",
               values_callable=lambda e: [m.value for m in e]),
        default=ProductStatus.ACTIVE, nullable=False,
    )

    attributes: Mapped[list["ProductVariantAttribute"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProductVariantAttribute.position",
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProductVariant.name",
    )

    __table_args__ = (
        # The mockup's "if subscription yes then recurring will be visible",
        # enforced in the database rather than left to the form.
        CheckConstraint(
            "(recurring_interval IS NOT NULL) = is_subscription",
            name="ck_product_recurring_matches_subscription",
        ),
        CheckConstraint(
            "tax_percent >= 0 AND tax_percent <= 100", name="ck_product_tax_range"
        ),
        Index("ix_products_category_status", "category", "status"),
    )


class ProductVariantAttribute(Base, TimestampMixin):
    """One axis of the variant matrix: "Color", "RAM"."""

    __tablename__ = "product_variant_attributes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="attributes")
    values: Mapped[list["ProductVariantAttributeValue"]] = relationship(
        back_populates="attribute", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProductVariantAttributeValue.position",
    )

    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_variant_attribute_name"),
    )


class ProductVariantAttributeValue(Base, TimestampMixin):
    """One value on an axis: "Black", "8GB"."""

    __tablename__ = "product_variant_attribute_values"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variant_attributes.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    attribute: Mapped["ProductVariantAttribute"] = relationship(back_populates="values")

    __table_args__ = (
        UniqueConstraint("attribute_id", "value", name="uq_variant_attribute_value"),
    )


class ProductVariant(Base, TimestampMixin):
    """One sellable combination, and the only thing that carries a SKU.

    Every product owns at least one: a product without variants gets a single
    hidden "Default" row, so pricing, stock and quotation lines all key on a
    variant and there is never a second code path.

    The combination lives in `options` rather than a join table. That is what
    makes Generate Variants idempotent: regenerating after the admin adds a
    value matches existing rows on their options payload and inserts only the
    genuinely new combinations, so SKUs, quantities and prices already typed
    into the matrix survive.
    """

    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # The two numbers an admin actually types, both in the base currency.
    # Every tier and currency price is derived from base_price; unit_cost is
    # what makes margin computable.
    unit_cost: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    base_price: Mapped[float] = mapped_column(UNIT_PRICE, default=0, nullable=False)
    # How many of this plan may be sold in total. Subscriptions only: a plan
    # has no warehouse to sit in, so its limit is a capacity rather than stock,
    # and stock_items would be fiction. NULL on a physical variant, where the
    # per-warehouse rows are the real answer.
    available_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")
    prices: Mapped[list["VariantPrice"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_product_variant_name"),
        CheckConstraint(
            "unit_cost >= 0 AND base_price >= 0", name="ck_variant_amounts_non_negative"
        ),
        CheckConstraint(
            "available_quantity IS NULL OR available_quantity >= 0",
            name="ck_variant_capacity_non_negative",
        ),
    )


class VariantPrice(Base, TimestampMixin):
    """The price of one variant, for one customer tier, in one currency.

    Entirely derived: base_price converted into the currency, less that tier's
    discount. Nothing here is typed. It is still stored rather than computed on
    read because that keeps price resolution a single indexed lookup, and means
    a later rate change cannot silently move a price already quoted -
    repricing is an explicit rebuild.
    """

    __tablename__ = "variant_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_tiers.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    unit_price: Mapped[float] = mapped_column(UNIT_PRICE, default=0, nullable=False)

    variant: Mapped["ProductVariant"] = relationship(back_populates="prices")

    __table_args__ = (
        UniqueConstraint(
            "variant_id", "tier_id", "currency_code", name="uq_variant_price"
        ),
        CheckConstraint("unit_price >= 0", name="ck_variant_price_non_negative"),
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
