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
    VariantPrice,
)
from app.models.inventory import StockItem
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
    """Write SKUs, per-warehouse stock and tier prices for the whole matrix.

    One transaction: a half-saved matrix would price some tiers and not others,
    and the quotation builder would then quote whichever half landed.
    """
    currencies = {c.code: c for c in await pricing_service.list_currencies(db)}
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

    for row in rows:
        variant = variants.get(row.id)
        if variant is None:
            raise ValueError("Variant does not belong to this product")
        variant.sku = row.sku.strip().upper()
        variant.unit_cost = row.unit_cost
        variant.is_active = row.is_active
        db.add(variant)

        for stock in row.stock:
            await _upsert_stock(db, variant.id, stock.warehouse_id, stock.quantity_on_hand)

        # One entered cell per tier fans out to every currency.
        for price in row.prices:
            source = currencies.get(price.currency_code.upper())
            if source is None:
                raise ValueError(f"Unknown currency {price.currency_code}")
            derived = pricing_service.derive_row(
                price.unit_price, source, currencies.values()
            )
            for code, amount in derived.items():
                await _upsert_price(
                    db,
                    variant_id=variant.id,
                    tier_id=price.tier_id,
                    currency_code=code,
                    unit_price=amount,
                    is_entered=(code == source.code),
                )

    await db.commit()


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


async def _upsert_price(
    db: AsyncSession,
    *,
    variant_id: uuid.UUID,
    tier_id: uuid.UUID,
    currency_code: str,
    unit_price: float,
    is_entered: bool,
) -> None:
    row = (
        await db.execute(
            select(VariantPrice).where(
                VariantPrice.variant_id == variant_id,
                VariantPrice.tier_id == tier_id,
                VariantPrice.currency_code == currency_code,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(
            VariantPrice(
                variant_id=variant_id,
                tier_id=tier_id,
                currency_code=currency_code,
                unit_price=unit_price,
                is_entered=is_entered,
            )
        )
        return
    row.unit_price = unit_price
    row.is_entered = is_entered
    db.add(row)


async def count_skus(db: AsyncSession) -> int:
    return int(
        (await db.execute(select(func.count()).select_from(ProductVariant))).scalar_one()
    )
