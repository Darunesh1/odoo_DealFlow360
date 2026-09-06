"""Learning what sells together, from what has actually sold together.

`product_pairings` has always had two sources. A `MANUAL` row is an admin's
judgement — useful precisely when there is no history yet. A `CO_PURCHASE` row
is evidence, and until now nothing produced one.

This mines them from `sales_records`, which `order_service.confirm_quotation` is
the only writer of: two products on the same confirmed order have been bought
together once. Do that across every order and the strongest signal in the
suggestion engine becomes a fact about the business rather than a guess about
it — and it gets better on its own as orders land.

The one rule that matters: **a mined pass never touches a MANUAL row.** An
admin's decision is not something a nightly job gets to overwrite or delete.
"""

from collections import defaultdict
import logging
from typing import Optional
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.models.analytics import SalesRecord
from app.models.catalog import PairingSource, ProductPairing

logger = logging.getLogger(__name__)

# Below this a co-occurrence is coincidence, not a pattern. Two orders is the
# lowest number that can distinguish the two at all.
MIN_CO_PURCHASES = 2
# How many suggestions one product may carry. Without a cap, a product on every
# order pairs with the entire catalogue and the signal stops meaning anything.
MAX_PAIRS_PER_PRODUCT = 8
# What the strongest observed pair is worth. Matches PAIRING_SATURATION in
# upsell_service, so the best-evidenced pair scores full marks.
TOP_WEIGHT = 2.0


async def co_purchase_counts(
    db: AsyncSession, *, minimum: int = MIN_CO_PURCHASES
) -> dict[uuid.UUID, list[tuple[uuid.UUID, int]]]:
    """For each product, what has been bought alongside it and how often.

    One self-join over the sales history. Both directions come back, because
    "people who buy a laptop buy a dock" and the reverse are different
    suggestions and deserve their own weights.
    """
    other = SalesRecord.__table__.alias("other")
    stmt = (
        select(
            SalesRecord.product_id,
            other.c.product_id,
            func.count(func.distinct(SalesRecord.quotation_id)),
        )
        .join(
            other,
            (other.c.quotation_id == SalesRecord.quotation_id)
            & (other.c.product_id != SalesRecord.product_id),
        )
        .group_by(SalesRecord.product_id, other.c.product_id)
        .having(func.count(func.distinct(SalesRecord.quotation_id)) >= minimum)
    )

    grouped: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = defaultdict(list)
    for product_id, suggested_id, count in (await db.execute(stmt)).all():
        grouped[product_id].append((suggested_id, int(count)))

    for product_id, pairs in grouped.items():
        # Strongest first, id as a tiebreak so a rerun is stable.
        pairs.sort(key=lambda pair: (-pair[1], str(pair[0])))
        grouped[product_id] = pairs[:MAX_PAIRS_PER_PRODUCT]
    return dict(grouped)


async def mine_co_purchases(
    db: AsyncSession, *, minimum: int = MIN_CO_PURCHASES
) -> int:
    """Rebuild every CO_PURCHASE pairing from the sales history.

    Returns how many pairings now stand. Rebuild rather than merge: a pair that
    no longer clears the threshold should stop being suggested, and working out
    which rows to retire is the same query as working out which to keep.
    """
    counts = await co_purchase_counts(db, minimum=minimum)

    existing = {
        (row.product_id, row.suggested_product_id): row
        for row in (
            await db.execute(
                select(ProductPairing).where(
                    ProductPairing.source == PairingSource.CO_PURCHASE
                )
            )
        ).scalars().all()
    }

    strongest = max(
        (count for pairs in counts.values() for _, count in pairs), default=0
    )
    if not strongest:
        # No history worth mining. Retire whatever a previous run left behind
        # rather than leaving stale evidence on the screen.
        removed = await _retire(db, set(existing))
        if removed:
            await db.commit()
            await cache.bump(cache.NS_CATALOG)
        return 0

    wanted: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for product_id, pairs in counts.items():
        for suggested_id, count in pairs:
            key = (product_id, suggested_id)
            wanted.add(key)
            # Normalised against the best-evidenced pair, so the scale is
            # relative to this business rather than to an absolute order count.
            weight = round(TOP_WEIGHT * count / strongest, 4)
            row = existing.get(key)
            if row is None:
                db.add(
                    ProductPairing(
                        product_id=product_id,
                        suggested_product_id=suggested_id,
                        weight=weight,
                        source=PairingSource.CO_PURCHASE,
                    )
                )
            elif abs(float(row.weight) - weight) > 1e-6:
                row.weight = weight
                db.add(row)

    await _retire(db, set(existing) - wanted)
    await db.commit()
    # The picker and the suggestion pool both read pairings.
    await cache.bump(cache.NS_CATALOG)
    logger.info(f"Mined {len(wanted)} co-purchase pairings from the sales history.")
    return len(wanted)


async def _retire(
    db: AsyncSession, keys: set[tuple[uuid.UUID, uuid.UUID]]
) -> int:
    """Delete mined pairings that no longer hold. MANUAL rows are never in here."""
    if not keys:
        return 0
    for product_id, suggested_id in keys:
        await db.execute(
            delete(ProductPairing).where(
                ProductPairing.product_id == product_id,
                ProductPairing.suggested_product_id == suggested_id,
                ProductPairing.source == PairingSource.CO_PURCHASE,
            )
        )
    return len(keys)
