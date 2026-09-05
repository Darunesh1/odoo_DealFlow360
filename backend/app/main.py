from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router, health_router
from app.core.config import settings
from app.core.database import init_db

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
    yield
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

app.include_router(health_router, tags=["Status"])
app.include_router(api_router)


@app.get("/", tags=["Status"])
async def root():
    """Welcome page / Status endpoint returning application metadata."""
    return {
        "title": app.title,
        "version": app.version,
        "docs_url": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
        "status": "healthy",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
