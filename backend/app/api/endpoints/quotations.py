from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, get_db, get_pagination, require_roles
from app.models.quotation import QuotationStatus
from app.models.user import Role, User
from app.schemas.catalog import SortOrder
from app.schemas.quotation import (
    QuotationCreate,
    QuotationListPage,
    QuotationListRow,
    QuotationSort,
    QuotationStageCounts,
    QuotationDiscountUpdate,
    QuotationLineCreate,
    QuotationLineRead,
    QuotationLineUpdate,
    QuotationRead,
    QuotationSubmitResponse,
    QuotationUpdate,
)
from app.schemas.quotation import UpsellSuggestion
from app.services import upsell_service
from app.services.catalog_service import get_customer_by_id
from app.services.quotation_service import (
    add_line,
    create_draft_quotation,
    delete_quotation,
    ensure_quotation_loaded,
    list_quotations,
    recalculate_quotation,
    reload_quotation,
    remove_line,
    search_quotations,
    stage_counts,
    submit_quotation,
    sync_customer_portal_email,
    update_line,
    update_quotation,
)

router = APIRouter(dependencies=[Depends(require_roles(Role.ADMIN, Role.SALES_REP, Role.SALES_MANAGER))])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _row(quotation) -> QuotationListRow:
    """Flattens a quotation into a list row.

    The customer and tier are already loaded (both selectin at the mapper), so
    this costs no extra query per row.
    """
    return QuotationListRow(
        id=quotation.id,
        number=quotation.number,
        customer_id=quotation.customer_id,
        customer_name=quotation.customer.name,
        customer_tier=quotation.customer.tier.name if quotation.customer.tier else None,
        owner_name=quotation.owner_name,
        status=quotation.status,
        currency=quotation.currency,
        total=float(quotation.total),
        margin_total=float(quotation.margin_total),
        line_count=len(quotation.lines),
        risk_band=quotation.risk_band,
        blended_risk_score=float(quotation.blended_risk_score),
        requires_approval=quotation.requires_approval,
        valid_until=quotation.valid_until,
        last_activity_at=quotation.last_activity_at,
        updated_at=quotation.updated_at,
    )


@router.get("/quotations", response_model=QuotationListPage)
async def read_quotations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pagination: Pagination = Depends(get_pagination),
    search: Optional[str] = Query(default=None, description="Number or customer name"),
    status_filter: Optional[QuotationStatus] = Query(default=None, alias="status"),
    sort: QuotationSort = Query(default=QuotationSort.UPDATED),
    order: SortOrder = Query(default=SortOrder.DESC),
) -> Any:
    """Screen 3. Paginated, because a sales team's quotation list grows without
    bound and the pipeline board reads the same rows."""
    items, total = await search_quotations(
        db,
        viewer=current_user,
        skip=pagination.skip,
        limit=pagination.limit,
        search=search,
        status=status_filter,
        sort=sort.value,
        order=order.value,
    )
    counts = await stage_counts(db, current_user)
    return QuotationListPage(
        items=[_row(item) for item in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=pagination.pages(total),
        counts=QuotationStageCounts(**counts),
    )


@router.get("/quotations/pipeline", response_model=dict[str, list[QuotationListRow]])
async def read_pipeline(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit_per_stage: int = Query(default=25, ge=1, le=100),
) -> Any:
    """The Kanban board (spec B2), one bucket per stage.

    Capped per stage rather than paginated: a board is a glance, and a column
    with four hundred cards in it is not one.
    """
    board: dict[str, list[QuotationListRow]] = {}
    for status_value in QuotationStatus:
        items, _ = await search_quotations(
            db,
            viewer=current_user,
            skip=0,
            limit=limit_per_stage,
            status=status_value,
            sort="updated",
            order="desc",
        )
        board[status_value.value] = [_row(item) for item in items]
    return board


@router.post("/quotations", response_model=QuotationRead, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    body: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        quotation = await create_draft_quotation(db, owner=current_user, obj_in=body)
    except ValueError as exc:
        raise _bad_request(exc)
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
    try:
        updated = await update_quotation(db, quotation, body)
    except ValueError as exc:
        raise _bad_request(exc)
    return QuotationRead.model_validate(updated)


@router.post("/quotations/{quotation_id}/lines", response_model=QuotationRead, status_code=status.HTTP_201_CREATED)
async def create_quotation_line(
    quotation_id: uuid.UUID,
    body: QuotationLineCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        updated = await add_line(db, quotation, body)
    except ValueError as exc:
        raise _bad_request(exc)
    return QuotationRead.model_validate(updated)


@router.patch("/quotations/{quotation_id}/lines/{line_id}", response_model=QuotationRead)
async def patch_quotation_line(
    quotation_id: uuid.UUID,
    line_id: uuid.UUID,
    body: QuotationLineUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        updated = await update_line(db, quotation, line_id, body)
    except ValueError as exc:
        raise _bad_request(exc)
    return QuotationRead.model_validate(updated)


@router.delete("/quotations/{quotation_id}/lines/{line_id}", response_model=QuotationRead)
async def delete_quotation_line(
    quotation_id: uuid.UUID,
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        updated = await remove_line(db, quotation, line_id)
    except ValueError as exc:
        raise _bad_request(exc)
    return QuotationRead.model_validate(updated)


@router.patch("/quotations/{quotation_id}/discount", response_model=QuotationRead)
async def patch_quotation_discount(
    quotation_id: uuid.UUID,
    body: QuotationDiscountUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        updated = await update_quotation(db, quotation, body)
    except ValueError as exc:
        raise _bad_request(exc)
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
    try:
        submitted, approval = await submit_quotation(db, quotation, current_user)
    except ValueError as exc:
        raise _bad_request(exc)
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


@router.post("/quotations/{quotation_id}/reload", response_model=QuotationRead)
async def reload_quotation_api(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """"Reload Data" from the workspace's top menu."""
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        updated = await reload_quotation(db, quotation)
    except ValueError as exc:
        raise _bad_request(exc)
    return QuotationRead.model_validate(updated)


@router.delete("/quotations/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quotation_api(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    quotation = await ensure_quotation_loaded(db, quotation_id)
    try:
        await delete_quotation(db, quotation)
    except ValueError as exc:
        raise _bad_request(exc)


@router.get(
    "/quotations/{quotation_id}/suggestions", response_model=list[UpsellSuggestion]
)
async def read_suggestions(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """The upsell and cross-sell panel beside the cart (spec B5)."""
    quotation = await ensure_quotation_loaded(db, quotation_id)
    return await upsell_service.suggest(db, quotation)


@router.post(
    "/quotations/{quotation_id}/suggestions/{product_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_suggestion(
    quotation_id: uuid.UUID,
    product_id: uuid.UUID,
) -> None:
    """Hides one suggestion on this quotation for a day."""
    await upsell_service.dismiss(quotation_id, product_id)
