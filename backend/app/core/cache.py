"""Redis-backed read cache and advisory locks.

Two problems, one module.

**Caching.** The catalog is read on every quotation screen and written rarely,
which is the shape a cache is for. Keys carry a *version* segment read from a
counter in Redis, so invalidation is a single ``INCR`` on that counter rather
than a ``SCAN``/``DEL`` sweep across an unknown key space. Bumping the version
orphans the old keys, which then expire on their own TTL. That makes
invalidation O(1), safe when two writers race, and impossible to get partially
wrong - there is no key list to keep in step with the keys actually written.

**Locks.** Confirming an order and running the biller both have to be
idempotent under a double-clicked button or a retried Celery task. ``with_lock``
is a ``SET NX EX`` held for the length of a block.
"""

from contextlib import asynccontextmanager
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from redis.asyncio import Redis

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Namespaces. One per family of reads that share an invalidation trigger, so a
# price edit does not throw away the reports as well.
#
# There is deliberately no dashboard namespace: its tiles are read live. They
# are cheap, per-viewer, and moved by nearly every write in the system, so a
# cache there buys tens of milliseconds and risks a tile disagreeing with the
# list it links to.
NS_CATALOG = "catalog"
NS_QUOTATION = "quotation"
NS_REPORT = "report"

CACHE_PREFIX = "cache"
LOCK_PREFIX = "lock"

# Sensible defaults; callers may override per key.
TTL_CATALOG = 300
TTL_SUGGESTIONS = 60
TTL_REPORT = 300
TTL_REP_AVERAGE = 3600


async def _version(redis: Redis, namespace: str) -> int:
    """The current generation of a namespace. Missing counts as generation 1."""
    raw = await redis.get(f"{CACHE_PREFIX}:{namespace}:version")
    try:
        return int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        return 1


async def bump(namespace: str) -> int:
    """Invalidates every cached read in a namespace.

    Call this after a write, not before: a reader that races an in-flight write
    should see the stale value and then the bump, never the reverse.
    """
    redis = get_redis_client()
    try:
        return int(await redis.incr(f"{CACHE_PREFIX}:{namespace}:version"))
    except Exception as exc:
        # A cache that cannot invalidate must not take the write down with it.
        logger.warning(f"Cache bump for {namespace} failed: {exc}")
        return 0


async def cache_key(namespace: str, suffix: str) -> str:
    version = await _version(get_redis_client(), namespace)
    return f"{CACHE_PREFIX}:{namespace}:v{version}:{suffix}"


async def cached_json(
    namespace: str,
    suffix: str,
    ttl: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    """Returns the cached value for a key, or loads, stores and returns it.

    Every Redis call is guarded: if Redis is down the loader still runs and the
    request still succeeds, just uncached. A cache is an optimisation, never a
    dependency.
    """
    redis = get_redis_client()
    key: Optional[str] = None
    try:
        key = await cache_key(namespace, suffix)
        hit = await redis.get(key)
        if hit is not None:
            return json.loads(hit)
    except Exception as exc:
        logger.warning(f"Cache read failed for {namespace}:{suffix}: {exc}")
        key = None

    value = await loader()

    if key is not None:
        try:
            await redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:
            logger.warning(f"Cache write failed for {key}: {exc}")
    return value


async def drop(namespace: str, suffix: str) -> None:
    """Removes one key without bumping the whole namespace."""
    try:
        redis = get_redis_client()
        await redis.delete(await cache_key(namespace, suffix))
    except Exception as exc:
        logger.warning(f"Cache drop failed for {namespace}:{suffix}: {exc}")


class LockNotAcquired(RuntimeError):
    """Someone else is already doing this. Retrying later may succeed."""


class LockUnavailable(RuntimeError):
    """Redis could not be reached, so no lock could be taken at all."""


@asynccontextmanager
async def with_lock(name: str, ttl: int = 30) -> AsyncIterator[None]:
    """Holds a short advisory lock for the length of the block.

    The TTL is the safety net: a worker killed mid-block releases the lock when
    it expires rather than wedging the resource forever.

    Unlike the caches, this one **fails closed**. Reading uncached is merely
    slower, but confirming an order twice writes the sales history twice, and
    there is no unique index on sales_records to catch it. If Redis is
    unreachable the caller is told so rather than proceeding unprotected -
    which is also academic in practice, because Redis is the Celery broker, so
    an outage has already stopped the workers.
    """
    redis = get_redis_client()
    key = f"{LOCK_PREFIX}:{name}"
    try:
        acquired = await redis.set(key, "1", nx=True, ex=max(ttl, 1))
    except Exception as exc:
        logger.error(f"Could not reach Redis to lock {name}: {exc}")
        raise LockUnavailable(
            "The coordination service is unavailable, so this cannot be done "
            "safely right now. Please try again in a moment."
        ) from exc

    if not acquired:
        raise LockNotAcquired(f"Another operation on {name} is already running")
    try:
        yield
    finally:
        try:
            await redis.delete(key)
        except Exception as exc:
            # The TTL will clear it; losing the release is not worth failing a
            # request that has already done its work.
            logger.warning(f"Lock release failed for {key}: {exc}")


# Sets, used for per-quotation upsell dismissals: a UI preference with a
# natural expiry does not deserve a table.
async def set_add(namespace: str, suffix: str, member: str, ttl: int) -> None:
    try:
        redis = get_redis_client()
        key = f"{CACHE_PREFIX}:{namespace}:set:{suffix}"
        await redis.sadd(key, member)
        await redis.expire(key, ttl)
    except Exception as exc:
        logger.warning(f"Cache set_add failed for {namespace}:{suffix}: {exc}")


async def set_members(namespace: str, suffix: str) -> set[str]:
    try:
        redis = get_redis_client()
        return set(await redis.smembers(f"{CACHE_PREFIX}:{namespace}:set:{suffix}"))
    except Exception as exc:
        logger.warning(f"Cache set_members failed for {namespace}:{suffix}: {exc}")
        return set()
