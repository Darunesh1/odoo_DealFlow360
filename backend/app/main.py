import asyncio
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router, health_router
from app.core.cache import LockNotAcquired, LockUnavailable
from app.core.config import settings
from app.core.database import init_db

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _startup_sweep() -> None:
    """Raise the deal-health alerts the current state justifies, once, at boot.

    Alerts only exist once a sweep writes them, and the only scheduled caller is
    Celery Beat - which is a separate `make beat` process that is easy not to be
    running. Without this the screen is empty on a perfectly healthy install and
    there is no way to tell that apart from "nothing is wrong".

    Detached and swallowing everything on purpose: a slow or failing sweep must
    never delay or abort startup, the same reasoning as
    `approval_service.plan_if_approved`. It opens its own session because the
    request-scoped one does not exist yet.
    """
    from app.core.database import async_session_maker
    from app.services import health_service

    try:
        async with async_session_maker() as db:
            raised = await health_service.sweep(db)
        logger.info(f"Startup deal-health sweep raised {raised} alert(s).")
    except Exception as exc:
        logger.warning(f"Startup deal-health sweep failed, continuing: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager that runs code on server startup and shutdown."""
    logger.info("Starting up FastAPI application...")
    try:
        # Run database checks and table initialization
        await init_db()
    except Exception as e:
        logger.error(f"Startup database initialization failed: {e}")
        # Terminate startup if database is unavailable
        raise e
    sweep_task = asyncio.create_task(_startup_sweep())
    yield
    sweep_task.cancel()
    logger.info("Shutting down FastAPI application...")
    from app.core.database import engine
    from app.core.redis import close_redis

    await engine.dispose()
    await close_redis()
    logger.info("Database and cache connections closed successfully.")


app = FastAPI(
    title="DealFlow360 API",
    description="Backend API for DealFlow360.",
    version="1.0.0",
    lifespan=lifespan,
)

# Browser clients must be listed explicitly: a wildcard origin is invalid once
# credentials are allowed, and browsers reject the combination outright.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(LockNotAcquired)
async def _lock_busy(request: Request, exc: LockNotAcquired) -> JSONResponse:
    """A double-clicked button, or two people acting on the same order.

    409 rather than 500: nothing is broken, the caller simply lost a race and
    retrying is the right response. Handled here so every route that takes a
    lock behaves the same way without repeating the try/except.
    """
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "That is already being processed. Give it a moment."},
    )


@app.exception_handler(LockUnavailable)
async def _lock_unavailable(request: Request, exc: LockUnavailable) -> JSONResponse:
    """Redis is unreachable, so the operation cannot be made safe."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


app.include_router(health_router, tags=["Status"])
app.include_router(api_router)


@app.get("/", tags=["Status"])
async def root():
    """Welcome page / Status endpoint returning application metadata."""
    return {
        "title": app.title,
        "version": app.version,
        "docs_url": "/docs",
        "api_prefix": settings.API_PREFIX,
        "status": "healthy",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
