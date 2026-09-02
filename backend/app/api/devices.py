from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.auth.auth_deps import require_auth
from app.core.database import get_db
from app.schemas.intelligence import DeviceProfile, DeviceListResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter(prefix="/api/v1/devices", tags=["Devices"])


@router.get("", response_model=DeviceListResponse)
def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search fingerprint or ip"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> DeviceListResponse:
    service = IntelligenceService(db)
    result = service.list_devices(page=page, page_size=page_size, search=search)
    return DeviceListResponse(**result)


@router.get("/{device_id}/activity", response_model=DeviceProfile)
def get_device_activity(
    device_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> DeviceProfile:
    service = IntelligenceService(db)
    result = service.get_device_activity(device_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Device not found")
    return DeviceProfile(**result)
