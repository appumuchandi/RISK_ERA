from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.intelligence import MerchantProfile, MerchantListResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter(prefix="/api/v1/merchants", tags=["Merchants"])


@router.get("", response_model=MerchantListResponse)
def list_merchants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search name or category_code"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> MerchantListResponse:
    service = IntelligenceService(db)
    result = service.list_merchants(page=page, page_size=page_size, search=search)
    return MerchantListResponse(**result)


@router.get("/{merchant_id}/profile", response_model=MerchantProfile)
def get_merchant_profile(
    merchant_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> MerchantProfile:
    service = IntelligenceService(db)
    result = service.get_merchant_profile(merchant_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return MerchantProfile(**result)
