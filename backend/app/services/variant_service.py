"""Generating the variant matrix and saving it back in one transaction."""

from __future__ import annotations

from itertools import product as cartesian
import re
from typing import Iterable, Optional, Sequence
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import (
    Product,
    ProductVariant,
    ProductVariantAttribute,
    ProductVariantAttributeValue,
)
from app.models.inventory import StockItem, Warehouse
from app.schemas.catalog import VariantAttributeInput, VariantRowInput
from app.services import pricing_service

DEFAULT_VARIANT_NAME = "Default"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return cleaned or "ITEM"


def _variant_name(options: dict[str, str]) -> str:
    return " / ".join(options.values()) if options else DEFAULT_VARIANT_NAME


async def _unique_sku(db: AsyncSession, base: str, taken: set[str]) -> str:
    """Append -2, -3 ... until the SKU is free, checking taken rows too.

    `taken` carries SKUs minted earlier in this same flush, which the database
    cannot see yet.
    """
    candidate = base[:64]
    suffix = 1
    while True:
        if candidate not in taken:
            exists = (
                await db.execute(
                    select(ProductVariant.id).where(ProductVariant.sku == candidate)
                )
            ).scalar_one_or_none()
            if exists is None:
                taken.add(candidate)
                return candidate
        suffix += 1
        tail = f"-{suffix}"
        candidate = f"{base[: 64 - len(tail)]}{tail}"


async def sku_for(
    db: AsyncSession, product: Product, options: dict[str, str], taken: set[str]
) -> str:
    parts = [_slug(product.name)]
    parts.extend(_slug(value) for value in options.values())
    if not options:
        parts.append("STD")
    return await _unique_sku(db, "-".join(parts), taken)


async def replace_attributes(
    db: AsyncSession, product: Product, attributes: Sequence[VariantAttributeInput]
) -> None:
    """Rewrite the axes of the matrix. Existing variants are left alone -
    regenerating is a separate, explicit click."""
    await db.execute(
        delete(ProductVariantAttribute).where(
            ProductVariantAttribute.product_id == product.id
        )
    )
    for position, attribute in enumerate(attributes):
        row = ProductVariantAttribute(
            product_id=product.id, name=attribute.name.strip(), position=position
        )
        db.add(row)
        await db.flush()
        seen: set[str] = set()
        for value_position, value in enumerate(attribute.values):
            cleaned = value.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            db.add(
                ProductVariantAttributeValue(
                    attribute_id=row.id, value=cleaned, position=value_position
                )
            )
    await db.flush()


async def ensure_default_variant(db: AsyncSession, product: Product) -> ProductVariant:
    """Every product owns at least one variant, so pricing, stock and quotation
    lines have exactly one code path."""
    existing = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.product_id == product.id,
                ProductVariant.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    variant = ProductVariant(
        product_id=product.id,
        sku=await sku_for(db, product, {}, set()),
        name=DEFAULT_VARIANT_NAME,
        options={},
        is_default=True,
    )
    db.add(variant)
    await db.flush()
    return variant


async def generate_variants(db: AsyncSession, product: Product) -> list[ProductVariant]:
    """Build every combination of the product's attribute values.

    Idempotent: existing rows are matched on their `options` payload, so
    regenerating after the admin adds a value inserts only the genuinely new
    combinations and leaves already-typed SKUs, quantities and prices intact.
    """
    attributes = list(
        (
            await db.execute(
                select(ProductVariantAttribute)
                .options(selectinload(ProductVariantAttribute.values))
                .where(ProductVariantAttribute.product_id == product.id)
                .order_by(ProductVariantAttribute.position)
            )
        )
        .scalars()
        .all()
    )
    axes = [
        (attribute.name, [value.value for value in attribute.values])
        for attribute in attributes
        if attribute.values
    ]
    if not axes:
        return [await ensure_default_variant(db, product)]

    existing = list(
        (
            await db.execute(
                select(ProductVariant).where(ProductVariant.product_id == product.id)
            )
        )
        .scalars()
        .all()
    )
    by_options = {_options_key(row.options): row for row in existing}
    taken = {row.sku for row in existing}

    # A product that gained real variants must not keep a stray Default row
    # around: it would show up in the matrix with no options and no meaning.
    for row in existing:
        if row.is_default and not row.options:
            await db.delete(row)
            by_options.pop(_options_key(row.options), None)
            taken.discard(row.sku)

    names = [name for name, _ in axes]
    for combination in cartesian(*[values for _, values in axes]):
        options = dict(zip(names, combination))
        key = _options_key(options)
        if key in by_options:
            continue
        variant = ProductVariant(
            product_id=product.id,
            sku=await sku_for(db, product, options, taken),
            name=_variant_name(options),
            options=options,
            is_default=False,
        )
        db.add(variant)
        by_options[key] = variant
    await db.flush()

    return list(
        (
            await db.execute(
                select(ProductVariant)
                .where(ProductVariant.product_id == product.id)
                .order_by(ProductVariant.name)
            )
        )
        .scalars()
        .all()
    )


def _options_key(options: Optional[dict]) -> tuple:
    return tuple(sorted((options or {}).items()))


async def save_variant_matrix(
    db: AsyncSession, product: Product, rows: Sequence[VariantRowInput]
) -> None:
    """Write SKUs, costs, base prices and per-warehouse stock for the matrix,
    then rebuild every derived price.

    One transaction, and validated up front: a half-configured SKU - no cost, no
    price, or no stock figure for a warehouse - would reach the rep's picker as
    something that cannot be quoted.
    """
    variants = {
        row.id: row
        for row in (
            await db.execute(
                select(ProductVariant).where(ProductVariant.product_id == product.id)
            )
        )
        .scalars()
        .all()
    }
    warehouses = list(
        (
            await db.execute(
                select(Warehouse).where(Warehouse.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    # A subscription has no shelf, so it is capped rather than stocked - one
    # number saying how many licences exist. Everything else is stock-tracked
    # and needs a figure per active warehouse. Neither may be skipped: a SKU
    # with no limit at all reaches the rep's picker as something sellable
    # without end.
    stocked = not product.is_subscription
    required_warehouses = {w.id for w in warehouses} if stocked else set()

    for row in rows:
        variant = variants.get(row.id)
        if variant is None:
            raise ValueError("Variant does not belong to this product")
        label = row.sku.strip() or variant.sku
        if row.unit_cost is None or row.unit_cost <= 0:
            raise ValueError(f"{label}: enter a unit cost before saving")
        if row.base_price is None or row.base_price <= 0:
            raise ValueError(f"{label}: enter a unit price before saving")

        if stocked:
            supplied = {entry.warehouse_id for entry in row.stock}
            missing = required_warehouses - supplied
            if missing:
                names = ", ".join(
                    sorted(w.name for w in warehouses if w.id in missing)
                )
                raise ValueError(f"{label}: enter a quantity for {names}")
        elif row.available_quantity is None or row.available_quantity <= 0:
            raise ValueError(
                f"{label}: enter how many licences of this plan can be sold"
            )

    for row in rows:
        variant = variants[row.id]
        variant.sku = row.sku.strip().upper()
        variant.unit_cost = row.unit_cost
        variant.base_price = row.base_price
        variant.is_active = row.is_active
        # Only meaningful on a plan; left null on a physical variant, where the
        # per-warehouse rows are the real answer.
        variant.available_quantity = None if stocked else row.available_quantity
        db.add(variant)
        for entry in row.stock:
            await _upsert_stock(
                db, variant.id, entry.warehouse_id, entry.quantity_on_hand
            )

    await db.flush()
    # Every price cell is derived, so it is rebuilt rather than written here.
    await pricing_service.rebuild_variant_prices(
        db, variant_ids=[row.id for row in rows]
    )


async def _upsert_stock(
    db: AsyncSession, variant_id: uuid.UUID, warehouse_id: uuid.UUID, quantity: int
) -> None:
    item = (
        await db.execute(
            select(StockItem).where(
                StockItem.variant_id == variant_id,
                StockItem.warehouse_id == warehouse_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        db.add(
            StockItem(
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                quantity_on_hand=quantity,
            )
        )
        return
    # Never drop on-hand below what is already reserved: the check constraint
    # would abort the whole matrix save over one typo.
    item.quantity_on_hand = max(quantity, item.quantity_reserved)
    db.add(item)


async def count_skus(db: AsyncSession) -> int:
    return int(
        (await db.execute(select(func.count()).select_from(ProductVariant))).scalar_one()
    )
