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
from app.schemas.quotation import QuotationCreate, QuotationLineCreate
from app.services import catalog_service, quotation_service, upsell_service, variant_service
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


async def _quotation(db, tier, seed_product):
    """A draft with one line on it, owned by a rep."""
    owner = await make_user(db, "rep@example.com", roles=[Role.SALES_REP])
    customer = await catalog_service.create_customer(
        db, CustomerCreate(name="Northwind", tier_id=tier.id, contact_email="buy@example.com")
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
            variant_id=seed_product.variants[0].id, quantity=2, line_discount_percent=0
        ),
    )


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
