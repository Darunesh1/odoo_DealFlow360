from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.models.user import Role, User
from app.schemas.quotation import (
    QuotationCreate,
    QuotationDiscountUpdate,
    QuotationLineCreate,
    QuotationLineRead,
    QuotationLineUpdate,
    QuotationRead,
    QuotationSubmitResponse,
    QuotationUpdate,
)
from app.services.catalog_service import get_customer_by_id
from app.services.quotation_service import (
    add_line,
    create_draft_quotation,
    ensure_quotation_loaded,
    list_quotations,
    recalculate_quotation,
    remove_line,
    submit_quotation,
    sync_customer_portal_email,
    update_line,
    update_quotation,
)

router = APIRouter(dependencies=[Depends(require_roles(Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER))])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


@router.get("/quotations", response_model=list[QuotationRead])
async def read_quotations(db: AsyncSession = Depends(get_db)) -> Any:
    return [QuotationRead.model_validate(item) for item in await list_quotations(db)]


@router.post("/quotations", response_model=QuotationRead, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    body: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    quotation = await create_draft_quotation(db, owner=current_user, obj_in=body)
    return QuotationRead.model_validate(quotation)


@router.get("/quotations/{quotation_id}", response_model=QuotationRead)
async def read_quotation(quotation_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    return QuotationRead.model_validate(quotation)


@router.patch("/quotations/{quotation_id}", response_model=QuotationRead)
async def patch_quotation(
    quotation_id: uuid.UUID,
    body: QuotationUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    updated = await update_quotation(db, quotation, body)
    return QuotationRead.model_validate(updated)


@router.post("/quotations/{quotation_id}/lines", response_model=QuotationRead, status_code=status.HTTP_201_CREATED)
async def create_quotation_line(
    quotation_id: uuid.UUID,
    body: QuotationLineCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    updated = await add_line(db, quotation, body)
    return QuotationRead.model_validate(updated)


@router.patch("/quotations/{quotation_id}/lines/{line_id}", response_model=QuotationRead)
async def patch_quotation_line(
    quotation_id: uuid.UUID,
    line_id: uuid.UUID,
    body: QuotationLineUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    updated = await update_line(db, quotation, line_id, body)
    return QuotationRead.model_validate(updated)


@router.delete("/quotations/{quotation_id}/lines/{line_id}", response_model=QuotationRead)
async def delete_quotation_line(
    quotation_id: uuid.UUID,
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    updated = await remove_line(db, quotation, line_id)
    return QuotationRead.model_validate(updated)


@router.patch("/quotations/{quotation_id}/discount", response_model=QuotationRead)
async def patch_quotation_discount(
    quotation_id: uuid.UUID,
    body: QuotationDiscountUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    updated = await update_quotation(db, quotation, body)
    return QuotationRead.model_validate(updated)


@router.post("/quotations/{quotation_id}/submit", response_model=QuotationSubmitResponse)
async def submit_quotation_api(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    customer = await get_customer_by_id(db, quotation.customer_id)
    if not customer:
        raise _not_found("Customer not found")
    submitted, approval = await submit_quotation(db, quotation, current_user)
    if submitted.recipient_email:
        await sync_customer_portal_email(
            db,
            customer=customer,
            recipient_email=submitted.recipient_email,
            quotation_number=submitted.number,
        )
    return QuotationSubmitResponse(
        quotation=QuotationRead.model_validate(submitted),
        approval_required=submitted.requires_approval,
        approval=approval,
    )

