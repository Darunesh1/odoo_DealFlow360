import logging
from typing import AsyncGenerator
import asyncpg
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure SQLAlchemy Async Engine
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.ENVIRONMENT == "development",
    future=True,
)

# Async Session Factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy database models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator for database sessions to use in FastAPI endpoints."""
    async with async_session_maker() as session:
        yield session


async def create_database_if_not_exists() -> None:
    """Connects to the default 'postgres' database and creates the configured database if it does not exist."""
    try:
        # Connect directly using asyncpg to default template database 'postgres'
        conn = await asyncpg.connect(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_SERVER,
            port=settings.POSTGRES_PORT,
            database="postgres",
        )
        try:
            # Query if configured database exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                settings.POSTGRES_DB,
            )
            if not exists:
                # pg_database check returned null; create database.
                # In PostgreSQL, CREATE DATABASE cannot run inside a transaction block,
                # which asyncpg execute runs outside by default unless explicitly in transaction.
                await conn.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
                logger.info(
                    f"Successfully created database: '{settings.POSTGRES_DB}'"
                )
            else:
                logger.info(f"Database '{settings.POSTGRES_DB}' already exists.")
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error checking/creating database '{settings.POSTGRES_DB}': {e}")
        # Re-raise so startup fails if DB connection is unavailable
        raise e


async def init_db() -> None:
    """Performs startup database verification and table creation."""
    if settings.ENVIRONMENT == "development":
        logger.info("Dev environment detected: verifying database exists...")
        await create_database_if_not_exists()

    # Import every model here to register it with the Base metadata before
    # table creation. A model that is not imported has its table SILENTLY
    # skipped, surfacing much later as a missing-relation error at request
    # time. The package __init__ imports all of them, so one line covers it.
    import app.models  # noqa: F401

    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")

    # Imported here rather than at module scope to avoid a
    # database -> seed -> services -> models -> database import cycle.
    from app.core.seed import seed_users

    await seed_users()
