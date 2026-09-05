from typing import Any
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import ping as redis_ping

router = APIRouter()


@router.get("/health")
async def health() -> Any:
    """Liveness probe. Answers as long as the process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(response: Response) -> Any:
    """Readiness probe. Reports on each backing service the API depends on."""
    checks = {"database": False, "redis": False}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    checks["redis"] = await redis_ping()

    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready else "degraded", "checks": checks}
