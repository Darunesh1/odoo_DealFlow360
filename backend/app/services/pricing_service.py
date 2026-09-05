"""Currency conversion and tier-price resolution.

The one place FX arithmetic lives. Everything here works in Decimal and
quantizes only on write; converting through float would drift a 4-decimal unit
price by the third product.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Currency, ProductVariant, VariantPrice

UNIT = Decimal("0.0001")


def _dec(value) -> Decimal:
    return Decimal(str(value))


def quantize_unit(value: Decimal) -> float:
    return float(value.quantize(UNIT, rounding=ROUND_HALF_UP))


async def list_currencies(db: AsyncSession, *, active_only: bool = False) -> Sequence[Currency]:
    stmt = select(Currency).order_by(Currency.is_base.desc(), Currency.code)
    if active_only:
        stmt = stmt.where(Currency.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_currency(db: AsyncSession, code: str) -> Optional[Currency]:
    return (
        await db.execute(select(Currency).where(Currency.code == code.upper()))
    ).scalar_one_or_none()


async def get_base_currency(db: AsyncSession) -> Optional[Currency]:
    return (
        await db.execute(select(Currency).where(Currency.is_base.is_(True)))
    ).scalar_one_or_none()


def convert(amount, source: Currency, target: Currency) -> Decimal:
    """Convert between two currencies through the base rate.

    rate_to_base is "one unit of this currency in base currency", so the base
    row is 1.0 and the round trip is exact for the base itself.
    """
    if source.code == target.code:
        return _dec(amount)
    in_base = _dec(amount) * _dec(source.rate_to_base)
    return in_base / _dec(target.rate_to_base)


async def rebuild_variant_prices(db: AsyncSession, *, variant_ids=None) -> int:
    """Recompute every (variant, tier, currency) price from base_price.

        unit_price = convert(base_price, base -> currency)
                     x (1 - tier.max_discount_percent / 100)

    The ONLY place a variant_prices row is written. Nothing in that table is
    typed, so anything that feeds the formula - a variant's price, a tier's
    ceiling, a currency's rate, a tier or currency appearing or disappearing -
    means calling this rather than patching rows in place.
    """
    from app.models.customer import CustomerTier

    currencies = list(await list_currencies(db))
    base = next((c for c in currencies if c.is_base), None)
    if base is None or not currencies:
        return 0
    tiers = list(
        (await db.execute(select(CustomerTier))).scalars().all()
    )
    if not tiers:
        return 0

    stmt = select(ProductVariant)
    if variant_ids is not None:
        ids = list(variant_ids)
        if not ids:
            return 0
        stmt = stmt.where(ProductVariant.id.in_(ids))
    variants = list((await db.execute(stmt)).scalars().all())
    if not variants:
        return 0

    existing = {
        (row.variant_id, row.tier_id, row.currency_code): row
        for row in (
            await db.execute(
                select(VariantPrice).where(
                    VariantPrice.variant_id.in_([v.id for v in variants])
                )
            )
        )
        .scalars()
        .all()
    }

    written = 0
    for variant in variants:
        for tier in tiers:
            keep = _dec(1) - _dec(tier.max_discount_percent) / _dec(100)
            for currency in currencies:
                amount = quantize_unit(
                    convert(variant.base_price, base, currency) * keep
                )
                row = existing.get((variant.id, tier.id, currency.code))
                if row is None:
                    db.add(
                        VariantPrice(
                            variant_id=variant.id,
                            tier_id=tier.id,
                            currency_code=currency.code,
                            unit_price=amount,
                        )
                    )
                else:
                    row.unit_price = amount
                    db.add(row)
                written += 1

    # Tiers and currencies can also disappear; drop rows that no longer point at
    # a live one, or the matrix would keep showing a deleted tier's column.
    live_tiers = {tier.id for tier in tiers}
    live_currencies = {currency.code for currency in currencies}
    for (variant_id, tier_id, code), row in existing.items():
        if tier_id not in live_tiers or code not in live_currencies:
            await db.delete(row)

    await db.commit()
    return written


async def resolve_variant_price(
    db: AsyncSession,
    *,
    variant_id: uuid.UUID,
    tier_id: uuid.UUID,
    currency_code: str,
) -> Optional[Decimal]:
    """The price a customer on this tier pays for this variant, in this currency.

    A plain indexed lookup: prices are stored per currency rather than converted
    on read, so a later rate change cannot move a price already quoted.
    """
    row = (
        await db.execute(
            select(VariantPrice.unit_price).where(
                VariantPrice.variant_id == variant_id,
                VariantPrice.tier_id == tier_id,
                VariantPrice.currency_code == currency_code.upper(),
            )
        )
    ).scalar_one_or_none()
    return None if row is None else _dec(row)


async def variant_price_range(
    db: AsyncSession, variant_ids: Sequence[uuid.UUID], currency_code: str
) -> tuple[Optional[float], Optional[float]]:
    """Min and max price across a set of variants, for screen 16's price range."""
    if not variant_ids:
        return None, None
    rows = list(
        (
            await db.execute(
                select(VariantPrice.unit_price).where(
                    VariantPrice.variant_id.in_(variant_ids),
                    VariantPrice.currency_code == currency_code.upper(),
                    VariantPrice.unit_price > 0,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None, None
    values = [float(value) for value in rows]
    return min(values), max(values)
