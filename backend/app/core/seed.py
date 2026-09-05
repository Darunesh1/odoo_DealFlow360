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
    """Seeds the catalog, customers, stock, and approval rules used by the demo."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import async_session_maker
    from app.models.approval import ApprovalRule, ApprovalRuleStep
    from app.models.catalog import PriceList, PriceListItem, Product, ProductCategory, RecurringInterval, ProductUnit
    from app.models.customer import Customer, CustomerTier
    from app.models.inventory import StockItem, Warehouse
    from app.services import (
        create_customer,
        create_customer_tier,
        create_price_list,
        create_product,
        create_product_category,
        create_warehouse,
        get_customer_by_id,
        get_customer_tier_by_code,
        get_customer_tier_by_id,
        get_customer_tier_by_code,
        get_price_list_by_id,
        get_price_list_item,
        get_product_by_sku,
        get_product_category_by_code,
        get_warehouse_by_code,
        upsert_price_list_item,
        upsert_stock_item,
    )
    from app.schemas.catalog import PriceListCreate, PriceListItemUpsert, ProductCreate, StockUpsert, WarehouseCreate
    from app.schemas.customer import CustomerCreate, CustomerTierCreate
    from app.models.quotation import RiskBand
    from app.models.user import Role

    if settings.ENVIRONMENT != "development" or not settings.SEED_DEMO_USERS:
        return

    tiers = [
        ("STANDARD", "Standard", 10.0, 1),
        ("GOLD", "Gold", 15.0, 2),
        ("ENTERPRISE", "Enterprise", 25.0, 3),
    ]
    categories = [
        ("HARDWARE", "Hardware", 15.0, 1),
        ("SOFTWARE", "Software", 10.0, 2),
        ("SERVICES", "Services", 10.0, 3),
    ]
    products = [
        {
            "sku": "LAPTOP-001",
            "name": "Laptop",
            "category_code": "HARDWARE",
            "list_price": 1200,
            "unit_cost": 850,
            "tax_percent": 18,
        },
        {
            "sku": "MONITOR-001",
            "name": "Monitor",
            "category_code": "HARDWARE",
            "list_price": 300,
            "unit_cost": 190,
            "tax_percent": 18,
        },
        {
            "sku": "BAG-001",
            "name": "Laptop Bag",
            "category_code": "HARDWARE",
            "list_price": 45,
            "unit_cost": 15,
            "tax_percent": 18,
        },
        {
            "sku": "INSTALL-001",
            "name": "Installation Service",
            "category_code": "SERVICES",
            "list_price": 150,
            "unit_cost": 60,
            "tax_percent": 18,
        },
        {
            "sku": "SUPPORT-001",
            "name": "Support Plan",
            "category_code": "SERVICES",
            "list_price": 200,
            "unit_cost": 80,
            "tax_percent": 18,
            "is_subscription": True,
            "recurring_interval": RecurringInterval.MONTHLY,
            "unit": ProductUnit.RECURRING,
        },
        {
            "sku": "ENT-SUB-001",
            "name": "Enterprise Subscription",
            "category_code": "SOFTWARE",
            "list_price": 500,
            "unit_cost": 180,
            "tax_percent": 18,
            "is_subscription": True,
            "recurring_interval": RecurringInterval.MONTHLY,
            "unit": ProductUnit.RECURRING,
        },
    ]
    warehouses = [
        ("CHN", "Chennai Warehouse", "Chennai, India", 50, 5, 1.0, 1),
        ("AMD", "Ahmedabad Warehouse", "Ahmedabad, India", 40, 4, 1.1, 2),
    ]

    async with async_session_maker() as session:
        tier_by_code: dict[str, CustomerTier] = {}
        for code, name, max_discount, order in tiers:
            tier = await get_customer_tier_by_code(session, code)
            if tier is None:
                tier = await create_customer_tier(
                    session,
                    CustomerTierCreate(
                        code=code,
                        name=name,
                        max_discount_percent=max_discount,
                        sort_order=order,
                    ),
                )
            else:
                tier.name = name
                tier.max_discount_percent = max_discount
                tier.sort_order = order
                session.add(tier)
                await session.commit()
                tier = await get_customer_tier_by_id(session, tier.id)
            tier_by_code[code] = tier

        category_by_code: dict[str, ProductCategory] = {}
        for code, name, max_discount, order in categories:
            category = await get_product_category_by_code(session, code)
            if category is None:
                category = await create_product_category(
                    session,
                    ProductCategoryCreate(
                        code=code,
                        name=name,
                        max_discount_percent=max_discount,
                        sort_order=order,
                    ),
                )
            else:
                category.name = name
                category.max_discount_percent = max_discount
                category.sort_order = order
                session.add(category)
                await session.commit()
                category = await get_product_category_by_code(session, code)
            category_by_code[code] = category

        product_by_sku: dict[str, Product] = {}
        for product_data in products:
            category = category_by_code[product_data["category_code"]]
            product = await get_product_by_sku(session, product_data["sku"])
            payload = dict(product_data)
            payload.pop("category_code")
            if product is None:
                product = await create_product(
                    session,
                    ProductCreate(
                        category_id=category.id,
                        **payload,
                    ),
                )
            else:
                product.name = product_data["name"]
                product.category_id = category.id
                product.list_price = product_data["list_price"]
                product.unit_cost = product_data["unit_cost"]
                product.tax_percent = product_data["tax_percent"]
                product.unit = product_data.get("unit", ProductUnit.EACH)
                product.is_subscription = product_data.get("is_subscription", False)
                product.recurring_interval = product_data.get("recurring_interval")
                session.add(product)
                await session.commit()
                product = await get_product_by_sku(session, product_data["sku"])
            product_by_sku[product_data["sku"]] = product

        default_price_list_id = await _price_list_id_by_name(session, "Default Price List")
        default_price_list = await get_price_list_by_id(session, default_price_list_id) if default_price_list_id else None
        if default_price_list is None:
            default_price_list = await create_price_list(
                session,
                PriceListCreate(name="Default Price List", tier_id=None, currency="USD", adjustment_percent=0),
            )

        for sku, unit_price in [
            ("LAPTOP-001", 1200),
            ("MONITOR-001", 300),
            ("BAG-001", 45),
            ("INSTALL-001", 150),
            ("SUPPORT-001", 200),
            ("ENT-SUB-001", 500),
        ]:
            await upsert_price_list_item(
                session,
                default_price_list.id,
                PriceListItemUpsert(product_id=product_by_sku[sku].id, unit_price=unit_price),
            )

        warehouse_by_code: dict[str, Warehouse] = {}
        for code, name, address, base_cost, per_unit, weight, order in warehouses:
            warehouse = await get_warehouse_by_code(session, code)
            if warehouse is None:
                warehouse = await create_warehouse(
                    session,
                    WarehouseCreate(
                        code=code,
                        name=name,
                        address=address,
                        shipping_base_cost=base_cost,
                        shipping_cost_per_unit=per_unit,
                        shipping_cost_weight=weight,
                        split_priority=order,
                    ),
                )
            else:
                warehouse.name = name
                warehouse.address = address
                warehouse.shipping_base_cost = base_cost
                warehouse.shipping_cost_per_unit = per_unit
                warehouse.shipping_cost_weight = weight
                warehouse.split_priority = order
                session.add(warehouse)
                await session.commit()
                warehouse = await get_warehouse_by_code(session, code)
            warehouse_by_code[code] = warehouse

        stock_rows = [
            ("CHN", "LAPTOP-001", 3, 0),
            ("AMD", "LAPTOP-001", 8, 1),
            ("CHN", "MONITOR-001", 12, 0),
            ("AMD", "MONITOR-001", 20, 0),
            ("CHN", "BAG-001", 40, 0),
            ("AMD", "BAG-001", 60, 0),
            ("CHN", "INSTALL-001", 0, 0),
            ("AMD", "INSTALL-001", 0, 0),
            ("CHN", "SUPPORT-001", 0, 0),
            ("AMD", "SUPPORT-001", 0, 0),
            ("CHN", "ENT-SUB-001", 0, 0),
            ("AMD", "ENT-SUB-001", 0, 0),
        ]
        for warehouse_code, sku, quantity_on_hand, quantity_reserved in stock_rows:
            await upsert_stock_item(
                session,
                StockUpsert(
                    warehouse_id=warehouse_by_code[warehouse_code].id,
                    product_id=product_by_sku[sku].id,
                    quantity_on_hand=quantity_on_hand,
                    quantity_reserved=quantity_reserved,
                ),
            )

        customer_rows = [
            ("Acme Corp", "GOLD", "acme@dealflow360.com"),
            ("TechWorld", "STANDARD", "procurement@techworld.com"),
        ]
        customer_ids: dict[str, uuid.UUID] = {}
        for name, tier_code, email in customer_rows:
            result = await session.execute(select(Customer).where(Customer.name == name))
            customer = result.scalar_one_or_none()
            if customer is None:
                customer = await create_customer(
                    session,
                    CustomerCreate(
                        name=name,
                        tier_id=tier_by_code[tier_code].id,
                        default_price_list_id=default_price_list.id,
                        contact_email=email,
                        billing_address=f"{name} HQ",
                    ),
                )
            else:
                customer.tier_id = tier_by_code[tier_code].id
                customer.default_price_list_id = default_price_list.id
                customer.contact_email = email
                customer.billing_address = f"{name} HQ"
                session.add(customer)
                await session.commit()
                customer = await get_customer_by_id(session, customer.id)
            customer_ids[name] = customer.id

        rules = [
            ("Low Risk Manager Approval", 0, 5, RiskBand.LOW, [Role.SALES_MANAGER]),
            ("Medium Risk Manager + Finance", 5, 15, RiskBand.MEDIUM, [Role.SALES_MANAGER, Role.FINANCE]),
            ("High Risk Manager + Finance", 15, None, RiskBand.HIGH, [Role.SALES_MANAGER, Role.FINANCE]),
        ]
        for sort_order, (name, min_score, max_score, band, roles) in enumerate(rules, start=1):
            result = await session.execute(select(ApprovalRule).where(ApprovalRule.risk_band == band))
            rule = result.scalar_one_or_none()
            if rule is None:
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
                    session.add(ApprovalRuleStep(rule_id=rule.id, step_order=step_order, role=role))
        await session.commit()


async def _price_list_id_by_name(session, name: str):
    from sqlalchemy import select

    from app.models.catalog import PriceList

    result = await session.execute(select(PriceList).where(PriceList.name == name))
    price_list = result.scalar_one_or_none()
    return price_list.id if price_list else None


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
