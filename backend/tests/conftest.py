from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.database
from app.core.config import settings
from app.core.redis import get_redis_client
from app.main import app as fastapi_app
from app.core.security import hash_password
from app.models.user import Role, User, UserRole

# API routes live under the versioned prefix; tests build URLs from it so a
# prefix change never means editing every test.
API = settings.API_PREFIX

# Override the database engine and session maker with NullPool to prevent connection reuse across pytest loops.
app.core.database.engine = create_async_engine(
    settings.async_database_url,
    poolclass=NullPool,
    future=True,
)
app.core.database.async_session_maker = async_sessionmaker(
    app.core.database.engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncGenerator[None, None]:
    """Clears users and the Redis token deny list between tests."""
    yield
    async with app.core.database.async_session_maker() as session:
        # Driven off the metadata rather than a hand-maintained list: with
        # thirty-odd tables, listing them in FK order is a trap that only bites
        # when someone adds a table and forgets. CASCADE handles the ordering.
        tables = ", ".join(
            f'"{t.name}"' for t in app.core.database.Base.metadata.sorted_tables
        )
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await session.commit()
    try:
        await get_redis_client().flushdb()
    except Exception:
        pass


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a fresh AsyncSession for asserting directly against the database."""
    async with app.core.database.async_session_maker() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Yields a test client connected to the FastAPI application."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_emails(monkeypatch):
    """Captures Celery email dispatches instead of queueing them on the broker."""
    from app.tasks import email_tasks

    calls = {
        "verification_emails": [],
        "welcome_emails": [],
        "reset_emails": [],
        "invite_emails": [],
    }

    def recorder(bucket):
        def _delay(*args, **kwargs):
            calls[bucket].append((args, kwargs))
            return None

        return _delay

    monkeypatch.setattr(
        email_tasks.send_verification_email, "delay", recorder("verification_emails")
    )
    monkeypatch.setattr(
        email_tasks.send_welcome_email, "delay", recorder("welcome_emails")
    )
    monkeypatch.setattr(
        email_tasks.send_password_reset_email, "delay", recorder("reset_emails")
    )
    monkeypatch.setattr(
        email_tasks.send_invite_email, "delay", recorder("invite_emails")
    )

    return calls


async def make_user(
    db_session: AsyncSession,
    email: str,
    password: str = "password123",
    full_name: str = "Test User",
    roles: tuple[Role, ...] = (Role.SALES_REP,),
    is_verified: bool = True,
) -> User:
    """Creates a ready-to-sign-in user straight in the database.

    Accounts are created by an administrator now, so there is no public route
    a test could register through.
    """
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_verified=is_verified,
        role_links=[UserRole(role=role) for role in roles],
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def login(client: AsyncClient, email: str, password: str = "password123") -> dict:
    """Logs in and returns the token pair."""
    response = await client.post(
        f"{API}/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def auth_headers(client: AsyncClient, email: str, password: str = "password123") -> dict:
    """Logs in and builds an Authorization header."""
    tokens = await login(client, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def grant_roles(db_session: AsyncSession, email: str, *roles: Role) -> None:
    """Adds roles to an existing user, bypassing the API."""
    from app.services import get_user_by_email

    user = await get_user_by_email(db_session, email=email)
    assert user is not None
    for role in roles:
        if role not in user.roles:
            user.role_links.append(UserRole(role=role))
    db_session.add(user)
    await db_session.commit()


async def admin_headers(
    client: AsyncClient, db_session: AsyncSession, email: str = "admin@example.com"
) -> dict:
    """Creates an administrator and returns their Authorization header."""
    await make_user(db_session, email, full_name="Admin", roles=(Role.ADMIN,))
    return await auth_headers(client, email)
