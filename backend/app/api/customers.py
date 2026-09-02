from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.intelligence import CustomerProfile, CustomerListResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


@router.get("", response_model=CustomerListResponse)
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search external_id"),
    risk_tier: Optional[str] = Query(None, description="Filter by risk_tier"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CustomerListResponse:
    service = IntelligenceService(db)
    result = service.list_customers(page=page, page_size=page_size, search=search, risk_tier=risk_tier)
    return CustomerListResponse(**result)


@router.get("/{customer_id}/profile", response_model=CustomerProfile)
def get_customer_profile(
    customer_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> CustomerProfile:
    service = IntelligenceService(db)
    result = service.get_customer_profile(customer_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerProfile(**result)
