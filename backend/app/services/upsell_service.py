"""The upsell and cross-sell panel (spec B5, configured by A6).

Suggestions are sourced in four tiers, strongest evidence first:

* ``product_pairings`` - what has historically been bought alongside what,
  carrying a weight.
* ``products.is_promoted`` - what the business is pushing this quarter, which
  A6 says should rank higher.
* **category affinity** - a laptop wants accessories, a service wants a plan.
* **margin** - anything else worth attaching, best margin first.

The last two exist because the first two are configuration somebody has to
enter, and in practice nobody has: a catalogue of three hundred products can
easily carry six pairings and one promotion, which left the panel empty on
almost every quote. Affinity and margin mean there is always something sensible
to show, while a real pairing still outranks both.

A6 also asks for a **minimum margin threshold**, so a suggestion that would
cost the company money never surfaces however well it pairs. That check is the
reason this returns a margin delta at all: the panel has to show the rep what
adding the line does to the deal, and the same number decides whether the line
is worth suggesting.

Ranking is deterministic here and then, when a Gemini key is configured,
re-ordered and annotated by `ai_ranking_service`. That step can only permute
and annotate this list - it never sources a candidate of its own, so the panel
is identical with the key removed, minus the rationale lines.
"""

from decimal import Decimal
import hashlib
import logging
from typing import Optional
import uuid

from pydantic import BaseModel, ValidationError
from sqlalchemy import case, select

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import settings
from app.models.catalog import (
    PairingSource,
    Product,
    ProductPairing,
    ProductStatus,
    ProductVariant,
    VariantPrice,
)
from app.models.quotation import Quotation
from app.services import ai_ranking_service

logger = logging.getLogger(__name__)

# How thin a margin may be before a suggestion is suppressed. A percentage of
# the selling price, so it means the same thing on a $46 plan and a $1,200
# laptop.
DEFAULT_MIN_MARGIN_PERCENT = 10.0

SUGGESTION_LIMIT = 5
DISMISS_TTL = 86_400

# How many priced candidates the ranker gets to choose from. Enough for a real
# choice, small enough that the prompt stays cheap and the model stays focused.
AI_CANDIDATE_LIMIT = 15
# How wide the SQL pool is before deterministic ranking trims it.
POOL_LIMIT = 60
# The cache holds more than it shows, so dismissing a card does not have to
# invalidate anything: dismissals are filtered after the read.
CACHE_OVERFETCH = 8

# Which categories sell into which. Free text typed by an admin, so keyed
# lower-cased, and a category missing from this map simply falls through to the
# margin tier - losing affinity ranking, never losing suggestions.
#
# Deliberately a constant rather than mined from history: co-occurrence over the
# handful of confirmed orders this system has would be noise, and it would put
# an aggregate on the critical path of a screen that refetches on every
# keystroke. Worth revisiting once there are orders to learn from.
CATEGORY_AFFINITY: dict[str, tuple[str, ...]] = {
    "hardware": ("Accessories", "Peripherals", "Services", "Subscription"),
    "peripherals": ("Accessories", "Hardware", "Services"),
    "networking": ("Hardware", "Services", "Subscription", "Accessories"),
    "accessories": ("Hardware", "Peripherals"),
    "services": ("Subscription", "Hardware", "Networking"),
    "subscription": ("Services", "Hardware", "Networking"),
}

# Weights for the tiers that have no configured weight of their own. Below the
# 1.0 floor a promoted product gets, so configuration always outranks a guess.
AFFINITY_WEIGHT = 0.6
FILLER_WEIGHT = 0.3


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
    # Where the suggestion came from: "Often bought together", "Currently
    # promoted". Deterministic, and present whether or not the ranker ran.
    reason: str
    # One sentence from the ranker about this quote specifically. None when no
    # key is configured, when the call failed, or when this card was backfilled
    # from the deterministic order.
    rationale: Optional[str] = None


def _min_margin_percent() -> float:
    return float(getattr(settings, "MIN_UPSELL_MARGIN_PERCENT", DEFAULT_MIN_MARGIN_PERCENT))


async def _pairing_weights(
    db: AsyncSession, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[float, str]]:
    """Configured pairings for what is already on the quote, as (weight, why).

    A product paired from two different lines keeps the higher weight.
    """
    if not product_ids:
        return {}

    rows = (
        await db.execute(
            select(
                ProductPairing.suggested_product_id,
                ProductPairing.weight,
                ProductPairing.source,
            ).where(ProductPairing.product_id.in_(product_ids))
        )
    ).all()

    scored: dict[uuid.UUID, tuple[float, str]] = {}
    for suggested_id, weight, source in rows:
        weight = float(weight)
        reason = (
            "Often bought together"
            if source == PairingSource.CO_PURCHASE
            else "Recommended pairing"
        )
        current = scored.get(suggested_id)
        if current is None or weight > current[0]:
            scored[suggested_id] = (weight, reason)
    return scored


def _affinity_categories(quotation: Quotation) -> tuple[list[str], dict[str, str]]:
    """Categories that complement what is on the quote, and which line drove each.

    The second value is what lets a card say "Pairs with Hardware" rather than
    an unattributed "Recommended".
    """
    wanted: list[str] = []
    driver: dict[str, str] = {}
    for line in quotation.lines:
        source = (line.category or "").strip()
        for target in CATEGORY_AFFINITY.get(source.lower(), ()):
            if target not in driver:
                driver[target] = source
                wanted.append(target)
    return wanted, driver


async def _priced_pool(
    db: AsyncSession,
    quotation: Quotation,
    *,
    exclude: set[uuid.UUID],
    pairing_ids: list[uuid.UUID],
    affinity: list[str],
) -> list[dict]:
    """Every suggestible product, already priced for this quote, in one query.

    Product joined to its default active variant joined to that variant's price
    row for this tier and currency, with the margin floor applied in SQL. This
    used to be one `resolve_variant_price` round trip per candidate, which was
    survivable at five candidates and would not have been at sixty.
    """
    unit_price = VariantPrice.unit_price
    unit_cost = ProductVariant.unit_cost
    margin = unit_price - unit_cost

    inner = (
        select(
            Product.id.label("product_id"),
            Product.name.label("name"),
            Product.category.label("category"),
            Product.is_promoted.label("is_promoted"),
            Product.promotion_label.label("promotion_label"),
            Product.is_subscription.label("is_subscription"),
            ProductVariant.id.label("variant_id"),
            ProductVariant.sku.label("sku"),
            unit_cost.label("unit_cost"),
            unit_price.label("unit_price"),
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(VariantPrice, VariantPrice.variant_id == ProductVariant.id)
        .where(
            Product.status == ProductStatus.ACTIVE,
            ProductVariant.is_active.is_(True),
            VariantPrice.tier_id == quotation.customer_tier_id,
            VariantPrice.currency_code == quotation.currency,
            unit_price > 0,
            # A6's minimum margin threshold, expressed where the rows are.
            # Suppressed rather than greyed out: a rep should not have to judge
            # which suggestions are safe to offer.
            margin / unit_price * 100 >= _min_margin_percent(),
        )
        # DISTINCT ON keeps one row per product, and the ordering picks the same
        # variant the old _default_variant() helper did: the default if there is
        # one, otherwise the first active by name.
        .distinct(Product.id)
        .order_by(Product.id, ProductVariant.is_default.desc(), ProductVariant.name)
    )
    if exclude:
        inner = inner.where(Product.id.notin_(exclude))

    sub = inner.subquery()
    # Tier order: a configured pairing beats a promotion beats an affinity guess
    # beats plain margin. `in_([])` is valid and simply never matches, so the
    # empty cases need no branch of their own.
    tier = case(
        (sub.c.product_id.in_(pairing_ids), 0),
        (sub.c.is_promoted.is_(True), 1),
        (sub.c.category.in_(affinity), 2),
        else_=3,
    )
    rows = (
        await db.execute(
            select(sub)
            .order_by(
                tier,
                (sub.c.unit_price - sub.c.unit_cost).desc(),
                sub.c.name,
            )
            .limit(POOL_LIMIT)
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _rank_deterministic(
    pool: list[dict],
    pairings: dict[uuid.UUID, tuple[float, str]],
    driver: dict[str, str],
) -> list[Suggestion]:
    """Score the pool without asking anybody's opinion.

    This is the answer the panel shows when no key is configured, and the
    fallback whenever the ranker declines to have one. Nothing downstream may
    replace it - only reorder it.
    """
    weights: dict[uuid.UUID, float] = {}
    suggestions: list[Suggestion] = []

    for row in pool:
        product_id = row["product_id"]
        paired = pairings.get(product_id)
        if paired is not None:
            weight, reason = paired
            if row["is_promoted"]:
                # Promoted is a floor, not a ceiling: a strong pairing that is
                # also promoted keeps its own weight.
                weight = max(weight, 1.0)
        elif row["is_promoted"]:
            weight, reason = 1.0, "Currently promoted"
        elif row["category"] in driver:
            weight = AFFINITY_WEIGHT
            reason = f"Pairs with {driver[row['category']]}"
        else:
            weight, reason = FILLER_WEIGHT, "High margin add-on"

        unit_price = Decimal(str(row["unit_price"]))
        unit_cost = Decimal(str(row["unit_cost"]))
        margin = unit_price - unit_cost
        weights[product_id] = weight
        suggestions.append(
            Suggestion(
                product_id=product_id,
                variant_id=row["variant_id"],
                name=row["name"],
                category=row["category"],
                sku=row["sku"],
                unit_price=float(unit_price),
                unit_cost=float(unit_cost),
                margin_delta=float(margin),
                margin_percent=round(
                    float(margin / unit_price * 100) if unit_price else 0.0, 2
                ),
                is_promoted=row["is_promoted"],
                promotion_label=row["promotion_label"],
                is_recurring=row["is_subscription"],
                reason=reason,
            )
        )

    # Promoted first, then by how much the weight and the margin together are
    # worth. Ties broken by name so the order is stable between refreshes rather
    # than shuffling under the rep's cursor.
    suggestions.sort(
        key=lambda s: (
            not s.is_promoted,
            -(weights[s.product_id] * s.margin_delta),
            s.name,
        )
    )
    return suggestions


def _fingerprint(quotation: Quotation) -> str:
    """What the suggestions depend on, hashed.

    Part of the cache key, so editing a line changes the key rather than
    needing an invalidation call at every edit site - the stale panel is
    unreachable by construction and old keys age out on the TTL. The model name
    is in here too, so removing the key cannot serve a ranking made with it.
    """
    parts = [
        str(quotation.customer_tier_id),
        str(quotation.currency),
        f"{_min_margin_percent():.2f}",
        settings.GEMINI_MODEL if settings.ai_ranking_configured else "off",
        *(
            f"{line.product_id}:{line.variant_id}:{line.quantity}"
            for line in sorted(quotation.lines, key=lambda line: line.position)
        ),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


async def _build(
    db: AsyncSession, quotation: Quotation, *, exclude: set[uuid.UUID]
) -> list[Suggestion]:
    """The whole pipeline, uncached: source, price, rank, then re-rank."""
    on_quote = {line.product_id for line in quotation.lines if line.product_id}
    pairings = await _pairing_weights(db, on_quote)
    affinity, driver = _affinity_categories(quotation)

    pool = await _priced_pool(
        db,
        quotation,
        exclude=exclude | on_quote,
        pairing_ids=list(pairings),
        affinity=affinity,
    )
    ranked = _rank_deterministic(pool, pairings, driver)[:AI_CANDIDATE_LIMIT]
    if not ranked:
        return []

    # Everything below only permutes and annotates `ranked`.
    try:
        picks = await ai_ranking_service.rerank(
            quotation=_quote_context(quotation),
            candidates=[s.model_dump(mode="json") for s in ranked],
            wanted=CACHE_OVERFETCH,
        )
    except Exception as exc:
        # rerank() already swallows its own failures; this is the belt to that
        # braces. A ranking is an improvement, never a dependency.
        logger.warning(f"Upsell re-ranking failed, using the deterministic order: {exc}")
        picks = None

    if not picks:
        return ranked[:CACHE_OVERFETCH]

    by_id = {str(s.product_id): s for s in ranked}
    chosen: list[Suggestion] = []
    seen: set[str] = set()
    for product_id, rationale in picks:
        suggestion = by_id.get(product_id)
        if suggestion is None or product_id in seen:
            continue
        seen.add(product_id)
        chosen.append(suggestion.model_copy(update={"rationale": rationale}))

    # Backfill from the deterministic order, so the panel is always as full as
    # it would have been without the ranker whatever the model returned.
    for suggestion in ranked:
        if len(chosen) >= CACHE_OVERFETCH:
            break
        if str(suggestion.product_id) not in seen:
            chosen.append(suggestion)
    return chosen


def _quote_context(quotation: Quotation) -> dict:
    """The little the ranker needs to know about the deal."""
    return {
        "customer": getattr(quotation.customer, "name", None),
        "tier": getattr(quotation.customer_tier, "name", None),
        "currency": quotation.currency,
        "line_count": len(quotation.lines),
        "total": float(quotation.total or 0),
        "lines": [
            {
                "name": line.product_name,
                "category": line.category,
                "quantity": line.quantity,
            }
            for line in quotation.lines
        ],
    }


async def suggest(
    db: AsyncSession, quotation: Quotation, *, limit: int = SUGGESTION_LIMIT
) -> list[Suggestion]:
    """Ranked suggestions for one quotation, priced for that customer's tier."""
    if quotation.customer_tier_id is None:
        # Nothing is priceable without a tier, so there is nothing safe to put
        # one click away from a line.
        return []

    dismissed = await cache.set_members(cache.NS_QUOTATION, f"dismissed:{quotation.id}")
    exclude = {uuid.UUID(value) for value in dismissed if _is_uuid(value)}

    async def load() -> list[dict]:
        built = await _build(db, quotation, exclude=exclude)
        return [item.model_dump(mode="json") for item in built]

    raw = await cache.cached_json(
        cache.NS_QUOTATION,
        f"suggestions:{quotation.id}:{_fingerprint(quotation)}",
        cache.TTL_SUGGESTIONS,
        load,
    )
    try:
        cached = [Suggestion.model_validate(item) for item in raw]
    except ValidationError as exc:
        # A schema change deployed over a warm cache must not 500 the panel.
        logger.warning(f"Discarding unreadable cached suggestions: {exc}")
        cached = await _build(db, quotation, exclude=exclude)

    # Filtered after the read, not baked into the key: otherwise dismiss() would
    # have to know the fingerprint to invalidate. The loader over-fetches so the
    # panel stays full.
    return [s for s in cached if s.product_id not in exclude][:limit]


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def dismiss(quotation_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Hides one suggestion for this quotation for a day.

    A UI preference with a natural expiry does not deserve a table, and a rep
    who dismisses the docking station today should still be offered it on
    tomorrow's deal.
    """
    await cache.set_add(
        cache.NS_QUOTATION, f"dismissed:{quotation_id}", str(product_id), DISMISS_TTL
    )
