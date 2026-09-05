from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.database
from app.core.config import settings
from app.core.redis import get_redis_client
from app.main import app as fastapi_app
from app.models.user import User

# API routes live under the versioned prefix; tests build URLs from it so a
# prefix change never means editing every test.
API = settings.API_V1_PREFIX

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
        try:
            await session.execute(delete(User))
            await session.commit()
        except Exception:
            await session.rollback()
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

    calls = {"verification_emails": [], "welcome_emails": [], "reset_emails": []}

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

    return calls


async def register_user(
    client: AsyncClient, email: str, password: str = "password123", full_name: str = "Test User"
) -> dict:
    """Registers a user and returns the created record."""
    response = await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def verify_latest_user(client: AsyncClient, mock_emails: dict, index: int = -1) -> None:
    """Completes email verification using the most recently captured token."""
    _, kwargs = mock_emails["verification_emails"][index]
    response = await client.post(
        f"{API}/auth/verify-email", json={"token": kwargs["token"]}
    )
    assert response.status_code == 200, response.text


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


async def promote_to_superuser(db_session: AsyncSession, email: str) -> None:
    """Flips the superuser flag directly in the database, bypassing the API."""
    from app.services import get_user_by_email

    user = await get_user_by_email(db_session, email=email)
    assert user is not None
    user.is_superuser = True
    db_session.add(user)
    await db_session.commit()
