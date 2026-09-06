"""The upsell panel's two promises: it always has something, and the AI is optional.

The panel used to source candidates from `product_pairings` and `is_promoted`
alone, which meant an empty panel on any catalogue where nobody had entered
either. Half of these tests pin the wider sourcing; the other half pin that the
Gemini step can fail in every way it knows how without the rep noticing more
than a missing sentence.
"""

from datetime import date, timedelta

import pytest

from app.models.catalog import Currency
from app.models.customer import CustomerTier
from app.models.user import Role
from app.schemas.catalog import ProductCreate, VariantRowInput
from app.schemas.customer import CustomerCreate, CustomerTierCreate
from app.schemas.quotation import (
    QuotationCreate,
    QuotationLineCreate,
    QuotationLineUpdate,
)
from app.models.catalog import PairingSource, ProductPairing
from app.services import (
    catalog_service,
    pairing_service,
    quotation_service,
    upsell_service,
    variant_service,
)
from tests.conftest import make_user


@pytest.fixture(autouse=True)
def no_live_api(monkeypatch):
    """No test in this module may reach Google.

    The developer's own .env carries a real key, and without this the baseline
    call in each test would spend real quota - which is how this module first
    tripped a 429. Tests that exercise the AI path patch `rerank` and switch the
    key on deliberately.
    """
    monkeypatch.setattr(upsell_service.settings, "GEMINI_API_KEY", None)


async def _catalogue(db, *, products: list[tuple[str, str, float, float]]):
    """A tier, a currency and some priced products. Returns them by name."""
    db.add(Currency(code="USD", name="US Dollar", symbol="$", rate_to_base=1, is_base=True))
    await db.commit()
    tier = await catalog_service.create_customer_tier(
        db, CustomerTierCreate(name="Bronze", max_discount_percent=5)
    )

    made = {}
    for name, category, cost, price in products:
        product = await catalog_service.create_product(
            db, ProductCreate(name=name, category=category, has_variants=False)
        )
        variant = product.variants[0]
        await variant_service.save_variant_matrix(
            db,
            product,
            [
                VariantRowInput(
                    id=variant.id,
                    sku=f"SKU-{name.replace(' ', '-')}",
                    unit_cost=cost,
                    base_price=price,
                )
            ],
        )
        made[name] = await catalog_service.get_product_by_id(db, product.id)
    return tier, made


async def _quotation(db, tier, seed_product, *, email="buy@example.com", variant=None):
    """A draft with one line on it, owned by a rep.

    A distinct email means a distinct customer, which means a distinct quotation
    id - and therefore a distinct suggestions cache key, so two quotes in one
    test cannot read each other's panel.
    """
    owner = await make_user(db, f"rep-{email}", roles=[Role.SALES_REP])
    customer = await catalog_service.create_customer(
        db, CustomerCreate(name=f"Northwind {email}", tier_id=tier.id, contact_email=email)
    )
    quotation = await quotation_service.create_draft_quotation(
        db,
        owner=owner,
        obj_in=QuotationCreate(
            customer_id=customer.id,
            currency="USD",
            requested_delivery_date=date.today() + timedelta(days=14),
        ),
    )
    return await quotation_service.add_line(
        db,
        quotation,
        QuotationLineCreate(
            variant_id=(variant or seed_product.variants[0]).id,
            quantity=2,
            line_discount_percent=0,
        ),
    )


async def _record_sale(db, quotation):
    """What order confirmation writes, without the rest of confirmation.

    `mine_co_purchases` reads `sales_records` and nothing else, so this is all a
    mining test needs - and it keeps the test from depending on the whole
    fulfillment path.
    """
    from datetime import datetime, timezone

    from app.models.analytics import SalesRecord

    for line in quotation.lines:
        db.add(
            SalesRecord(
                quotation_id=quotation.id,
                product_id=line.product_id,
                product_name=line.product_name,
                customer_id=quotation.customer_id,
                category=line.category,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                sold_at=datetime.now(timezone.utc),
            )
        )
    await db.commit()


async def _pairings(db) -> dict:
    """Every pairing as {(product, suggested): source}."""
    from sqlalchemy import select

    rows = (await db.execute(select(ProductPairing))).scalars().all()
    return {(row.product_id, row.suggested_product_id): row.source for row in rows}



async def test_a_quote_with_no_pairings_still_gets_suggestions(db_session, monkeypatch):
    """The regression this whole change exists for.

    No `product_pairings` row and nothing promoted - which used to mean an
    empty panel - now fills from category affinity and margin.
    """
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Monitor", "Peripherals", 100, 400),
            ("Studio Keyboard", "Accessories", 20, 90),
            ("Care Plan", "Services", 50, 240),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert suggestions, "a Hardware line should attract accessories"
    names = {s.name for s in suggestions}
    assert "Studio Laptop" not in names, "what is on the quote is not a suggestion"
    assert all(s.rationale is None for s in suggestions)


async def test_the_margin_floor_still_suppresses(db_session, monkeypatch):
    """A6's threshold, now applied in SQL rather than in Python."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            # 5% margin, under the 10% floor.
            ("Thin Cable", "Accessories", 95, 100),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert "Thin Cable" not in {s.name for s in suggestions}


async def test_a_dismissed_product_stays_dismissed(db_session, monkeypatch):
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Monitor", "Peripherals", 100, 400),
            ("Studio Keyboard", "Accessories", 20, 90),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])
    first = (await upsell_service.suggest(db_session, quotation))[0]

    await upsell_service.dismiss(quotation.id, first.product_id)
    after = await upsell_service.suggest(db_session, quotation)

    assert first.product_id not in {s.product_id for s in after}


async def test_no_key_means_no_call_and_no_rationale(db_session, monkeypatch):
    """The AI is an improvement, never a dependency."""
    async def explode(**kwargs):  # pragma: no cover - proving it is never reached
        raise AssertionError("rerank must not be called without a key")

    monkeypatch.setattr(upsell_service.ai_ranking_service, "rerank", explode)
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Monitor", "Peripherals", 100, 400),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert suggestions
    assert all(s.rationale is None for s in suggestions)


@pytest.mark.parametrize(
    "behaviour",
    ["hallucinated", "raises", "empty"],
    ids=["every id invented", "upstream raises", "no opinion"],
)
async def test_the_panel_survives_anything_the_ranker_does(
    db_session, monkeypatch, behaviour
):
    """Whatever comes back, the deterministic list is what gets rendered."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Monitor", "Peripherals", 100, 400),
            ("Studio Keyboard", "Accessories", 20, 90),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])
    baseline = await upsell_service.suggest(db_session, quotation)

    async def fake(**kwargs):
        if behaviour == "hallucinated":
            return [("not-a-product", "invented"), ("nor-this", "also invented")]
        if behaviour == "raises":
            raise RuntimeError("upstream on fire")
        return []

    monkeypatch.setattr(upsell_service.ai_ranking_service, "rerank", fake)
    # The fingerprint carries the model name, so switching the key on gives a
    # fresh cache key rather than reusing the run above.
    monkeypatch.setattr(upsell_service.settings, "GEMINI_API_KEY", "test-key")

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert len(suggestions) == len(baseline)
    assert all(s.rationale is None for s in suggestions)


async def test_a_partly_useful_ranking_is_backfilled(db_session, monkeypatch):
    """One good pick and one invented id still fills the panel."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Monitor", "Peripherals", 100, 400),
            ("Studio Keyboard", "Accessories", 20, 90),
            ("Care Plan", "Services", 50, 240),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])
    baseline = await upsell_service.suggest(db_session, quotation)
    real_id = str(baseline[0].product_id)

    async def fake(**kwargs):
        return [(real_id, "Protects the laptop already on the quote"), ("made-up", "no")]

    monkeypatch.setattr(upsell_service.ai_ranking_service, "rerank", fake)
    monkeypatch.setattr(upsell_service.settings, "GEMINI_API_KEY", "test-key")

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert len(suggestions) == len(baseline), "the invented id is backfilled over"
    assert suggestions[0].rationale == "Protects the laptop already on the quote"
    assert all(s.rationale is None for s in suggestions[1:])


# --------------------------------------------------------------------------- #
# Ranking: the panel has to answer "what is on this quote", not "what is dear"
# --------------------------------------------------------------------------- #


async def test_different_lines_produce_different_suggestions(db_session):
    """The complaint this change exists for.

    The panel used to show the catalogue's five highest-margin products on every
    quotation, because the sort multiplied a small tier weight by a large
    currency margin. Two quotes with nothing in common must not agree.
    """
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Studio Dock", "Accessories", 30, 120),
            ("Cable Kit", "Accessories", 10, 40),
            ("Onsite Setup", "Services", 60, 300),
            ("Core Router", "Networking", 200, 600),
        ],
    )
    hardware = await _quotation(db_session, tier, made["Studio Laptop"])
    networking = await _quotation(
        db_session, tier, made["Core Router"], email="second@example.com"
    )

    a = [s.product_id for s in await upsell_service.suggest(db_session, hardware)]
    b = [s.product_id for s in await upsell_service.suggest(db_session, networking)]

    assert a and b
    assert a != b, "two unrelated quotes returned the same panel"


async def test_relevance_outranks_margin(db_session):
    """A modest accessory for what is on the quote beats a fat unrelated margin."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            # Complements the laptop, but earns almost nothing.
            ("Cable Kit", "Accessories", 10, 40),
            # Nothing to do with it, and the biggest margin in the catalogue.
            ("Core Router", "Networking", 200, 900),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    names = [s.name for s in await upsell_service.suggest(db_session, quotation)]

    assert names.index("Cable Kit") < names.index("Core Router")


async def test_a_near_duplicate_of_a_line_is_not_the_top_suggestion(db_session):
    """Another laptop beside a laptop is not a cross-sell."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Pro Laptop", "Hardware", 500, 1400),
            ("Studio Dock", "Accessories", 30, 120),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    names = [s.name for s in await upsell_service.suggest(db_session, quotation)]

    assert names.index("Studio Dock") < names.index("Pro Laptop")


async def test_a_shared_adjective_is_not_a_duplicate(db_session):
    """"Studio" is a stopword; "Laptop" is not. Pins NAME_STOPWORDS."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Studio Dock", "Accessories", 30, 120),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    top = (await upsell_service.suggest(db_session, quotation))[0]

    assert top.name == "Studio Dock"


async def test_a_configured_pairing_outranks_a_bigger_margin(db_session):
    """Somebody typed this pairing. It beats an unrelated product's margin."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Cable Kit", "Accessories", 10, 40),
            ("Core Router", "Networking", 200, 900),
        ],
    )
    db_session.add(
        ProductPairing(
            product_id=made["Studio Laptop"].id,
            suggested_product_id=made["Cable Kit"].id,
            weight=2.0,
            source=PairingSource.MANUAL,
        )
    )
    await db_session.commit()
    quotation = await _quotation(db_session, tier, made["Studio Laptop"])

    suggestions = await upsell_service.suggest(db_session, quotation)

    assert suggestions[0].name == "Cable Kit"
    assert suggestions[0].reason == "Recommended pairing"


def test_affinity_does_not_want_every_category():
    """The direct pin on the bug: the affinity set used to cover the catalogue.

    A pure unit test - `_category_demand` reads only the lines, so it needs no
    database at all.
    """

    class _Line:
        def __init__(self, category, name="Thing"):
            self.category = category
            self.product_name = name

    class _Quote:
        lines = [_Line("Hardware"), _Line("Hardware"), _Line("Networking")]

    demand = upsell_service._category_demand(_Quote())

    assert len(demand.demand) <= upsell_service.MAX_AFFINITY_CATEGORIES
    # Hardware is on the quote, so it is discounted below the cutoff rather than
    # suggested back to itself.
    assert "Hardware" not in demand.demand
    assert "Accessories" in demand.demand
    assert demand.driver["Accessories"] == "Hardware"


# --------------------------------------------------------------------------- #
# Co-purchase mining
# --------------------------------------------------------------------------- #


async def test_mining_learns_from_orders_and_spares_manual_pairings(db_session):
    """Evidence is rebuilt from history; an admin's judgement is left alone."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Studio Dock", "Accessories", 30, 120),
            ("Cable Kit", "Accessories", 10, 40),
        ],
    )
    typed = ProductPairing(
        product_id=made["Studio Laptop"].id,
        suggested_product_id=made["Cable Kit"].id,
        weight=1.5,
        source=PairingSource.MANUAL,
    )
    db_session.add(typed)
    await db_session.commit()

    # Two confirmed orders, each carrying the laptop and the dock.
    for index in range(2):
        quotation = await _quotation(
            db_session,
            tier,
            made["Studio Laptop"],
            email=f"buyer{index}@example.com",
        )
        await quotation_service.add_line(
            db_session,
            quotation,
            QuotationLineCreate(
                variant_id=made["Studio Dock"].variants[0].id,
                quantity=1,
                line_discount_percent=0,
            ),
        )
        await _record_sale(db_session, quotation)

    mined = await pairing_service.mine_co_purchases(db_session, minimum=2)

    assert mined == 2, "both directions of the laptop/dock pair"
    rows = await _pairings(db_session)
    assert (made["Studio Laptop"].id, made["Studio Dock"].id) in rows
    assert rows[(made["Studio Laptop"].id, made["Cable Kit"].id)] == PairingSource.MANUAL


async def test_mining_retires_evidence_that_no_longer_holds(db_session):
    """A pair that stops clearing the threshold stops being suggested."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Laptop", "Hardware", 400, 1000),
            ("Studio Dock", "Accessories", 30, 120),
        ],
    )
    db_session.add(
        ProductPairing(
            product_id=made["Studio Laptop"].id,
            suggested_product_id=made["Studio Dock"].id,
            weight=2.0,
            source=PairingSource.CO_PURCHASE,
        )
    )
    await db_session.commit()

    # No sales history at all, so nothing justifies that row.
    assert await pairing_service.mine_co_purchases(db_session) == 0
    assert await _pairings(db_session) == {}


# --------------------------------------------------------------------------- #
# Upsell: a better version of what is already on the quote
# --------------------------------------------------------------------------- #


async def _tiered_product(db, tier, name, *, cheap, dear):
    """One product with two priced variants, so there is something to upgrade to."""
    from app.schemas.catalog import VariantAttributeInput

    product = await catalog_service.create_product(
        db,
        ProductCreate(
            name=name,
            category="Hardware",
            has_variants=True,
            attributes=[VariantAttributeInput(name="RAM", values=["8GB", "16GB"])],
        ),
    )
    await variant_service.generate_variants(db, product)
    product = await catalog_service.get_product_by_id(db, product.id)
    rows = []
    for variant in sorted(product.variants, key=lambda v: v.name):
        price = cheap if "8GB" in variant.name else dear
        rows.append(
            VariantRowInput(
                id=variant.id,
                sku=f"SKU-{name}-{variant.name}".replace(" ", "-"),
                unit_cost=price * 0.4,
                base_price=price,
            )
        )
    await variant_service.save_variant_matrix(db, product, rows)
    return await catalog_service.get_product_by_id(db, product.id)


async def test_an_upsell_offers_only_dearer_variants(db_session):
    """A cheaper variant is a discount, not a suggestion."""
    tier, _ = await _catalogue(db_session, products=[("Filler", "Accessories", 10, 40)])
    laptop = await _tiered_product(db_session, tier, "Laptop", cheap=900, dear=1400)
    cheapest = min(laptop.variants, key=lambda v: v.base_price)
    quotation = await _quotation(db_session, tier, laptop, variant=cheapest)

    upsells = [
        s for s in await upsell_service.suggest(db_session, quotation)
        if s.kind == "upsell"
    ]

    assert upsells, "the dearer variant should be offered"
    assert all(s.price_delta > 0 for s in upsells)
    assert all(s.replaces_line_id == quotation.lines[0].id for s in upsells)
    assert all("16GB" in s.name for s in upsells)


async def test_accepting_an_upsell_swaps_the_line_in_place(db_session):
    """One line still, re-priced, with the dearer SKU on it."""
    tier, _ = await _catalogue(db_session, products=[("Filler", "Accessories", 10, 40)])
    laptop = await _tiered_product(db_session, tier, "Laptop", cheap=900, dear=1400)
    cheapest = min(laptop.variants, key=lambda v: v.base_price)
    dearest = max(laptop.variants, key=lambda v: v.base_price)
    quotation = await _quotation(db_session, tier, laptop, variant=cheapest)
    before = float(quotation.lines[0].unit_price)

    quotation = await quotation_service.update_line(
        db_session,
        quotation,
        quotation.lines[0].id,
        QuotationLineUpdate(variant_id=dearest.id),
    )

    assert len(quotation.lines) == 1, "an upgrade replaces, it does not add"
    line = quotation.lines[0]
    assert line.variant_id == dearest.id
    assert line.sku.endswith("16GB")
    assert float(line.unit_price) > before


async def test_a_line_cannot_be_swapped_to_another_product(db_session):
    """The swap is an upgrade path, not a way to replace the whole line."""
    tier, made = await _catalogue(
        db_session,
        products=[
            ("Studio Dock", "Accessories", 30, 120),
            ("Cable Kit", "Accessories", 10, 40),
        ],
    )
    quotation = await _quotation(db_session, tier, made["Studio Dock"])

    with pytest.raises(ValueError, match="different product"):
        await quotation_service.update_line(
            db_session,
            quotation,
            quotation.lines[0].id,
            QuotationLineUpdate(variant_id=made["Cable Kit"].variants[0].id),
        )
