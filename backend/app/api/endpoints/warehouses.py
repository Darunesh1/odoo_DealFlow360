"""Warehouses and stock.

Open to Finance / Operations as well as admins: the spec puts warehouse
fulfillment splits and backorder decisions on that role, and they cannot make
them without being able to manage the locations.
"""

from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.api.endpoints.serializers import serialize_stock
from app.models.user import Role
from app.schemas.catalog import (
    StockRead,
    StockUpsert,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)
from app.services import catalog_service
from app.services.catalog_service import InUseError

router = APIRouter(dependencies=[Depends(require_roles(Role.ADMIN, Role.FINANCE))])


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/warehouses", response_model=List[WarehouseRead])
async def read_warehouses(db: AsyncSession = Depends(get_db)) -> Any:
    return list(await catalog_service.list_warehouses(db))


@router.post("/warehouses", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
async def create_warehouse(body: WarehouseCreate, db: AsyncSession = Depends(get_db)) -> Any:
    if await catalog_service.get_warehouse_by_code(db, body.code):
        raise _conflict(ValueError(f"Warehouse code {body.code} already exists"))
    return await catalog_service.create_warehouse(db, body)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseRead)
async def patch_warehouse(
    warehouse_id: uuid.UUID, body: WarehouseUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    warehouse = await catalog_service.get_warehouse_by_id(db, warehouse_id)
    if not warehouse:
        raise _not_found("Warehouse")
    return await catalog_service.update_warehouse(db, warehouse, body)


@router.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_warehouse(
    warehouse_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    warehouse = await catalog_service.get_warehouse_by_id(db, warehouse_id)
    if not warehouse:
        raise _not_found("Warehouse")
    try:
        await catalog_service.delete_warehouse(db, warehouse)
    except InUseError as exc:
        raise _conflict(exc)


@router.get("/stock", response_model=List[StockRead])
async def read_stock(
    db: AsyncSession = Depends(get_db),
    warehouse_id: Optional[uuid.UUID] = None,
    variant_id: Optional[uuid.UUID] = None,
) -> Any:
    items = await catalog_service.list_stock_items(
        db, warehouse_id=warehouse_id, variant_id=variant_id
    )
    return [serialize_stock(item) for item in items]


@router.post("/stock", response_model=StockRead)
async def upsert_stock(body: StockUpsert, db: AsyncSession = Depends(get_db)) -> Any:
    return serialize_stock(await catalog_service.upsert_stock_item(db, body))
