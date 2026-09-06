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
import re
from typing import NamedTuple, Optional
import uuid

from pydantic import BaseModel, ValidationError
from sqlalchemy import case, select

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.cache import cached_json
from app.core.config import settings
from app.models.catalog import (
    PairingSource,
    Product,
    ProductPairing,
    ProductStatus,
    ProductVariant,
    VariantPrice,
)
from app.models.analytics import SalesRecord
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
# How many upgrades to offer. More than a couple and the panel stops being a
# suggestion and starts being a variant picker.
UPSELL_LIMIT = 2

# Which categories sell into which. Free text typed by an admin, so keyed
# lower-cased, and a category missing from this map simply falls through to the
# margin tier - losing affinity ranking, never losing suggestions.
#
# Deliberately a constant rather than mined from history: co-occurrence over the
# handful of confirmed orders this system has would be noise, and it would put
# an aggregate on the critical path of a screen that refetches on every
# keystroke. Worth revisiting once there are orders to learn from.
CATEGORY_AFFINITY: dict[str, dict[str, float]] = {
    "hardware": {"Accessories": 1.0, "Peripherals": 0.9, "Services": 0.7, "Subscription": 0.5},
    "peripherals": {"Accessories": 1.0, "Services": 0.45, "Hardware": 0.4},
    "networking": {"Services": 1.0, "Accessories": 0.75, "Subscription": 0.55, "Hardware": 0.4},
    "accessories": {"Hardware": 0.55, "Peripherals": 0.55},
    "services": {"Subscription": 1.0, "Hardware": 0.45, "Networking": 0.4},
    "subscription": {"Services": 1.0, "Hardware": 0.4, "Networking": 0.35},
}

# --------------------------------------------------------------------------- #
# The scoring policy, in one place so it can be argued with.
#
# Every component is normalised to 0-1 and then weighted, so these numbers *are*
# the policy. They add to 100 before the duplicate penalty.
#
# Margin is deliberately worth only ten points, and is a percentile within the
# candidate pool rather than a currency amount. The old ranking multiplied a
# tier weight by the raw margin delta, and with margins spanning $25 to $710 in
# a real catalogue that meant 0.3 x $709 beat 0.6 x $50 - so the panel showed
# the most profitable products in the catalogue on every quote, whatever was on
# it. Relevance has to be able to outrank money.
# --------------------------------------------------------------------------- #
W_CO_PURCHASE = 40.0    # mined from what has actually been sold together
W_ADMIN_PAIRING = 20.0  # a product_pairings row somebody typed
W_AFFINITY = 15.0       # complementary-category demand
W_CUSTOMER_FIT = 10.0   # this customer has bought it, or its category, before
W_MARGIN = 10.0         # tiebreak, never the driver
W_PROMOTION = 5.0       # A6 asks that promoted products rank higher
P_NEAR_DUPLICATE = 30.0 # another laptop next to a laptop is not a cross-sell

# A pairing weight at or above this counts as a full-strength signal.
PAIRING_SATURATION = 2.0
# A category already on the quote is worth less: a cross-sell beats a same-aisle
# repeat, but a second accessory is still a legitimate suggestion.
SAME_CATEGORY_PENALTY = 0.45
# Below this a category is not really wanted, and more than this many categories
# is not a preference. Together these are what stop the affinity set covering
# the whole catalogue, which is what made every panel identical.
AFFINITY_CUTOFF = 0.35
MAX_AFFINITY_CATEGORIES = 3
# So one strong signal cannot fill the panel with five of the same thing.
MAX_PER_CATEGORY = 2

# Words that carry no product identity. Every adjective the demo catalogue uses
# is here, so "Studio Laptop" and "Studio Dock" are not mistaken for the same
# kind of thing while "Studio Laptop" and "Pro Laptop" are.
NAME_STOPWORDS = frozenset({
    "studio", "compact", "rugged", "prime", "ultra", "lite", "edge", "plus",
    "mini", "max", "series", "with", "and", "for", "the", "kit", "new",
})
# Shorter tokens are initialisms and noise more often than they are nouns.
MIN_TOKEN_LENGTH = 4


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
    # The additive score that put it here, out of 100.
    score: float = 0.0
    # "cross_sell" (something else worth adding) or "upsell" (a better version
    # of something already on the quote). The two answer different questions and
    # the panel groups them separately.
    kind: str = "cross_sell"
    # Upsell only: the line this would replace, and what the swap costs.
    replaces_line_id: Optional[uuid.UUID] = None
    price_delta: Optional[float] = None


def _min_margin_percent() -> float:
    return float(getattr(settings, "MIN_UPSELL_MARGIN_PERCENT", DEFAULT_MIN_MARGIN_PERCENT))


async def _cost_factor(db: AsyncSession, currency_code: str) -> Decimal:
    """What multiplies a base-currency cost into this quote's currency.

    `product_variants.unit_cost` is typed in the base currency and every
    resolved price is in the quote's, so every margin comparison needs this.
    One scalar rather than a join: it is the same number for every row.
    """
    from app.services.catalog_service import list_currencies

    currencies = list(await list_currencies(db))
    target = next((c for c in currencies if c.code == currency_code), None)
    base = next((c for c in currencies if c.is_base), None)
    if target is None or base is None or not target.rate_to_base:
        return Decimal("1")
    return Decimal(str(base.rate_to_base)) / Decimal(str(target.rate_to_base))


async def _pairing_weights(
    db: AsyncSession, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[float, str, bool]]:
    """Pairings for what is on the quote, as (weight, why, was it mined).

    The third value separates the two strongest signals: a row mined from
    confirmed sales history is evidence, while one an admin typed is judgement.
    They are weighted differently and they say different things on the card.

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

    scored: dict[uuid.UUID, tuple[float, str, bool]] = {}
    for suggested_id, weight, source in rows:
        weight = float(weight)
        mined = source == PairingSource.CO_PURCHASE
        reason = "Often bought together" if mined else "Recommended pairing"
        current = scored.get(suggested_id)
        if current is None or weight > current[0]:
            scored[suggested_id] = (weight, reason, mined)
    return scored


class CustomerHistory(NamedTuple):
    """What this customer has bought before.

    A returning enterprise buyer and a brand-new logo should not see the same
    panel. A customer with no history scores zero everywhere, which needs no
    special case anywhere else.
    """

    products: frozenset[uuid.UUID]
    categories: frozenset[str]

    def fit(self, product_id: uuid.UUID, category: str) -> float:
        if product_id in self.products:
            return 1.0
        return 0.5 if category in self.categories else 0.0


EMPTY_HISTORY = CustomerHistory(frozenset(), frozenset())


async def _customer_history(
    db: AsyncSession, customer_id: Optional[uuid.UUID]
) -> CustomerHistory:
    """One query, cached: every product and category this customer has bought.

    Read from `sales_records`, which only `order_service.confirm_quotation`
    writes, so the TTL is the only invalidation it needs.
    """
    if customer_id is None:
        return EMPTY_HISTORY

    async def load() -> dict:
        rows = (
            await db.execute(
                select(SalesRecord.product_id, SalesRecord.category)
                .where(SalesRecord.customer_id == customer_id)
                .distinct()
            )
        ).all()
        return {
            "products": [str(product_id) for product_id, _ in rows],
            "categories": [category for _, category in rows if category],
        }

    payload = await cached_json(
        cache.NS_REPORT, f"customer-history:{customer_id}", cache.TTL_CATALOG, load
    )
    return CustomerHistory(
        products=frozenset(uuid.UUID(value) for value in payload["products"]),
        categories=frozenset(payload["categories"]),
    )


class CategoryDemand(NamedTuple):
    """How much this quote wants each category, and what made it want it."""

    demand: dict[str, float]
    driver: dict[str, str]
    on_quote: set[str]


def _category_demand(quotation: Quotation) -> CategoryDemand:
    """What would complement this quote, scored rather than merely listed.

    The old version returned the *union* of every line's complementary
    categories, which on a three-line quote covered all six categories in the
    catalogue - so "affinity" matched everything and discriminated nothing.

    Three things fix that. Lines combine with a noisy-OR, so two Hardware lines
    reinforce Accessories without the number running away. A category already on
    the quote is discounted, because a cross-sell beats a same-aisle repeat. And
    the result is cut below a threshold and capped, so a quote wants a few
    things strongly rather than everything weakly.
    """
    on_quote = {
        (line.category or "").strip()
        for line in quotation.lines
        if (line.category or "").strip()
    }

    # noisy-OR, accumulated as the probability that *nothing* wanted it
    residual: dict[str, float] = {}
    best: dict[str, tuple[float, str]] = {}
    for line in quotation.lines:
        source = (line.category or "").strip()
        for target, weight in CATEGORY_AFFINITY.get(source.lower(), {}).items():
            residual[target] = residual.get(target, 1.0) * (1.0 - weight)
            current = best.get(target)
            # Ties broken on the name so the card reads the same on every load.
            if current is None or (weight, source) > (current[0], current[1]):
                best[target] = (weight, source)

    demand = {target: 1.0 - value for target, value in residual.items()}
    for target in list(demand):
        if target in on_quote:
            demand[target] *= SAME_CATEGORY_PENALTY

    kept = sorted(
        ((target, value) for target, value in demand.items() if value >= AFFINITY_CUTOFF),
        key=lambda item: (-item[1], item[0]),
    )[:MAX_AFFINITY_CATEGORIES]

    return CategoryDemand(
        demand=dict(kept),
        driver={target: best[target][1] for target, _ in kept},
        on_quote=on_quote,
    )


def _tokens(name: str) -> set[str]:
    """The words in a product name that say what kind of thing it is."""
    return {
        token
        for token in re.split(r"[^a-z]+", (name or "").lower())
        if len(token) >= MIN_TOKEN_LENGTH and token not in NAME_STOPWORDS
    }


def _line_tokens(quotation: Quotation) -> set[str]:
    """What kinds of thing are already on the quote."""
    tokens: set[str] = set()
    for line in quotation.lines:
        tokens |= _tokens(line.product_name)
    return tokens


async def _priced_pool(
    db: AsyncSession,
    quotation: Quotation,
    *,
    exclude: set[uuid.UUID],
    pairing_ids: list[uuid.UUID],
    affinity: list[str],
    cost_factor: Decimal,
) -> list[dict]:
    """Every suggestible product, already priced for this quote, in one query.

    Product joined to its default active variant joined to that variant's price
    row for this tier and currency, with the margin floor applied in SQL. This
    used to be one `resolve_variant_price` round trip per candidate, which was
    survivable at five candidates and would not have been at sixty.
    """
    unit_price = VariantPrice.unit_price
    # `unit_cost` is typed in the base currency while `unit_price` resolves in
    # the quote's, so the cost has to be brought across before they meet -
    # otherwise the margin floor lets low-margin products through on any quote
    # that is not in the base currency.
    unit_cost = ProductVariant.unit_cost * cost_factor
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
                # Margin *percent*, not the absolute delta. Ordering the pool by
                # currency amount meant the sixty rows handed to the scorer were
                # always the dearest sixty, so a $30 cable could never reach the
                # panel however well it paired.
                ((sub.c.unit_price - sub.c.unit_cost) / sub.c.unit_price).desc(),
                sub.c.name,
            )
            .limit(POOL_LIMIT)
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _margin_percentiles(pool: list[dict]) -> dict[uuid.UUID, float]:
    """Where each candidate's margin sits within this pool, 0-1.

    A percentile rather than the currency amount, which is the whole point: the
    most profitable product in the catalogue should be worth a few points more
    than the least, not seven hundred times more.
    """
    values = sorted({float(row["unit_price"]) - float(row["unit_cost"]) for row in pool})
    if len(values) <= 1:
        return {row["product_id"]: 1.0 for row in pool}
    rank = {value: index / (len(values) - 1) for index, value in enumerate(values)}
    return {
        row["product_id"]: rank[float(row["unit_price"]) - float(row["unit_cost"])]
        for row in pool
    }


def _score_candidate(
    row: dict,
    *,
    pairings: dict[uuid.UUID, tuple[float, str, bool]],
    affinity: CategoryDemand,
    customer: CustomerHistory,
    margin_percentile: float,
    duplicate_tokens: set[str],
) -> tuple[float, str]:
    """One candidate's score out of 100, and the reason the card will show."""
    score = 0.0
    reason = "High margin add-on"

    paired = pairings.get(row["product_id"])
    if paired is not None:
        weight, pair_reason, mined = paired
        strength = min(weight, PAIRING_SATURATION) / PAIRING_SATURATION
        score += (W_CO_PURCHASE if mined else W_ADMIN_PAIRING) * strength
        reason = pair_reason

    demand = affinity.demand.get(row["category"], 0.0)
    if demand > 0:
        score += W_AFFINITY * demand
        if paired is None:
            driver = affinity.driver.get(row["category"], row["category"])
            reason = (
                f"Completes the {row['category']} on this quote"
                if row["category"] in affinity.on_quote
                else f"Pairs with the {driver} on this quote"
            )

    fit = customer.fit(row["product_id"], row["category"])
    if fit > 0:
        score += W_CUSTOMER_FIT * fit
        if paired is None and demand <= 0:
            reason = "This customer buys these"

    if row["is_promoted"]:
        score += W_PROMOTION
        if paired is None and demand <= 0 and fit <= 0:
            reason = "Currently promoted"

    score += W_MARGIN * margin_percentile

    # Another laptop beside a laptop is not a cross-sell. A penalty rather than
    # an exclusion: sometimes a rep really is adding a second unit, and a thin
    # catalogue must not produce an empty panel. A configured pairing is exempt,
    # being somebody's deliberate decision.
    if paired is None and _tokens(row["name"]) & duplicate_tokens:
        score -= P_NEAR_DUPLICATE

    return score, reason


def _diversify(suggestions: list[Suggestion]) -> list[Suggestion]:
    """Stop one strong signal filling the panel with five of the same thing.

    Stable: anything over the per-category cap is deferred to the tail rather
    than dropped, so the list is the same length and the order within a category
    is untouched.
    """
    head: list[Suggestion] = []
    tail: list[Suggestion] = []
    seen: dict[str, int] = {}
    for suggestion in suggestions:
        count = seen.get(suggestion.category, 0)
        if count < MAX_PER_CATEGORY:
            seen[suggestion.category] = count + 1
            head.append(suggestion)
        else:
            tail.append(suggestion)
    return head + tail


def _rank_deterministic(
    pool: list[dict],
    pairings: dict[uuid.UUID, tuple[float, str, bool]],
    affinity: CategoryDemand,
    customer: CustomerHistory,
    duplicate_tokens: set[str],
) -> list[Suggestion]:
    """Score and order the pool without asking anybody's opinion.

    This is what the panel shows when no key is configured, and the fallback
    whenever the ranker declines to have one. Nothing downstream may replace it -
    only reorder it.
    """
    percentiles = _margin_percentiles(pool)
    scored: list[tuple[float, Suggestion]] = []

    for row in pool:
        score, reason = _score_candidate(
            row,
            pairings=pairings,
            affinity=affinity,
            customer=customer,
            margin_percentile=percentiles[row["product_id"]],
            duplicate_tokens=duplicate_tokens,
        )
        unit_price = Decimal(str(row["unit_price"]))
        unit_cost = Decimal(str(row["unit_cost"]))
        margin = unit_price - unit_cost
        scored.append(
            (
                score,
                Suggestion(
                    product_id=row["product_id"],
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
                    score=round(score, 1),
                ),
            )
        )

    # Score first; name and id only to make the order total, so the panel does
    # not shuffle under the rep's cursor between refreshes.
    scored.sort(key=lambda item: (-round(item[0], 3), item[1].name, str(item[1].product_id)))
    return _diversify([suggestion for _, suggestion in scored])


async def _upsell_candidates(
    db: AsyncSession, quotation: Quotation, cost_factor: Decimal
) -> list[Suggestion]:
    """Better versions of what is already on the quote.

    Cross-sell asks "what else?"; upsell asks "which one?". They are different
    questions with different evidence, so this does not compete on the
    cross-sell score - a dearer variant of a line the rep has already chosen
    needs no relevance argument, it is relevant by construction.

    Ordered by the smallest uplift first: the next step up converts, a triple
    price jump does not.
    """
    quoted = {
        line.variant_id: line for line in quotation.lines if line.variant_id
    }
    product_ids = {line.product_id for line in quotation.lines if line.product_id}
    if not quoted or not product_ids:
        return []

    unit_price = VariantPrice.unit_price
    unit_cost = ProductVariant.unit_cost * cost_factor
    margin = unit_price - unit_cost

    rows = (
        await db.execute(
            select(
                Product.id.label("product_id"),
                Product.name.label("name"),
                Product.category.label("category"),
                Product.is_promoted.label("is_promoted"),
                Product.promotion_label.label("promotion_label"),
                Product.is_subscription.label("is_subscription"),
                ProductVariant.id.label("variant_id"),
                ProductVariant.name.label("variant_name"),
                ProductVariant.sku.label("sku"),
                unit_cost.label("unit_cost"),
                unit_price.label("unit_price"),
            )
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .join(VariantPrice, VariantPrice.variant_id == ProductVariant.id)
            .where(
                Product.id.in_(product_ids),
                Product.status == ProductStatus.ACTIVE,
                ProductVariant.is_active.is_(True),
                ProductVariant.id.notin_(set(quoted)),
                VariantPrice.tier_id == quotation.customer_tier_id,
                VariantPrice.currency_code == quotation.currency,
                unit_price > 0,
                # The same margin floor cross-sells clear. An upgrade that costs
                # the company money is not an upgrade worth offering.
                margin / unit_price * 100 >= _min_margin_percent(),
            )
        )
    ).mappings().all()

    by_product: dict[uuid.UUID, list] = {}
    for line in quotation.lines:
        if line.product_id:
            by_product.setdefault(line.product_id, []).append(line)

    suggestions: list[tuple[float, Suggestion]] = []
    for row in rows:
        for line in by_product.get(row["product_id"], []):
            delta = float(row["unit_price"]) - float(line.unit_price)
            if delta <= 0:
                # Only ever a step up. A cheaper variant is a discount the rep
                # can already give, not a suggestion worth making.
                continue
            price = Decimal(str(row["unit_price"]))
            cost = Decimal(str(row["unit_cost"]))
            variant_margin = price - cost
            suggestions.append(
                (
                    delta,
                    Suggestion(
                        product_id=row["product_id"],
                        variant_id=row["variant_id"],
                        name=f"{row['name']} - {row['variant_name']}",
                        category=row["category"],
                        sku=row["sku"],
                        unit_price=float(price),
                        unit_cost=float(cost),
                        margin_delta=float(variant_margin) - float(line.unit_cost or 0),
                        margin_percent=round(
                            float(variant_margin / price * 100) if price else 0.0, 2
                        ),
                        is_promoted=row["is_promoted"],
                        promotion_label=row["promotion_label"],
                        is_recurring=row["is_subscription"],
                        reason=f"A step up from {line.variant_name or 'the version'} on this quote",
                        kind="upsell",
                        replaces_line_id=line.id,
                        price_delta=round(delta, 2),
                    ),
                )
            )

    suggestions.sort(key=lambda item: (item[0], item[1].name))
    return [suggestion for _, suggestion in suggestions[:UPSELL_LIMIT]]


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
    affinity = _category_demand(quotation)
    customer = await _customer_history(db, quotation.customer_id)
    cost_factor = await _cost_factor(db, quotation.currency)

    pool = await _priced_pool(
        db,
        quotation,
        exclude=exclude | on_quote,
        pairing_ids=list(pairings),
        affinity=list(affinity.demand),
        cost_factor=cost_factor,
    )
    ranked = _rank_deterministic(
        pool, pairings, affinity, customer, _line_tokens(quotation)
    )[:AI_CANDIDATE_LIMIT]

    # Upgrades are sourced and ordered separately, and are not sent to the
    # ranker: a dearer version of a line the rep already chose is relevant by
    # construction, and asking a model to re-argue that only risks it dropping
    # one. They are prepended, so the panel leads with "you could sell more of
    # what they already want".
    upsells = await _upsell_candidates(db, quotation, cost_factor)

    if not ranked:
        return upsells

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
        return upsells + ranked[:CACHE_OVERFETCH]

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
    return upsells + chosen


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
    #
    # Upgrades are kept whole and the cross-sell list is trimmed around them, so
    # offering two upsells never costs the rep every cross-sell.
    visible = [s for s in cached if s.product_id not in exclude]
    upsells = [s for s in visible if s.kind == "upsell"]
    cross = [s for s in visible if s.kind != "upsell"]
    return upsells[:UPSELL_LIMIT] + cross[: max(limit - len(upsells[:UPSELL_LIMIT]), 1)]


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
