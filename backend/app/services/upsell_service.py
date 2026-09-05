"""The upsell and cross-sell panel (spec B5, configured by A6).

Suggestions come from two places, both configuration rather than guesswork:

* ``product_pairings`` - what has historically been bought alongside what,
  carrying a weight.
* ``products.is_promoted`` - what the business is pushing this quarter, which
  A6 says should rank higher.

A6 also asks for a **minimum margin threshold**, so a suggestion that would
cost the company money never surfaces however well it pairs. That check is the
reason this returns a margin delta at all: the panel has to show the rep what
adding the line does to the deal, and the same number decides whether the line
is worth suggesting.
"""

from decimal import Decimal
from typing import Optional, Sequence
import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import settings
from app.models.catalog import PairingSource, Product, ProductPairing, ProductStatus, ProductVariant
from app.models.quotation import Quotation
from app.services import pricing_service

# How thin a margin may be before a suggestion is suppressed. A percentage of
# the selling price, so it means the same thing on a $46 plan and a $1,200
# laptop.
DEFAULT_MIN_MARGIN_PERCENT = 10.0

SUGGESTION_LIMIT = 5
DISMISS_TTL = 86_400


class Suggestion(BaseModel):
    """One card in the panel."""

    product_id: uuid.UUID
    variant_id: uuid.UUID
    name: str
    category: str
    sku: str
    unit_price: float
    unit_cost: float
    # What one unit adds to the deal's margin. The mockup's "Margin +$46".
    margin_delta: float
    margin_percent: float
    is_promoted: bool
    promotion_label: Optional[str] = None
    is_recurring: bool
    reason: str


def _min_margin_percent() -> float:
    return float(getattr(settings, "MIN_UPSELL_MARGIN_PERCENT", DEFAULT_MIN_MARGIN_PERCENT))


def _default_variant(product: Product) -> Optional[ProductVariant]:
    """What a one-click "Add to Quote" would put on the line.

    The default variant if there is one, otherwise the first active. A product
    with no sellable variant is not suggestible.
    """
    active = [v for v in product.variants if v.is_active]
    if not active:
        return None
    return next((v for v in active if v.is_default), active[0])


async def _candidates(
    db: AsyncSession, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[float, str]]:
    """Product ids worth suggesting, mapped to (weight, why).

    Pairings for what is already on the quote, plus everything currently
    promoted. A product that is both keeps the higher weight.
    """
    scored: dict[uuid.UUID, tuple[float, str]] = {}

    if product_ids:
        rows = (
            await db.execute(
                select(ProductPairing).where(ProductPairing.product_id.in_(product_ids))
            )
        ).scalars().all()
        for row in rows:
            weight = float(row.weight)
            reason = (
                "Often bought together"
                if row.source == PairingSource.CO_PURCHASE
                else "Recommended pairing"
            )
            current = scored.get(row.suggested_product_id)
            if current is None or weight > current[0]:
                scored[row.suggested_product_id] = (weight, reason)

    promoted = (
        await db.execute(
            select(Product).where(
                Product.is_promoted.is_(True),
                Product.status == ProductStatus.ACTIVE,
            )
        )
    ).scalars().all()
    for product in promoted:
        current = scored.get(product.id)
        # Promoted products get a floor, not a ceiling: a strong pairing that
        # is also promoted keeps its own weight.
        weight = max(current[0] if current else 0.0, 1.0)
        scored[product.id] = (weight, "Currently promoted")

    return scored


async def suggest(
    db: AsyncSession, quotation: Quotation, *, limit: int = SUGGESTION_LIMIT
) -> list[Suggestion]:
    """Ranked suggestions for one quotation, priced for that customer's tier."""
    on_quote = {line.product_id for line in quotation.lines if line.product_id}
    scored = await _candidates(db, on_quote)

    dismissed = await cache.set_members(cache.NS_QUOTATION, f"dismissed:{quotation.id}")
    wanted = [pid for pid in scored if pid not in on_quote and str(pid) not in dismissed]
    if not wanted:
        return []

    products = (
        await db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.id.in_(wanted), Product.status == ProductStatus.ACTIVE)
        )
    ).scalars().all()

    min_margin = _min_margin_percent()
    suggestions: list[Suggestion] = []

    for product in products:
        variant = _default_variant(product)
        if variant is None:
            continue

        price = await pricing_service.resolve_variant_price(
            db,
            variant_id=variant.id,
            tier_id=quotation.customer_tier_id,
            currency_code=quotation.currency,
        )
        if price is None:
            # No price for this tier and currency yet: an unpriced SKU must
            # never be one click away from a quotation line.
            continue

        unit_price = Decimal(str(price))
        unit_cost = Decimal(str(variant.unit_cost))
        margin = unit_price - unit_cost
        margin_percent = float(margin / unit_price * 100) if unit_price else 0.0

        # A6's minimum margin threshold. Suppressed, not shown greyed out - a
        # rep should not have to judge which suggestions are safe.
        if margin_percent < min_margin:
            continue

        weight, reason = scored[product.id]
        suggestions.append(
            Suggestion(
                product_id=product.id,
                variant_id=variant.id,
                name=product.name,
                category=product.category,
                sku=variant.sku,
                unit_price=float(unit_price),
                unit_cost=float(unit_cost),
                margin_delta=float(margin),
                margin_percent=round(margin_percent, 2),
                is_promoted=product.is_promoted,
                promotion_label=product.promotion_label,
                is_recurring=product.is_subscription,
                reason=reason,
            )
        )

    # Promoted first, then by how much the pairing weight and the margin
    # together are worth. Ties broken by name so the order is stable between
    # refreshes rather than shuffling under the rep's cursor.
    suggestions.sort(
        key=lambda s: (
            not s.is_promoted,
            -(scored[s.product_id][0] * s.margin_delta),
            s.name,
        )
    )
    return suggestions[:limit]


async def dismiss(quotation_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Hides one suggestion for this quotation for a day.

    A UI preference with a natural expiry does not deserve a table, and a rep
    who dismisses the docking station today should still be offered it on
    tomorrow's deal.
    """
    await cache.set_add(
        cache.NS_QUOTATION, f"dismissed:{quotation_id}", str(product_id), DISMISS_TTL
    )
