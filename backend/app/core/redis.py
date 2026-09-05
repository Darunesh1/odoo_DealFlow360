import logging
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis, from_url

from app.core.config import settings

logger = logging.getLogger(__name__)

# Key prefix for revoked refresh token ids.
REVOKED_TOKEN_PREFIX = "revoked_jti:"

_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Returns a lazily created, process wide Redis client."""
    global _client
    if _client is None:
        _client = from_url(settings.redis_url, decode_responses=True)
    return _client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding the shared Redis client."""
    yield get_redis_client()


async def close_redis() -> None:
    """Closes the shared Redis client on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def revoke_token(redis: Redis, jti: str, ttl_seconds: int) -> None:
    """Marks a refresh token id as revoked.

    The entry expires alongside the token itself, so the deny list never grows
    beyond the set of tokens that are still otherwise valid.
    """
    if not jti:
        return
    await redis.set(f"{REVOKED_TOKEN_PREFIX}{jti}", "1", ex=max(ttl_seconds, 1))


async def is_token_revoked(redis: Redis, jti: Optional[str]) -> bool:
    """Reports whether a refresh token id has been revoked."""
    if not jti:
        # Tokens issued before jti support cannot be revoked individually.
        return False
    return await redis.exists(f"{REVOKED_TOKEN_PREFIX}{jti}") == 1


async def ping() -> bool:
    """Health check helper returning True when Redis answers."""
    try:
        return bool(await get_redis_client().ping())
    except Exception as exc:
        logger.warning(f"Redis ping failed: {exc}")
        return False
