"""Startup seeding.

There is no public signup, so without a bootstrap administrator a fresh
deployment would have nobody who could sign in. This runs from init_db() on
every start and is safe to repeat.
"""

import logging

logger = logging.getLogger(__name__)

# Demo accounts, one per role, so every role can be exercised without walking an
# invitation through the mail log first. Development only.
DEMO_USERS = [
    ("rep@dealflow360.com", "Riya Sales Rep", "SALES_REP"),
    ("manager@dealflow360.com", "Marco Sales Manager", "SALES_MANAGER"),
    ("finance@dealflow360.com", "Fatima Finance", "FINANCE"),
    ("customer@dealflow360.com", "Acme Corp", "CUSTOMER"),
]


async def seed_users() -> None:
    """Ensures the bootstrap administrator exists, plus demo users in development."""
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
        (settings.FIRST_ADMIN_EMAIL, "DealFlow Administrator", Role.ADMIN),
    ]
    if settings.ENVIRONMENT == "development" and settings.SEED_DEMO_USERS:
        wanted += [(email, name, Role[role]) for email, name, role in DEMO_USERS]

    async with async_session_maker() as session:
        for raw_email, full_name, role in wanted:
            email = normalize_email(raw_email)
            user = await get_user_by_email(session, email=email)

            if user is None:
                session.add(
                    User(
                        email=email,
                        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                        full_name=full_name,
                        is_active=True,
                        is_verified=True,
                        role_links=[UserRole(role=role)],
                    )
                )
                try:
                    await session.commit()
                    logger.info("Seeded %s with the %s role.", email, role.value)
                except IntegrityError:
                    # Another process won the race and wrote an equivalent row.
                    await session.rollback()
                continue

            # The account exists. Repair only what could lock us out, and never
            # touch the password: overwriting it on every boot would silently
            # revert a chosen password and make the env var a standing backdoor.
            changed = False
            if role not in user.roles:
                user.role_links.append(UserRole(role=role))
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if changed:
                await session.commit()
                logger.info("Restored the %s role on %s.", role.value, email)
