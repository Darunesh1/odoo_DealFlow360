"""Fixed-window rate limiting over Redis.

Public write routes need a ceiling: ``/register`` creates rows for anyone who
asks, and ``/login`` and ``/forgot-password`` are the two an attacker grinds.

A fixed window rather than a sliding one - two counters and an EXPIRE, no
sorted set to trim. It lets a burst straddle a window boundary, which for a
sign-up form is a trade worth making for the simplicity.

Every limit is checked against **both** the caller's IP and the address they
named, because the two attacks are different: one host trying many addresses,
and many hosts trying one.
"""

from dataclasses import dataclass
import hashlib
import logging
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

PREFIX = "ratelimit"


@dataclass(frozen=True)
class Limit:
    """`times` attempts per `seconds`."""

    times: int
    seconds: int


# Tuned so a real person never meets them and a script always does.
LOGIN = Limit(times=10, seconds=300)
REGISTER = Limit(times=5, seconds=3600)
PASSWORD_RESET = Limit(times=5, seconds=3600)


def client_ip(request: Request) -> str:
    """The caller's address, trusting one proxy hop if there is one."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _hash(value: str) -> str:
    """Email addresses are not stored in Redis in the clear.

    A cache dump should not become a list of who uses the product.
    """
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]


async def _hit(bucket: str, limit: Limit) -> int:
    """Increments one counter and returns the seconds left, or 0 if under."""
    redis = get_redis_client()
    key = f"{PREFIX}:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        # Only the first hit sets the expiry, so the window is fixed from the
        # first attempt rather than sliding forward with every retry - which
        # would let a steady drip hold the key alive forever.
        await redis.expire(key, limit.seconds)
    if count > limit.times:
        return max(int(await redis.ttl(key)), 1)
    return 0


async def enforce(
    request: Request,
    *,
    scope: str,
    limit: Limit,
    identifier: Optional[str] = None,
) -> None:
    """Raises 429 with a Retry-After once either counter is over its limit.

    Redis being unavailable must not lock everyone out of signing in, so a
    failure here logs and lets the request through.
    """
    try:
        buckets = [f"{scope}:ip:{client_ip(request)}"]
        if identifier:
            buckets.append(f"{scope}:id:{_hash(identifier)}")
        retry_after = max([await _hit(bucket, limit) for bucket in buckets])
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Rate limit check failed for {scope}, allowing: {exc}")
        return

    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )
