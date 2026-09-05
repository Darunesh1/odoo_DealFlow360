from fastapi import APIRouter

from app.api.endpoints import (
    admin,
    approvals,
    auth,
    catalog,
    health,
    lookups,
    products,
    quotations,
    users,
    warehouses,
)
from app.core.config import settings

# Application API. Unversioned: there is one frontend, shipped with this
# backend, so there is no external client to keep a v1 alive for.
api_router = APIRouter(prefix=settings.API_PREFIX)
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(catalog.router, prefix="/admin", tags=["Catalog"])
# Read-only catalog for every internal role, and warehouses for Finance too.
# Split out of the admin router rather than duplicated, so there is one
# implementation of each read and no chance of the two drifting.
api_router.include_router(products.router, tags=["Products"])
api_router.include_router(warehouses.router, prefix="/admin", tags=["Warehouses"])
api_router.include_router(lookups.router, prefix="/lookups", tags=["Lookups"])
api_router.include_router(quotations.router, tags=["Quotations"])
api_router.include_router(approvals.router, tags=["Approvals"])

# Operational routes, mounted at the root for orchestrator probes.
health_router = health.router
