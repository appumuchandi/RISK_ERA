from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.auth_deps import require_auth
from app.schemas.transaction import (
    TransactionIngestRequest,
    TransactionIngestResponse,
    TransactionDetail,
    TransactionListResponse,
)
from app.schemas.rules import RiskExplainResponse
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])




@router.get("", response_model=TransactionListResponse)
def list_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field: created_at, amount, risk_score, provider_event_id, status"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    risk: Optional[str] = Query(None, description="Risk level: low, medium, high, critical"),
    min_amount: Optional[Decimal] = Query(None, ge=0, description="Minimum amount"),
    max_amount: Optional[Decimal] = Query(None, ge=0, description="Maximum amount"),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    merchant_id: Optional[UUID] = Query(None, description="Filter by merchant ID"),
    device_id: Optional[UUID] = Query(None, description="Filter by device ID"),
    status: Optional[str] = Query(None, description="Filter by transaction status"),
    provider_event_id: Optional[str] = Query(None, description="Exact provider event ID"),
    search: Optional[str] = Query(None, description="Search provider_event_id (ILIKE)"),
    from_date: Optional[datetime] = Query(None, description="From date (ISO8601)"),
    to_date: Optional[datetime] = Query(None, description="To date (ISO8601)"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> TransactionListResponse:
    """List transactions with intelligence — pagination, sorting, filtering, risk scoring.

    All data derived from real PostgreSQL rows + deterministic RuleEngine evaluation.
    Risk fields (score, level, decision, triggered_rules) are computed, never hardcoded.
    """
    service = TransactionService(db)
    try:
        result = service.list_transactions(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            risk=risk,
            min_amount=min_amount,
            max_amount=max_amount,
            customer_id=customer_id,
            merchant_id=merchant_id,
            device_id=device_id,
            status=status,
            provider_event_id=provider_event_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
        )
        return TransactionListResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post(
    "",
    response_model=TransactionIngestResponse,
    status_code=http_status.HTTP_200_OK,
)
def ingest_transaction(
    request: TransactionIngestRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> TransactionIngestResponse:
    service = TransactionService(db)
    try:
        return service.ingest(request)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="Duplicate transaction")


@router.get("/{transaction_id}", response_model=TransactionDetail)
def get_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> TransactionDetail:
    from app.models import Transaction
    from sqlalchemy import select

    stmt = select(Transaction).where(Transaction.id == transaction_id)
    txn = db.execute(stmt).scalar_one_or_none()

    if not txn:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return TransactionDetail.model_validate(txn)


@router.get("/by-provider/{provider_event_id}", response_model=TransactionDetail)
def get_transaction_by_provider_id(
    provider_event_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> TransactionDetail:
    from app.models import Transaction
    from sqlalchemy import select

    stmt = select(Transaction).where(Transaction.provider_event_id == provider_event_id)
    txn = db.execute(stmt).scalar_one_or_none()

    if not txn:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return TransactionDetail.model_validate(txn)


@router.get("/{transaction_id}/risk-explain", response_model=RiskExplainResponse)
def get_transaction_risk_explain(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> RiskExplainResponse:
    from app.services.risk_explain_service import explain_transaction
    result = explain_transaction(db, transaction_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return RiskExplainResponse(**result)