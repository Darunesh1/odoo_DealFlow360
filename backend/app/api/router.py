from fastapi import APIRouter

from app.api.endpoints import admin, auth, health, users
from app.core.config import settings

# Versioned application API.
api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])

# Unversioned operational routes, mounted at the root for orchestrator probes.
health_router = health.router
