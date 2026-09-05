from fastapi import APIRouter

from app.api.endpoints import admin, auth, catalog, health, lookups, quotations, users
from app.core.config import settings

# Application API. Unversioned: there is one frontend, shipped with this
# backend, so there is no external client to keep a v1 alive for.
api_router = APIRouter(prefix=settings.API_PREFIX)
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(catalog.router, prefix="/admin", tags=["Catalog"])
api_router.include_router(lookups.router, prefix="/lookups", tags=["Lookups"])
api_router.include_router(quotations.router, tags=["Quotations"])

# Operational routes, mounted at the root for orchestrator probes.
health_router = health.router
