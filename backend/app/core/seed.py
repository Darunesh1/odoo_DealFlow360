"""Startup seeding for the hackathon demo."""

import logging
import uuid

logger = logging.getLogger(__name__)

DEMO_USERS = [
    ("rep@dealflow360.com", "Riya Sales Rep", "SALES_REP"),
    ("manager@dealflow360.com", "Marco Sales Manager", "SALES_MANAGER"),
    ("finance@dealflow360.com", "Fatima Finance", "FINANCE"),
    ("customer@dealflow360.com", "Acme Corp", "CUSTOMER"),
]


async def seed_demo_data() -> None:
    """Seeds the mockup's catalog: currencies, tiers, category ceilings,
    products with their generated variants, per-warehouse stock, tier prices,
    customers and the approval chain.

    Idempotent and keyed on natural names, so a restart repairs rather than
    duplicates.
    """
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import async_session_maker
    from app.models.approval import ApprovalRule, ApprovalRuleStep
    from app.models.catalog import (
        CategoryDiscountLimit,
        Currency,
        Product,
        ProductUnit,
        ProductVariant,
        RecurringInterval,
    )
    from app.models.customer import Customer, CustomerTier
    from app.models.inventory import Warehouse
    from app.models.quotation import RiskBand
    from app.models.user import Role
    from app.schemas.catalog import (
        CategoryLimitCreate,
        ProductCreate,
        VariantAttributeInput,
        VariantPriceInput,
        VariantRowInput,
        WarehouseCreate,
    )
    from app.schemas.customer import CustomerCreate, CustomerTierCreate
    from app.services import catalog_service, variant_service

    if settings.ENVIRONMENT != "development" or not settings.SEED_DEMO_USERS:
        return

    # (code, name, symbol, rate to base, is base)
    currencies = [
        ("USD", "US Dollar", "$", 1.0, True),
        ("INR", "Indian Rupee", "\u20b9", 0.012, False),
    ]
    # Screen 18's exact ceilings.
    tiers = [("Bronze", 5.0), ("Silver", 10.0), ("Gold", 15.0)]
    category_limits = [("Hardware", 15.0), ("Services", 10.0)]

    # (name, category, unit, tax %, subscription interval, attributes)
    products = [
        (
            "Laptop Pro 14", "Hardware", ProductUnit.EACH, 15.0, None,
            [("Color", ["Black", "Silver"]), ("RAM", ["8GB", "16GB"])],
        ),
        (
            "Docking Station", "Hardware", ProductUnit.EACH, 15.0, None,
            [("Color", ["Black", "Silver", "White"])],
        ),
        ("Onsite Setup Service", "Services", ProductUnit.EACH, 10.0, None, []),
        ("Extended Warranty", "Services", ProductUnit.EACH, 10.0, None, []),
        (
            "Care Plan 2yr", "Subscription", ProductUnit.RECURRING, 0.0,
            RecurringInterval.MONTHLY, [],
        ),
    ]
    # SKU suffix -> (unit cost, Bronze USD price)
    pricing = {
        "Laptop Pro 14": (850.0, 1200.0),
        "Docking Station": (110.0, 180.0),
        "Onsite Setup Service": (180.0, 450.0),
        "Extended Warranty": (60.0, 180.0),
        "Care Plan 2yr": (18.0, 46.0),
    }
    warehouses = [
        ("MAIN", "Main Warehouse", "Chennai, India", 50, 5, 1.0, 1),
        ("EAST", "East Depot", "Ahmedabad, India", 40, 4, 1.1, 2),
    ]
    customers = [
        ("Acme Corp", "Gold", "acme@dealflow360.com"),
        ("Beta Industries", "Silver", "procurement@betaindustries.com"),
        ("Nova Retail", "Bronze", "buying@novaretail.com"),
    ]

    async with async_session_maker() as session:
        # --- currencies ---------------------------------------------------- #
        for code, name, symbol, rate, is_base in currencies:
            row = (
                await session.execute(select(Currency).where(Currency.code == code))
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    Currency(
                        code=code, name=name, symbol=symbol,
                        rate_to_base=rate, is_base=is_base,
                    )
                )
        await session.commit()

        # --- tiers ----------------------------------------------------------- #
        tier_by_name: dict[str, CustomerTier] = {}
        for name, max_discount in tiers:
            tier = await catalog_service.get_customer_tier_by_name(session, name)
            if tier is None:
                tier = await catalog_service.create_customer_tier(
                    session,
                    CustomerTierCreate(name=name, max_discount_percent=max_discount),
                )
            tier_by_name[name] = tier

        # --- category ceilings ------------------------------------------------ #
        # "Subscription" is deliberately absent: no row means no ceiling, which
        # is not the same as a ceiling of zero.
        for category, max_discount in category_limits:
            if await catalog_service.get_category_limit(session, category) is None:
                await catalog_service.create_category_limit(
                    session,
                    CategoryLimitCreate(
                        category=category, max_discount_percent=max_discount
                    ),
                )

        # --- warehouses -------------------------------------------------------- #
        warehouse_by_code: dict[str, Warehouse] = {}
        for code, name, address, base_cost, per_unit, weight, priority in warehouses:
            warehouse = await catalog_service.get_warehouse_by_code(session, code)
            if warehouse is None:
                warehouse = await catalog_service.create_warehouse(
                    session,
                    WarehouseCreate(
                        code=code, name=name, address=address,
                        shipping_base_cost=base_cost,
                        shipping_cost_per_unit=per_unit,
                        shipping_cost_weight=weight,
                        split_priority=priority,
                    ),
                )
            warehouse_by_code[code] = warehouse

        # --- products, variants, prices and stock ------------------------------ #
        for name, category, unit, tax, interval, attributes in products:
            existing = (
                await session.execute(select(Product).where(Product.name == name))
            ).scalar_one_or_none()
            if existing is not None:
                continue
            product = await catalog_service.create_product(
                session,
                ProductCreate(
                    name=name,
                    category=category,
                    unit=unit,
                    tax_percent=tax,
                    is_subscription=interval is not None,
                    recurring_interval=interval,
                    has_variants=bool(attributes),
                    attributes=[
                        VariantAttributeInput(name=attribute, values=values)
                        for attribute, values in attributes
                    ],
                ),
            )
            unit_cost, bronze_price = pricing[name]
            rows = []
            for index, variant in enumerate(product.variants):
                # Laptop Pro 14 is deliberately short at Main so the warehouse
                # split demo has something to split.
                main_qty = 3 if name == "Laptop Pro 14" else 40
                east_qty = 8 if name == "Laptop Pro 14" else 25
                # Services and subscriptions are not stock-tracked at all.
                stocked = category == "Hardware"
                rows.append(
                    VariantRowInput(
                        id=variant.id,
                        sku=variant.sku,
                        unit_cost=unit_cost,
                        stock=(
                            [
                                {
                                    "warehouse_id": warehouse_by_code["MAIN"].id,
                                    "quantity_on_hand": main_qty,
                                },
                                {
                                    "warehouse_id": warehouse_by_code["EAST"].id,
                                    "quantity_on_hand": east_qty,
                                },
                            ]
                            if stocked
                            else []
                        ),
                        prices=[
                            # One entered cell per tier; the service fans the
                            # other currency out from the FX rate. Higher tiers
                            # get the better price.
                            VariantPriceInput(
                                tier_id=tier_by_name[tier_name].id,
                                currency_code="USD",
                                unit_price=round(
                                    (bronze_price + index * 30)
                                    * (1 - discount / 100),
                                    2,
                                ),
                            )
                            for tier_name, discount in (
                                ("Bronze", 0), ("Silver", 5), ("Gold", 10)
                            )
                        ],
                    )
                )
            await variant_service.save_variant_matrix(session, product, rows)

        # --- customers --------------------------------------------------------- #
        for name, tier_name, email in customers:
            existing = (
                await session.execute(select(Customer).where(Customer.name == name))
            ).scalar_one_or_none()
            if existing is None:
                await catalog_service.create_customer(
                    session,
                    CustomerCreate(
                        name=name,
                        tier_id=tier_by_name[tier_name].id,
                        contact_email=email,
                        billing_address=f"{name} HQ",
                    ),
                )

        # --- approval chain ---------------------------------------------------- #
        # A Sales Rep is never an approver and Admin is never a step. Within
        # every ceiling nobody approves, which is a rule with ZERO steps rather
        # than an absent rule - that is what lets an auto-approved quotation
        # still show up in the approvals list.
        rules = [
            ("Within tier and category limits", 0, 0.01, RiskBand.NONE, []),
            ("Over limit - Sales Manager", 0.01, 45, RiskBand.MEDIUM, [Role.SALES_MANAGER]),
            (
                "Over limit, high risk - Sales Manager then Finance",
                45, None, RiskBand.HIGH, [Role.SALES_MANAGER, Role.FINANCE],
            ),
        ]
        for sort_order, (name, min_score, max_score, band, roles) in enumerate(rules, start=1):
            rule = (
                await session.execute(
                    select(ApprovalRule).where(ApprovalRule.risk_band == band)
                )
            ).scalar_one_or_none()
            if rule is not None:
                continue
            rule = ApprovalRule(
                name=name,
                min_score=min_score,
                max_score=max_score,
                risk_band=band,
                sort_order=sort_order,
                is_active=True,
            )
            session.add(rule)
            await session.flush()
            for step_order, role in enumerate(roles, start=1):
                session.add(
                    ApprovalRuleStep(rule_id=rule.id, step_order=step_order, role=role)
                )
        await session.commit()


async def seed_users() -> None:
    """Ensures the bootstrap administrator and demo users exist."""
    from sqlalchemy.exc import IntegrityError

    from app.core.config import settings
    from app.core.database import async_session_maker
    from app.core.security import hash_password
    from app.models.user import Role, User, UserRole
    from app.services import get_user_by_email, normalize_email

    if not settings.FIRST_ADMIN_EMAIL or not settings.FIRST_ADMIN_PASSWORD:
        logger.warning("No FIRST_ADMIN_EMAIL configured; skipping seeding.")
        return

    wanted = [
        (settings.FIRST_ADMIN_EMAIL, "DealFlow Administrator", Role.ADMIN, None),
    ]
    if settings.ENVIRONMENT == "development" and settings.SEED_DEMO_USERS:
        wanted += [
            ("rep@dealflow360.com", "Riya Sales Rep", Role.SALES_REP, None),
            ("manager@dealflow360.com", "Marco Sales Manager", Role.SALES_MANAGER, None),
            ("finance@dealflow360.com", "Fatima Finance", Role.FINANCE, None),
            ("customer@dealflow360.com", "Acme Corp", Role.CUSTOMER, "Acme Corp"),
        ]

    async with async_session_maker() as session:
        for raw_email, full_name, role, customer_name in wanted:
            email = normalize_email(raw_email)
            user = await get_user_by_email(session, email=email)

            customer_id = None
            if customer_name:
                from sqlalchemy import select
                from app.models.customer import Customer

                result = await session.execute(select(Customer).where(Customer.name == customer_name))
                customer = result.scalar_one_or_none()
                customer_id = customer.id if customer else None

            if user is None:
                session.add(
                    User(
                        email=email,
                        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                        full_name=full_name,
                        customer_id=customer_id,
                        is_active=True,
                        is_verified=True,
                        role_links=[UserRole(role=role)],
                    )
                )
                try:
                    await session.commit()
                    logger.info("Seeded %s with the %s role.", email, role.value)
                except IntegrityError:
                    await session.rollback()
                continue

            changed = False
            if role not in user.roles:
                user.role_links.append(UserRole(role=role))
                changed = True
            if customer_id and user.customer_id != customer_id:
                user.customer_id = customer_id
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if changed:
                await session.commit()
                logger.info("Restored the %s role on %s.", role.value, email)
