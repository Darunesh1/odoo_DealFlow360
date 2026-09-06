"""Bulk demo data, for load-testing and for a tester who wants a full system.

    uv run python scripts/generate_load_data.py --products 300 --customers 300

Written with the ORM rather than raw SQL so every rule the app enforces is
enforced here too - derived prices, a default variant per product, a licence
cap on plans. Slower to run, but the data it produces is data the application
would actually have made.

Idempotent by name: re-running tops up rather than duplicating.

The generator is idempotent **by name**, which matters when the naming scheme
changes: a re-run then adds correctly-shaped products alongside the old ones
rather than replacing them. After editing NOUN_CATEGORY or the adjectives, run
`make fresh` first (and restart the API so it re-seeds) before `make load-data`.
"""
import argparse
import asyncio
import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.INFO)

ADJECTIVES = ["Compact", "Pro", "Ultra", "Lite", "Rugged", "Studio", "Edge", "Prime"]

# The category comes from the noun, never from a die roll. It used to be
# random.choice(CATEGORIES) independent of the name, which put "Studio Laptop"
# in Peripherals and "Pro Monitor" in Services - and every category-driven
# suggestion then read as nonsense however correct the ranking was.
NOUN_CATEGORY = {
    "Laptop": "Hardware",
    "Tablet": "Hardware",
    "Workstation": "Hardware",
    "Monitor": "Peripherals",
    "Headset": "Peripherals",
    "Keyboard": "Peripherals",
    "Dock": "Accessories",
    "Cable Kit": "Accessories",
    "Stand": "Accessories",
    "Router": "Networking",
    "Switch": "Networking",
    "Access Point": "Networking",
}
SERVICE_NOUNS = ["Onsite Setup", "Installation Service", "Support Retainer", "Migration Service"]
PLAN_NOUNS = ["Care Plan", "Support Plan", "Cloud Plan", "Licence Plan"]

# What a thing of this kind costs, so a keyboard is not $890 and the margin
# component of the suggestion score reads sensibly.
CATEGORY_COST = {
    "Hardware": (400, 900),
    "Networking": (80, 400),
    "Peripherals": (40, 220),
    "Accessories": (15, 90),
    "Services": (60, 300),
    "Subscription": (10, 60),
}

# Which categories are worth pairing, and with what. Seeded as MANUAL - an
# author typed them - so `pairing_service.mine_co_purchases` leaves them alone.
PAIRING_PATTERNS = [
    ("Hardware", "Accessories"),
    ("Hardware", "Peripherals"),
    ("Hardware", "Services"),
    ("Networking", "Services"),
    ("Peripherals", "Accessories"),
]
# Real addresses the tester signs in with. Created directly rather than
# invited, so nobody has to open an inbox to get in - and so we do not email
# three live addresses every time this runs.
REAL_TESTERS = [
    ("ic45608@imail.iitm.ac.in", "IITM Madras Procurement"),
    ("22f3003115@ds.study.iitm.ac.in", "IITM Data Science Lab"),
    ("daruneshrajasekar@gmail.com", "Darunesh Rajasekar"),
]

COMPANY_A = ["Northwind", "Acme", "Beta", "Nova", "Zenith", "Orion", "Delta", "Vertex",
             "Cobalt", "Summit", "Harbour", "Ironwood", "Lumen", "Pinnacle", "Quarry"]
COMPANY_B = ["Industries", "Retail", "Systems", "Logistics", "Holdings", "Partners",
             "Traders", "Works", "Group", "Supply"]


async def main(n_products: int, n_customers: int, n_quotations: int) -> None:
    from sqlalchemy import func, select

    from app.core.database import async_session_maker
    from app.models.catalog import (
        PairingSource,
        Product,
        ProductPairing,
        ProductUnit,
        RecurringInterval,
    )
    from app.models.customer import Customer, CustomerTier
    from app.models.inventory import Warehouse
    from app.models.user import Role
    from app.schemas.catalog import ProductCreate, VariantAttributeInput, VariantRowInput
    from app.schemas.customer import CustomerCreate
    from app.schemas.quotation import QuotationCreate, QuotationLineCreate
    from app.core.config import settings
    from app.core.security import hash_password
    from app.models.user import User, UserRole
    from app.services import catalog_service, quotation_service, user_service, variant_service

    random.seed(20260906)  # Reproducible, so two runs make the same catalogue.

    # One password for every generated account, so a tester never has to look
    # one up: whatever FIRST_ADMIN_PASSWORD is set to. Hashed ONCE and reused -
    # bcrypt is ~100 ms a go, and three hundred of them would be half a minute
    # of nothing. Every copy still verifies against the same password; only the
    # salt would have differed.
    shared_password = hash_password(settings.FIRST_ADMIN_PASSWORD)

    async def ensure_login(email: str, full_name: str, customer_id=None, role=Role.CUSTOMER):
        """A sign-in-ready account. Not an invite - test data nobody can log
        into is not test data."""
        existing = await user_service.get_user_by_email(db, email=email)
        if existing is not None:
            # Repair rather than skip: an earlier run may have left an
            # unusable-password invite behind.
            existing.hashed_password = shared_password
            existing.is_active = True
            existing.is_verified = True
            if customer_id and existing.customer_id is None:
                existing.customer_id = customer_id
            if role not in existing.roles:
                # A re-run that changes the mix should move the account, not
                # leave it on the role the last run happened to give it.
                existing.role_links.append(UserRole(role=role))
            db.add(existing)
            await db.commit()
            return existing
        user = User(
            email=user_service.normalize_email(email),
            hashed_password=shared_password,
            full_name=full_name,
            customer_id=customer_id,
            is_active=True,
            is_verified=True,
            role_links=[UserRole(role=role)],
        )
        db.add(user)
        await db.commit()
        return user

    async with async_session_maker() as db:
        tiers = list(await catalog_service.list_customer_tiers(db))
        warehouses = [w for w in await catalog_service.list_warehouses(db) if w.is_active]
        if not tiers or not warehouses:
            raise SystemExit("Seed the app first: start the API once, then re-run.")

        # ---------------------------------------------------------------- #
        # Products
        # ---------------------------------------------------------------- #
        existing = (await db.execute(select(func.count()).select_from(Product))).scalar_one()
        made = 0
        for index in range(n_products):
            # One in eight is a plan, so the subscription paths get exercised;
            # one in six of the rest is a service.
            is_plan = index % 8 == 7
            is_service = not is_plan and index % 6 == 3
            if is_plan:
                noun, category = random.choice(PLAN_NOUNS), "Subscription"
            elif is_service:
                noun, category = random.choice(SERVICE_NOUNS), "Services"
            else:
                noun = random.choice(list(NOUN_CATEGORY))
                category = NOUN_CATEGORY[noun]

            name = f"{random.choice(ADJECTIVES)} {noun} {1000 + index}"
            if (
                await db.execute(select(Product).where(Product.name == name))
            ).scalars().first() is not None:
                continue

            # A third of the physical products carry a real upgrade axis, which
            # is what gives the upsell panel something to offer: "8GB -> 16GB",
            # not "Black -> Silver". Colour is not an upgrade.
            attributes = (
                [
                    VariantAttributeInput(
                        name="Capacity" if category == "Hardware" else "Tier",
                        values=(
                            ["8GB", "16GB", "32GB"]
                            if category == "Hardware"
                            else ["Standard", "Plus", "Pro"]
                        ),
                    )
                ]
                if (index % 3 == 0 and not is_plan and not is_service)
                else []
            )

            product = await catalog_service.create_product(
                db,
                ProductCreate(
                    name=name,
                    category=category,
                    unit=ProductUnit.RECURRING if is_plan else ProductUnit.EACH,
                    tax_percent=random.choice([0.0, 5.0, 12.0, 15.0]),
                    is_subscription=is_plan,
                    recurring_interval=RecurringInterval.MONTHLY if is_plan else None,
                    # A twentieth of the catalogue, so the promotion component
                    # of the suggestion score exists without swamping it.
                    is_promoted=index % 20 == 5,
                    promotion_label="Q4 push" if index % 20 == 5 else None,
                    has_variants=bool(attributes),
                    attributes=attributes,
                ),
            )

            low, high = CATEGORY_COST[category]
            cost = round(random.uniform(low, high), 2)
            # Price by the position of the value in the axis, not by the
            # variant's name. Sorting alphabetically made "8GB" the dearest of
            # 8/16/32 and "Standard" dearer than "Pro", so every upgrade the
            # panel offered was actually a downgrade.
            # One markup per product, not per variant: drawing it per row let a
            # random 1.3 on the Pro tier undercut a 1.9 on the Plus, so the
            # ladder the upsell panel offers was not always a ladder.
            markup = random.uniform(1.3, 1.9)
            axis = attributes[0].values if attributes else []
            rank = {value: index for index, value in enumerate(axis)}

            def _step(variant) -> int:
                for value, index in rank.items():
                    if value in variant.name:
                        return index
                return 0

            rows = [
                VariantRowInput(
                    id=variant.id,
                    sku=variant.sku,
                    # Later variants in the axis cost more, so the upgrade the
                    # panel offers is genuinely a step up rather than a coin toss.
                    unit_cost=round(cost * (1 + 0.25 * step), 2),
                    base_price=round(cost * (1 + 0.25 * step) * markup, 2),
                    available_quantity=None if not is_plan else random.randint(20, 200),
                    stock=(
                        []
                        if is_plan
                        else [
                            {"warehouse_id": w.id, "quantity_on_hand": random.randint(0, 120)}
                            for w in warehouses
                        ]
                    ),
                )
                for step, variant in ((_step(v), v) for v in product.variants)
            ]
            await variant_service.save_variant_matrix(db, product, rows)
            made += 1
            if made % 25 == 0:
                print(f"  {made} products…", flush=True)
        print(f"products: {existing} before, {made} added")

        # ---------------------------------------------------------------- #
        # Pairings, so the strongest suggestion signal is exercised before a
        # single order has been confirmed. MANUAL, because an author typed
        # them - `pairing_service.mine_co_purchases` rebuilds the CO_PURCHASE
        # set from the sales history and would retire anything it finds there.
        # ---------------------------------------------------------------- #
        by_category: dict[str, list] = {}
        for product in (await db.execute(select(Product))).scalars().all():
            by_category.setdefault(product.category, []).append(product)

        known = {
            (row.product_id, row.suggested_product_id)
            for row in (await db.execute(select(ProductPairing))).scalars().all()
        }
        paired = 0
        for source_category, target_category in PAIRING_PATTERNS:
            sources = by_category.get(source_category, [])
            targets = by_category.get(target_category, [])
            if not sources or not targets:
                continue
            for source in random.sample(sources, min(len(sources), 8)):
                for target in random.sample(targets, min(len(targets), 2)):
                    key = (source.id, target.id)
                    if source.id == target.id or key in known:
                        continue
                    known.add(key)
                    db.add(
                        ProductPairing(
                            product_id=source.id,
                            suggested_product_id=target.id,
                            weight=round(random.uniform(1.2, 1.8), 2),
                            source=PairingSource.MANUAL,
                        )
                    )
                    paired += 1
        await db.commit()
        print(f"pairings: {paired} added")

        # ---------------------------------------------------------------- #
        # Customers, each with a portal login
        # ---------------------------------------------------------------- #
        added_customers = 0
        for index in range(n_customers):
            name = f"{random.choice(COMPANY_A)} {random.choice(COMPANY_B)} {index + 1}"
            if (
                await db.execute(select(Customer).where(Customer.name == name))
            ).scalars().first() is not None:
                continue
            # example.com, not example.test: email-validator refuses the
            # special-use .test TLD, so a stored .test address 500s every
            # response schema carrying an EmailStr.
            email = f"buyer{index + 1}@example.com"
            customer = await catalog_service.create_customer(
                db,
                CustomerCreate(
                    name=name,
                    tier_id=random.choice(tiers).id,
                    contact_email=email,
                    billing_address=f"{name} HQ",
                ),
            )
            await ensure_login(email, name, customer_id=customer.id)
            added_customers += 1
            if added_customers % 50 == 0:
                print(f"  {added_customers} customers…", flush=True)
        print(f"customers: {added_customers} added")

        # ---------------------------------------------------------------- #
        # Internal users, so role-scoped screens have something to scope
        #
        # A mix, not thirty clones of one role: scoping is only observable
        # when several reps own different deals and somebody senior can see
        # across them. Managers and finance are a fraction of the reps, which
        # is roughly the shape of a real sales floor and enough to test that a
        # rep's screens narrow while theirs do not.
        # ---------------------------------------------------------------- #
        n_reps = max(n_customers // 20, 5)
        n_managers = max(n_reps // 5, 2)
        n_finance = max(n_reps // 5, 2)

        reps: list[User] = []
        for index in range(n_reps):
            reps.append(
                await ensure_login(
                    f"rep{index + 1}@example.com",
                    f"Test Rep {index + 1}",
                    role=Role.SALES_REP,
                )
            )
        for index in range(n_managers):
            await ensure_login(
                f"manager{index + 1}@example.com",
                f"Test Manager {index + 1}",
                role=Role.SALES_MANAGER,
            )
        for index in range(n_finance):
            await ensure_login(
                f"finance{index + 1}@example.com",
                f"Test Finance {index + 1}",
                role=Role.FINANCE,
            )
        print(
            f"internal users: {n_reps} reps, {n_managers} managers, "
            f"{n_finance} finance"
        )

        # ---------------------------------------------------------------- #
        # The tester's own accounts
        # ---------------------------------------------------------------- #
        lowest = await catalog_service.get_lowest_active_tier(db)
        for email, company in REAL_TESTERS:
            customer = await catalog_service.find_customer_by_email(db, email)
            if customer is None:
                customer = await catalog_service.create_customer(
                    db,
                    CustomerCreate(
                        name=company,
                        tier_id=(lowest or tiers[0]).id,
                        contact_email=email,
                        billing_address=f"{company} HQ",
                    ),
                )
            await ensure_login(email, company, customer_id=customer.id)
            print(f"  tester account ready: {email}  ({company})")
        tester_customer_ids = [
            (await catalog_service.find_customer_by_email(db, email)).id
            for email, _ in REAL_TESTERS
        ]

        # ---------------------------------------------------------------- #
        # Quotations, so the lists and the dashboards have volume
        # ---------------------------------------------------------------- #
        customers = list(await catalog_service.list_customers(db))
        sellable = [
            p for p in await catalog_service.list_active_products(db) if p.variants
        ]
        seeded_rep = await user_service.get_user_by_email(
            db, email="rep@dealflow360.com"
        )
        if seeded_rep is not None:
            reps.append(seeded_rep)
        if not reps or not customers or not sellable:
            print("quotations: skipped (no rep or no catalogue)")
            return

        # Give each tester something to open. Submitted, so it clears the
        # draft state the portal deliberately hides - a portal with nothing in
        # it tells a tester nothing.
        by_id = {c.id: c for c in customers}
        for customer_id in tester_customer_ids:
            customer = by_id.get(customer_id)
            if customer is None:
                continue
            for _ in range(2):
                rep = random.choice(reps)
                quotation = await quotation_service.create_draft_quotation(
                    db,
                    owner=rep,
                    obj_in=QuotationCreate(
                        customer_id=customer.id,
                        currency="USD",
                        requested_delivery_date=date.today()
                        + timedelta(days=random.randint(7, 30)),
                    ),
                )
                for _ in range(random.randint(2, 3)):
                    product = random.choice(sellable)
                    variant = random.choice([v for v in product.variants if v.is_active])
                    try:
                        quotation = await quotation_service.add_line(
                            db,
                            quotation,
                            QuotationLineCreate(
                                variant_id=variant.id,
                                quantity=random.randint(1, 5),
                                # Inside the Bronze ceiling, so it auto-approves
                                # and lands in the portal rather than sitting
                                # with an approver.
                                line_discount_percent=random.choice([0, 3, 5]),
                            ),
                        )
                    except ValueError:
                        continue
                if quotation.lines:
                    try:
                        await quotation_service.submit_quotation(db, quotation, rep)
                    except ValueError:
                        pass
        print(f"tester portals: seeded for {len(tester_customer_ids)} accounts")

        made_quotes = 0
        for index in range(n_quotations):
            customer = random.choice(customers)
            rep = random.choice(reps)
            quotation = await quotation_service.create_draft_quotation(
                db,
                owner=rep,
                obj_in=QuotationCreate(
                    customer_id=customer.id,
                    currency="USD",
                    requested_delivery_date=date.today()
                    + timedelta(days=random.randint(3, 60)),
                ),
            )
            for _ in range(random.randint(1, 4)):
                product = random.choice(sellable)
                variant = random.choice([v for v in product.variants if v.is_active])
                try:
                    quotation = await quotation_service.add_line(
                        db,
                        quotation,
                        QuotationLineCreate(
                            variant_id=variant.id,
                            quantity=random.randint(1, 10),
                            line_discount_percent=random.choice([0, 5, 8, 12, 18]),
                        ),
                    )
                except ValueError:
                    # A plan at capacity, or an archived product; skip the line.
                    continue
            # Age a third of them so the deal-health sweep has something to find.
            if index % 3 == 0:
                quotation.last_activity_at = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(8, 40)
                )
                db.add(quotation)
                await db.commit()
            made_quotes += 1
            if made_quotes % 25 == 0:
                print(f"  {made_quotes} quotations…", flush=True)
        print(f"quotations: {made_quotes} added")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products", type=int, default=300)
    parser.add_argument("--customers", type=int, default=300)
    parser.add_argument("--quotations", type=int, default=150)
    args = parser.parse_args()
    asyncio.run(main(args.products, args.customers, args.quotations))
