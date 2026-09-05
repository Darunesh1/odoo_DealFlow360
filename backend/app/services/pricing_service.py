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


def derive_row(
    entered_amount,
    entered_currency: Currency,
    currencies: Iterable[Currency],
) -> dict[str, float]:
    """Fill every currency for one tier from the single cell the admin typed."""
    return {
        currency.code: quantize_unit(convert(entered_amount, entered_currency, currency))
        for currency in currencies
    }


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


async def recompute_derived_prices(db: AsyncSession, currency: Currency) -> int:
    """Re-derive every non-entered price in `currency` after a rate change.

    Cells the admin typed by hand are left exactly as typed - a rate correction
    is not licence to rewrite someone's deliberate number.
    """
    currencies = {c.code: c for c in await list_currencies(db)}
    rows = list(
        (
            await db.execute(
                select(VariantPrice).where(
                    VariantPrice.currency_code == currency.code,
                    VariantPrice.is_entered.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    updated = 0
    for row in rows:
        source = (
            await db.execute(
                select(VariantPrice).where(
                    VariantPrice.variant_id == row.variant_id,
                    VariantPrice.tier_id == row.tier_id,
                    VariantPrice.is_entered.is_(True),
                )
            )
        ).scalar_one_or_none()
        if source is None or source.currency_code not in currencies:
            continue
        row.unit_price = quantize_unit(
            convert(source.unit_price, currencies[source.currency_code], currency)
        )
        db.add(row)
        updated += 1
    await db.commit()
    return updated


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
